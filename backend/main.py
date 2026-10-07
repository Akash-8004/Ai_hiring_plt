import array
import asyncio
import base64
import json
import logging
import math
import os
import re
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from backend.core.models import JobDescription, ParsedResume
from backend.core.sanitizer import strip_html as _strip_html
from backend.core.sample_data import DEFAULT_JOB
from backend.config import frontend_base_url
from backend.live.relay import GeminiLiveRelay
from backend.services.ai_ranker import AIRankingService
from backend.services.HR_Round.hr_evaluator import HREvaluator
from backend.services.Technical.interviewer import get_interviewer_prompt
from backend.services.Technical.question_processor import QuestionProcessor
from backend.services.drive_metrics import compute_drive_metrics, score_candidates_for_drive
from backend.services.resume_parser import clean_other_links, extract_other_links, parse_resume_text, parse_uploaded_resume_with_ai, parse_resume_text_with_ai, _is_text_empty
from backend.services.Technical.technical_evaluator import TechnicalInterviewEvaluator
from backend.services import r2_storage
from backend.storage import database
from backend.services import email_service
from backend.services.email_templates import interview_invite_email
from backend.auth.security import (
    get_current_user,
    hash_password,
    log_activity,
    require_authenticated,
    require_company_admin,
    require_drive_delete,
    require_job_manage,
    require_permission,
)
from backend.auth.routes import router as auth_router
from backend.admin.routes import admin_router, company_router
from backend.leads.routes import router as leads_router

logger = logging.getLogger(__name__)


_is_dev = os.getenv("ENV", "production").lower() == "dev"

app = FastAPI(
    title="AI Hiring Platform API",
    version="0.2.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra_cors = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _extra_cors:
    _cors_origins.extend(o.strip() for o in _extra_cors.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers middleware (BUG 22) ────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    # Content-Security-Policy — tuned for React/Vite SPA + Google Fonts + WebSocket + media
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self' wss: ws:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )
    if not _is_dev:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# ── Register auth & admin routers ───────────────────────────────────────────
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(company_router)
app.include_router(leads_router)

# ── Shared services (stateless, safe to share) ─────────────────────────────
ranking_service = AIRankingService()
hr_evaluator = HREvaluator()
technical_evaluator = TechnicalInterviewEvaluator()
question_processor = QuestionProcessor()

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_MB = 25

_MAGIC_BYTES = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}


def _validate_magic_bytes(file_name: str, contents: bytes, ext: str) -> str | None:
    expected = _MAGIC_BYTES.get(ext)
    if expected and not contents[:len(expected)].startswith(expected):
        if ext == ".pdf" and contents[:4] == b"PK\x03\x04":
            return f"'{file_name}' appears to be a ZIP/DOCX file, not a PDF."
        return f"'{file_name}' does not appear to be a valid {ext.upper().lstrip('.')} file."
    if ext == ".docx" and not contents[:4] == b"PK\x03\x04":
        return f"'{file_name}' does not appear to be a valid DOCX file."
    return None


# ── Startup: seed Super Admin ──────────────────────────────────────────────

@app.on_event("startup")
def seed_super_admin():
    """Create the initial Super Admin from .env if none exists."""
    if database.count_super_admins() == 0:
        email = os.getenv("SUPER_ADMIN_EMAIL", "admin@aihiring.com").strip().lower()
        password = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123456")

        if not database.get_user_by_email(email):
            database.insert_user({
                "email": email,
                "password_hash": hash_password(password),
                "full_name": "Super Admin",
                "role": "super_admin",
                "company_id": None,
                "status": "active",
                "permissions": ["*"],
                "created_by": "system",
                "created_at": datetime.now(timezone.utc),
                "last_login": None,
                "login_count": 0,
                "active_session_token": None,
            })
            print(f"[OK] Super Admin seeded: {email}")

            database.insert_audit_log({
                "actor_id": "system",
                "actor_email": email,
                "actor_role": "super_admin",
                "company_id": None,
                "action": "system.super_admin_seeded",
                "category": "system",
                "severity": "info",
                "target_type": "user",
                "target_id": None,
                "target_label": f"Super Admin ({email})",
                "metadata": {},
                "ip_address": None,
                "user_agent": None,
                "timestamp": datetime.now(timezone.utc),
            })

    database.backfill_job_drives()
    database.normalize_user_emails()


@app.on_event("startup")
async def _start_resume_workers():
    from backend.services.resume_jobs import start_workers
    await start_workers(app)


@app.on_event("shutdown")
async def _stop_resume_workers():
    from backend.services.resume_jobs import stop_workers
    await stop_workers()


# ── Pydantic Models ────────────────────────────────────────────────────────

_REQUIRED_JOB_TEXT = {
    "title": "Job drive title",
    "department": "Department",
    "location": "Location",
    "education": "Education",
    "description": "Job description",
}


def _required_job_field_error(data: dict) -> str | None:
    """Return the first missing required job field error, or None."""
    for field, label in _REQUIRED_JOB_TEXT.items():
        if not str(data.get(field, "")).strip():
            return f"{label} is required"
    skills = data.get("required_skills")
    if not skills or not any(str(s).strip() for s in skills):
        return "Enter at least one required skill"
    return None


class JobPayload(BaseModel):
    title: str = Field(max_length=200)
    department: str = Field(max_length=150)
    location: str = Field(max_length=200)
    experience_years: int = Field(ge=0, le=30)
    required_skills: list[str]
    nice_to_have_skills: list[str] = []
    education: str = Field(max_length=1000)
    description: str = Field(max_length=50000)
    threshold: int = Field(ge=40, le=100)
    hr_interview_duration: int = Field(default=7, ge=3, le=60)
    technical_interview_duration: int = Field(default=5, ge=3, le=60)
    custom_questions: list[dict] = Field(default_factory=list)
    job_id: str | None = None

    @field_validator("title", "department", "location", "education", "description")
    @classmethod
    def validate_required_text(cls, v: str, info: ValidationInfo) -> str:
        value = v.strip() if isinstance(v, str) else ""
        if not value:
            raise ValueError(f"{_REQUIRED_JOB_TEXT[info.field_name]} is required")
        return value

    @field_validator("required_skills", "nice_to_have_skills")
    @classmethod
    def validate_skills(cls, v: list[str], info: ValidationInfo) -> list[str]:
        skills = [s.strip()[:200] for s in v if isinstance(s, str) and s.strip()]
        if info.field_name == "required_skills" and not skills:
            raise ValueError("Enter at least one required skill")
        return skills


class ManualResumePayload(BaseModel):
    file_name: str = "manual_resume.txt"
    text: str = Field(max_length=300000)


class RejectJdPayload(BaseModel):
    note: str = Field(default="", max_length=5000)


class ProcessQuestionsPayload(BaseModel):
    text: str = Field(default="", max_length=50000)


class EvaluationPayload(BaseModel):
    token: str
    transcript: list[dict[str, str]] = Field(default_factory=list)
    interview_type: str = "hr"


class DeadlinePayload(BaseModel):
    deadline: str | None = None


# ── Health (no auth) ───────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Workspace (authenticated, scoped to company) ──────────────────────────

@app.get("/api/workspace")
def workspace(
    job_id: str | None = None,
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    return _workspace_payload(company_id, user, job_id=job_id)


@app.put("/api/job")
def update_job(
    payload: JobPayload,
    user: dict = Depends(require_job_manage),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    job = JobDescription(**payload.model_dump(exclude={"job_id"}))
    # BUG 28: sanitize user-supplied job text fields on write
    job.title = _strip_html(job.title)
    job.description = _strip_html(job.description)
    job.department = _strip_html(job.department)
    job.location = _strip_html(job.location)
    job.education = _strip_html(job.education)
    for q in job.custom_questions:
        if isinstance(q, dict) and isinstance(q.get("text"), str):
            q["text"] = _strip_html(q["text"])
    effective_job_id = payload.job_id

    is_admin = user.get("role") in ("super_admin", "company_admin")

    if not is_admin:
        # Non-admin (sub-user) changes are submitted as a request for approval.
        if effective_job_id and not database.get_job_by_id(company_id, effective_job_id):
            raise HTTPException(status_code=404, detail="Drive not found")
        if not effective_job_id:
            effective_job_id = secrets.token_urlsafe(12)
        database.upsert_jd_request(
            company_id=company_id,
            job_id=effective_job_id,
            proposed=asdict(job),
            target_status=("create" if not payload.job_id else "edit"),
            requested_by={"id": str(user.get("_id") or ""), "email": user.get("email"), "name": user.get("full_name")},
        )
        log_activity(
            action=f"job.change_requested_{'create' if not payload.job_id else 'edit'}",
            category="job",
            actor=user,
            target_type="job",
            target_id=effective_job_id,
            target_label=job.title,
            request=request,
        )
        payload_data = _workspace_payload(company_id, user, job_id=effective_job_id)
        payload_data["jd_request"] = _clean_mongo(database.get_jd_request(company_id, effective_job_id))
        return payload_data

    if not effective_job_id:
        stored = database.upsert_job(job, company_id)
        effective_job_id = stored["job_id"]
        database.set_active_drive(company_id, effective_job_id)
        action = "job.created"
        database.clear_candidate_scores(company_id, job_id=effective_job_id)
    else:
        old_job = database.get_job_by_id(company_id, effective_job_id)
        if not old_job:
            raise HTTPException(status_code=404, detail="Drive not found")
        old_scoring = database.get_scoring_fields(old_job)
        new_scoring = database.get_scoring_fields(job)
        database.upsert_job(job, company_id, job_id=effective_job_id)
        action = "job.updated"
        if database.has_pending_jd_request(company_id, effective_job_id):
            database.resolve_jd_request(
                company_id,
                effective_job_id,
                "approved",
                reviewed_by={"id": str(user.get("_id") or ""), "email": user.get("email")},
                note="Drive updated directly by company admin",
            )
        if old_scoring != new_scoring:
            database.clear_candidate_scores(company_id, job_id=effective_job_id)
    log_activity(
        action=action,
        category="job",
        actor=user,
        target_type="job",
        target_id=effective_job_id,
        target_label=job.title,
        request=request,
    )
    return _workspace_payload(company_id, user, job_id=effective_job_id)


@app.get("/api/job/requests")
def list_job_requests(
    user: dict = Depends(require_job_manage),
) -> dict[str, Any]:
    """List JD change requests for the caller's company.

    Company admins / users with ``manage_jobs`` (the same access required to
    submit a change request) may read the queue. Sub-users see only the requests
    they submitted (so they can track their own pending proposals).
    """
    company_id = str(user["company_id"]) if user.get("company_id") else None
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    return {"requests": _jd_requests_for_user(company_id, user)}


@app.post("/api/job/requests/{request_id}/approve")
def approve_job_request(
    request_id: str,
    user: dict = Depends(require_company_admin),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    req_doc = database.get_jd_request_by_id(request_id)
    if not req_doc or req_doc.get("company_id") != company_id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    job_id = req_doc["job_id"]
    target_status = req_doc.get("target_status")

    if target_status == "delete":
        title = req_doc.get("proposed", {}).get("title", job_id)
        database.delete_job(company_id, job_id)
        if database.get_active_drive(company_id) == job_id:
            remaining = database.list_jobs(company_id)
            effective_job_id = remaining[0]["job_id"] if remaining else None
            database.set_active_drive(company_id, effective_job_id)
        else:
            effective_job_id = database.get_active_drive(company_id)
        database.resolve_jd_request(
            company_id, job_id, "approved",
            reviewed_by={"id": str(user.get("_id") or ""), "email": user.get("email")},
        )
        log_activity(
            action="job.deleted",
            category="job",
            actor=user,
            target_type="job",
            target_id=job_id,
            target_label=title,
            severity="critical",
            request=request,
        )
        return _workspace_payload(company_id, user, job_id=effective_job_id)

    proposed = dict(req_doc.get("proposed") or {})
    if err := _required_job_field_error(proposed):
        raise HTTPException(status_code=422, detail=err)
    job = JobDescription(**proposed)

    if target_status == "create":
        stored = database.upsert_job(job, company_id, job_id=job_id)
        effective_job_id = stored["job_id"]
        database.set_active_drive(company_id, effective_job_id)
        database.clear_candidate_scores(company_id, job_id=effective_job_id)
    else:
        old_job = database.get_job_by_id(company_id, job_id)
        if not old_job:
            raise HTTPException(status_code=404, detail="Drive not found")
        old_scoring = database.get_scoring_fields(old_job)
        new_scoring = database.get_scoring_fields(job)
        effective_job_id = job_id
        database.upsert_job(job, company_id, job_id=job_id)
        if old_scoring != new_scoring:
            database.clear_candidate_scores(company_id, job_id=effective_job_id)
    database.resolve_jd_request(
        company_id, job_id, "approved",
        reviewed_by={"id": str(user.get("_id") or ""), "email": user.get("email")},
    )
    log_activity(
        action="job.change_approved",
        category="job",
        actor=user,
        target_type="job",
        target_id=effective_job_id,
        target_label=job.title,
        request=request,
    )
    return _workspace_payload(company_id, user, job_id=effective_job_id)


@app.post("/api/job/requests/{request_id}/reject")
def reject_job_request(
    request_id: str,
    payload: RejectJdPayload | None = None,
    user: dict = Depends(require_company_admin),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    req_doc = database.get_jd_request_by_id(request_id)
    if not req_doc or req_doc.get("company_id") != company_id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request already resolved")

    job_id = req_doc["job_id"]
    note = payload.note.strip() if payload and payload.note else None
    database.resolve_jd_request(
        company_id, job_id, "rejected",
        reviewed_by={"id": str(user.get("_id") or ""), "email": user.get("email")},
        note=note,
    )
    log_activity(
        action="job.change_rejected",
        category="job",
        actor=user,
        target_type="job",
        target_id=job_id,
        target_label=req_doc.get("proposed", {}).get("title", ""),
        metadata={"note": note} if note else {},
        request=request,
    )
    return _workspace_payload(company_id, user)


@app.delete("/api/job/{job_id}")
def delete_job_drive(
    job_id: str,
    company_id: str | None = Query(None),
    user: dict = Depends(require_drive_delete),
    request: Request = None,
) -> dict[str, Any]:
    if user.get("role") == "super_admin" and company_id:
        cid = company_id
    elif user.get("company_id"):
        cid = str(user["company_id"])
    else:
        raise HTTPException(status_code=400, detail="company_id required")

    job_doc = database.get_job_doc(cid, job_id)
    if not job_doc:
        raise HTTPException(status_code=404, detail="Drive not found")
    title = job_doc.get("title", job_id)

    is_admin = user.get("role") in ("super_admin", "company_admin")

    if not is_admin:
        candidates_count = len(database.load_candidates(cid, job_id=job_id))
        database.upsert_jd_request(
            company_id=cid,
            job_id=job_id,
            proposed={
                "title": title,
                "department": job_doc.get("department", ""),
                "candidate_count": candidates_count,
            },
            target_status="delete",
            requested_by={"id": str(user.get("_id") or ""), "email": user.get("email"), "name": user.get("full_name")},
        )
        log_activity(
            action="job.change_requested_delete",
            category="job",
            actor=user,
            target_type="job",
            target_id=job_id,
            target_label=title,
            request=request,
        )
        payload_data = _workspace_payload(cid, user, job_id=job_id)
        payload_data["jd_request"] = _clean_mongo(database.get_jd_request(cid, job_id))
        return payload_data

    database.delete_job(cid, job_id)
    if database.has_pending_jd_request(cid, job_id):
        database.resolve_jd_request(
            cid,
            job_id,
            "approved",
            reviewed_by={"id": str(user.get("_id") or ""), "email": user.get("email")},
            note="Drive deleted directly by company admin",
        )
    log_activity(
        action="job.deleted",
        category="job",
        actor=user,
        target_type="job",
        target_id=job_id,
        target_label=title,
        severity="critical",
        request=request,
    )
    if database.get_active_drive(cid) == job_id:
        remaining = database.list_jobs(cid)
        database.set_active_drive(cid, remaining[0]["job_id"] if remaining else None)
    return _workspace_payload(cid, user)


@app.post("/api/job/questions/process")
async def process_questions_file(
    file: UploadFile = File(...),
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    """Restructure HR-supplied coding questions from an uploaded PDF/DOCX/TXT."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Allowed formats: PDF, DOCX, TXT.",
        )
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The file is empty.")
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {MAX_UPLOAD_MB} MB limit.",
        )
    try:
        questions = await asyncio.to_thread(
            question_processor.process_file, file.filename, contents
        )
    except Exception as exc:
        logger.exception("Question file processing failed")
        raise HTTPException(
            status_code=400,
            detail="Could not process the file. Please check the file and try again.",
        ) from exc
    return {
        "questions": questions,
        "provider_used": question_processor.last_provider_used,
        "message": question_processor.last_error,
    }


@app.post("/api/job/questions/process-text")
def process_questions_text(
    payload: ProcessQuestionsPayload,
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    """Restructure HR-supplied coding questions from manually pasted text."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Question text is required.")
    try:
        questions = question_processor.process_text(payload.text)
    except Exception as exc:
        logger.exception("Question text processing failed")
        raise HTTPException(
            status_code=400,
            detail="Could not process the questions. Please try again.",
        ) from exc
    return {
        "questions": questions,
        "provider_used": question_processor.last_provider_used,
        "message": question_processor.last_error,
    }


@app.post("/api/resumes/manual")
def add_manual_resume(
    payload: ManualResumePayload,
    user: dict = Depends(require_permission("manage_resumes")),
    request: Request = None,
) -> dict[str, Any]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Resume text is required.")
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first")
    resume = parse_resume_text_with_ai(payload.file_name, payload.text)
    _enforce_candidate_limit(company_id)
    database.upsert_candidate(resume, company_id=company_id, job_id=job_id)
    log_activity(
        action="candidate.uploaded",
        category="candidate",
        actor=user,
        target_type="candidate",
        target_label=f"{resume.full_name} ({resume.email})",
        request=request,
    )
    return _workspace_payload(company_id, user, job_id=job_id)


@app.post("/api/resumes/upload", status_code=202)
async def upload_resumes(
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_permission("manage_resumes")),
    request: Request = None,
) -> dict[str, Any]:
    from backend.services.resume_jobs import kick_workers
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    batch_id = secrets.token_urlsafe(16)
    accepted = []
    rejected = []

    for file in files:
        fname = file.filename or "resume.txt"
        suffix = Path(fname).suffix.lower()
        if suffix not in ALLOWED_RESUME_EXTENSIONS:
            rejected.append({"file_name": fname, "error": f"Unsupported file type '{suffix or 'unknown'}'. Allowed: PDF, DOCX, TXT, PNG, JPG, JPEG."})
            continue
        try:
            contents = await file.read()
        except Exception:
            rejected.append({"file_name": fname, "error": "Failed to read file."})
            continue
        if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
            rejected.append({"file_name": fname, "error": f"File exceeds {MAX_UPLOAD_MB} MB limit."})
            continue
        if not contents:
            rejected.append({"file_name": fname, "error": "File is empty."})
            continue
        magic_err = _validate_magic_bytes(fname, contents, suffix)
        if magic_err:
            rejected.append({"file_name": fname, "error": magic_err})
            continue
        try:
            spool_path = _spool_file(batch_id, fname, contents)
        except Exception:
            rejected.append({"file_name": fname, "error": "Failed to spool file."})
            continue
        job_doc = {
            "batchId": batch_id,
            "company_id": company_id,
            "job_id": job_id,
            "file_name": fname,
            "ext": suffix,
            "size_bytes": len(contents),
            "spool_path": str(spool_path),
            "status": "queued",
            "stage": "queued",
            "ocr_used": False,
            "error": None,
            "attempts": 0,
            "candidate_email": None,
            "candidate_name": None,
            "created_at": datetime.now(timezone.utc),
            "claimed_at": None,
            "finished_at": None,
            "expireAt": None,
            "actor": {"user_id": str(user.get("_id") or ""), "email": user.get("email")},
        }
        database.insert_resume_job(job_doc)
        accepted.append(fname)

    log_activity(
        action="candidate.bulk_uploaded",
        category="candidate",
        actor=user,
        metadata={"count": len(accepted), "file_names": accepted, "rejected": len(rejected), "batch_id": batch_id},
        request=request,
    )
    kick_workers()
    return {"batchId": batch_id, "accepted": len(accepted), "rejected": rejected}


def _spool_file(batch_id: str, file_name: str, contents: bytes) -> Path:
    # NOTE: temp_files/resumes/<batchId>/ is two levels deep, so
    # serve_local_recording (which only joins one level) cannot serve it.
    # Do not add a serving route for resume spool files.
    safe_name = Path(file_name).name
    spool_dir = Path(__file__).resolve().parent.parent / "temp_files" / "resumes" / batch_id
    spool_dir.mkdir(parents=True, exist_ok=True)
    spool_path = spool_dir / safe_name
    spool_path.write_bytes(contents)
    return spool_path


# ── Invitation ──────────────────────────────────────────────────────────────

def _build_interview_link(token: str, interview_type: str) -> str:
    """Public interview URL using the configured frontend origin."""
    return f"{frontend_base_url()}/?interview={token}&type={interview_type}"


def _normalise_invitation(invitation: dict | None) -> dict | None:
    """Repair invitation links previously stored with a localhost origin."""
    if not isinstance(invitation, dict):
        return invitation
    link = invitation.get("link")
    if (
        isinstance(link, str)
        and re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?", link) is not None
    ):
        invitation = dict(invitation)
        invitation["link"] = _build_interview_link(
            invitation.get("token", ""), invitation.get("type", "technical")
        )
    return invitation


@app.put("/api/job/deadline")
def update_round_deadline(
    interview_type: str,
    payload: DeadlinePayload,
    user: dict = Depends(require_permission("conduct_interviews")),
) -> dict[str, Any]:
    if interview_type not in ("hr", "technical"):
        raise HTTPException(status_code=400, detail="Interview type must be 'hr' or 'technical'.")
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not company_id or not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first.")
    database.set_job_deadline(company_id, job_id, interview_type, _normalise_deadline(payload.deadline))
    return _workspace_payload(company_id, user, job_id=job_id)


# ── Pipeline override reasons ────────────────────────────────────────────────
# An admin may bypass a pipeline gate (invite a resume-rejected candidate to
# the HR round, or invite a candidate who failed HR to the technical round).
# Every such bypass must carry one of these reasons so it is auditable later.
OVERRIDE_REASONS = {
    "strong_resume": "Strong resume / screening mis-scored",
    "referral": "Referred by a team member",
    "recruiter_request": "Direct request from the hiring manager",
    "candidate_experience": "Relevant experience the rubric missed",
    "role_priority": "Urgent / priority role",
}
MAX_OVERRIDE_NOTE = 500
PER_CANDIDATE_MAX_WINDOW_DAYS = int(os.getenv("PER_CANDIDATE_MAX_WINDOW_DAYS", "14"))


@app.post("/api/candidates/{email}/invite")
def invite_candidate(
    email: str,
    interview_type: str = "technical",
    send_email: bool = True,
    override_reason: str = "",
    override_note: str = "",
    deadline: str = "",
    user: dict = Depends(require_permission("conduct_interviews")),
    request: Request = None,
) -> dict[str, Any]:
    """Generate an interview invitation link. interview_type can be 'technical' or 'hr'.

    Advancing a candidate past a gate they did not clear is allowed, but only
    as an explicit, recorded override — never silently. See OVERRIDE_REASONS.
    """
    if interview_type not in ("hr", "technical"):
        raise HTTPException(status_code=400, detail="Interview type must be 'hr' or 'technical'.")
    company_id = str(user["company_id"]) if user.get("company_id") else None

    # Resolve the drive exactly as the pipeline view does, and look the candidate
    # up *within that drive*.
    #
    # A candidate document is keyed by (email, company, job), so the same person
    # uploaded to a second drive has a second, independent document. Looking the
    # candidate up by email alone returns an arbitrary one of them, so the invite
    # would be validated against — and written to — a different drive's state.
    # That surfaced as "The hr deadline has passed" on candidates that had never
    # been near an expired deadline, while the UI showed the active drive's
    # healthy one.
    effective_job_id = _resolve_effective_job_id(company_id)
    candidate_doc = (
        database.get_candidate_doc(email, company_id, effective_job_id)
        if effective_job_id
        else None
    )
    if not candidate_doc:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found in the current job drive.",
        )
    job_id = candidate_doc.get("job_id") or effective_job_id
    job_doc = database.get_job_doc(company_id, job_id) if company_id and job_id else None
    job_doc = job_doc or {}
    deadline_field = (
        "hr_deadline" if interview_type == "hr" else "technical_deadline"
    )
    drive_deadline = job_doc.get(deadline_field) if job_doc else None
    per_candidate = _normalise_deadline(deadline) if deadline else None
    effective = per_candidate or drive_deadline

    if not effective:
        raise HTTPException(
            status_code=400,
            detail=f"Set a {interview_type} deadline before sending invitations.",
        )
    if _deadline_has_passed(effective):
        raise HTTPException(status_code=400, detail=f"The {interview_type} deadline has passed.")
    if per_candidate:
        cap = datetime.now(timezone.utc) + timedelta(days=PER_CANDIDATE_MAX_WINDOW_DAYS)
        if _parse_deadline(per_candidate) > cap:
            raise HTTPException(
                status_code=400,
                detail=f"A per-candidate window cannot extend more than {PER_CANDIDATE_MAX_WINDOW_DAYS} days from now.",
            )
    if interview_type == "technical" and _deadline_is_active(job_doc.get("hr_deadline")):
        raise HTTPException(status_code=403, detail="Technical round unlocks after the HR deadline passes.")

    # ── Pipeline gate ──────────────────────────────────────────────────────
    # Three explicit outcomes instead of a "decision in (PASS, FAIL)" test,
    # which used to let a FAILED HR round through indistinguishably from a pass.
    hr_interview = candidate_doc.get("hr_interview") or {}
    hr_decision = hr_interview.get("decision")

    # Shortlist status is re-derived exactly as services/ranking.py does.
    # A missing cached_score is treated as "not shortlisted", which
    # conservatively requires a reason rather than silently waving the invite by.
    cached_score = candidate_doc.get("cached_score") or {}
    resume_score = cached_score.get("total_score")
    threshold = job_doc.get("threshold", 80)
    resume_shortlisted = isinstance(resume_score, (int, float)) and resume_score >= threshold

    if interview_type == "technical":
        if hr_decision == "PASS":
            override_needed = False
        elif hr_decision == "FAIL":
            override_needed = True
        else:
            # Never attempted the HR round — a hard block, not an override.
            raise HTTPException(
                status_code=400,
                detail="Candidate must complete the HR round before a technical invitation can be issued.",
            )
    else:
        override_needed = not resume_shortlisted

    reason_code = (override_reason or "").strip()
    if override_needed:
        if not reason_code:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "override_reason_required",
                    "message": (
                        f"This candidate did not clear the "
                        f"{'resume screening' if interview_type == 'hr' else 'HR round'}. "
                        "A reason is required to invite them anyway."
                    ),
                },
            )
        if reason_code not in OVERRIDE_REASONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_override_reason",
                    "message": "Select a valid override reason.",
                },
            )

    if override_needed:
        database.record_candidate_override(
            email,
            {
                "round": interview_type,
                "reason": reason_code,
                "reason_label": OVERRIDE_REASONS[reason_code],
                "note": (override_note or "").strip()[:MAX_OVERRIDE_NOTE],
                "by_email": user.get("email", ""),
                "by_role": user.get("role", ""),
                "at": datetime.now(timezone.utc).isoformat(),
                "context": {
                    "resume_score": resume_score,
                    "resume_status": "Shortlisted" if resume_shortlisted else "Rejected",
                    "hr_decision": hr_decision,
                    "hr_score": hr_interview.get("score"),
                },
            },
            company_id,
            job_id,
        )

    invitation_key = "hr_invitation" if interview_type == "hr" else "invitation"
    invitation = candidate_doc.get(invitation_key) or {}
    if not invitation.get("token"):
        token = secrets.token_urlsafe(12)
        invitation = {
            "token": token,
            "type": interview_type,
            "link": _build_interview_link(token, interview_type),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": effective,
            "deadline_source": "per_candidate" if per_candidate else "drive",
        }
        if interview_type == "hr":
            database.set_candidate_hr_invitation(email, invitation, company_id, job_id)
        else:
            database.set_candidate_invitation(email, invitation, company_id, job_id)
    else:
        token = invitation.get("token")
        if per_candidate and per_candidate != invitation.get("expires_at"):
            if _deadline_has_passed(invitation.get("expires_at")):
                raise HTTPException(
                    status_code=400,
                    detail="This invitation window has already expired and cannot be amended. Use 'Still Invite' to issue an override if permitted.",
                )
            database.set_candidate_invitation_expiry(
                email, interview_type, per_candidate, "per_candidate", company_id, job_id
            )
            invitation["expires_at"] = per_candidate
            invitation["deadline_source"] = "per_candidate"
    token = invitation["token"]
    log_activity(
        action=(
            f"candidate.{interview_type}_round_overridden"
            if override_needed
            else f"candidate.invited_{interview_type}"
        ),
        category="candidate",
        actor=user,
        target_type="candidate",
        target_id=email,
        target_label=email,
        metadata={
            "interview_type": interview_type,
            "deadline_source": invitation.get("deadline_source", "per_candidate" if per_candidate else "drive"),
            "deadline": invitation.get("expires_at", effective),
            **(
                {
                    "override": True,
                    "override_reason": reason_code,
                    "override_reason_label": OVERRIDE_REASONS[reason_code],
                    "override_note": (override_note or "").strip()[:MAX_OVERRIDE_NOTE],
                    "hr_decision": hr_decision,
                    "resume_score": resume_score,
                }
                if override_needed
                else {}
            ),
        },
        severity="warning" if override_needed else "info",
        request=request,
    )

    # ── Send invitation email if requested ────────────────────────────────
    email_sent = False
    email_error = None
    already_sent = (candidate_doc.get("email_sent") or {}).get(interview_type, False)
    if send_email:
        if already_sent:
            email_sent = True
        else:
            try:
                candidate_name = candidate_doc.get("full_name", email)
                email_link = _build_interview_link(token, interview_type)
                subject, html_body, plain_body = interview_invite_email(
                    candidate_name, interview_type, email_link, deadline=invitation.get("expires_at"),
                )
                result = email_service.send_email(email, subject, html_body, plain_body)
                email_sent = result.get("ok", False)
                email_error = result.get("error")
                email_service.log_email_send(
                    to_email=email,
                    subject=subject,
                    email_type="interview_invite",
                    status="sent" if email_sent else "failed",
                    error_message=email_error,
                    metadata={"interview_type": interview_type, "token": token},
                    sent_by=user.get("email", "system"),
                )
                if email_sent:
                    database.set_candidate_email_sent(email, interview_type, company_id, job_id)
            except Exception as exc:
                email_error = str(exc)

    payload = _workspace_payload(company_id, user, job_id=_active_drive_id(company_id))
    payload["email_sent"] = email_sent
    if email_error:
        payload["email_error"] = email_error
    return payload

@app.get("/api/interview/session/{token}")
def interview_session(token: str) -> dict[str, Any]:
    """Public endpoint — candidates access via invitation token, no auth needed."""
    email, company_id = _candidate_ref_for_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")

    candidate_doc = database.get_candidate_doc(email, company_id)
    if not candidate_doc:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    _ensure_invitation_active(token, candidate_doc)

    job_id = candidate_doc.get("job_id")
    candidates = database.load_candidates(company_id, job_id=job_id)
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    current_job = (
        database.get_job_by_id(str(company_id), job_id) if company_id and job_id else None
    ) or database.load_job(company_id) or DEFAULT_JOB

    # Determine interview type from the invitation
    invitation = candidate_doc.get("invitation") or {}
    hr_invitation = candidate_doc.get("hr_invitation") or {}
    if invitation.get("token") == token:
        interview_type = invitation.get("type", "technical")
        interview_data = candidate_doc.get("technical_interview") or {}
    elif hr_invitation.get("token") == token:
        interview_type = "hr"
        interview_data = candidate_doc.get("hr_interview") or candidate_doc.get("interview") or {}
    else:
        interview_type = "technical"
        interview_data = {}

    # Load company name for branding
    company_name = "AI Hiring Platform"
    if company_id:
        company = database.get_company_by_id(str(company_id))
        if company:
            company_name = company.get("settings", {}).get("interview_branding_name", company.get("name", company_name))

    # NOTE: systemPrompt is intentionally NOT returned here (contains full resume
    # PII).  It is generated server-side in the WebSocket handler instead.

    # Redact candidate name to first name only for this public endpoint
    first_name = (resume.full_name or "Candidate").split()[0] if resume.full_name else "Candidate"

    return {
        "token": token,
        "candidateName": first_name,
        "jobTitle": current_job.title,
        "companyName": company_name,
        "interviewType": interview_type,
        "customQuestions": (
            _sanitized_questions(current_job.custom_questions)
            if interview_type == "technical"
            else []
        ),
        "completed": interview_data.get("status") == "completed",
        "decision": interview_data.get("decision"),
        "score": interview_data.get("score"),
    }


# ── Evaluation ──────────────────────────────────────────────────────────────

@app.post("/api/interview/evaluate")
def evaluate_interview(payload: EvaluationPayload) -> dict[str, Any]:
    """Public endpoint — called by interview UI after interview completes."""
    email, company_id = _candidate_ref_for_token(payload.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    candidate_doc = database.get_candidate_doc(email, company_id) or {}
    invitation = _ensure_invitation_active(payload.token, candidate_doc)
    if payload.interview_type != invitation.get("type", "technical"):
        raise HTTPException(status_code=400, detail="Interview type does not match invitation.")
    job_id = candidate_doc.get("job_id")
    candidates = database.load_candidates(company_id, job_id=job_id)
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    current_job = (
        database.get_job_by_id(str(company_id), job_id) if company_id and job_id else None
    ) or database.load_job(company_id) or DEFAULT_JOB
    return _run_interview_evaluation(
        email, resume, payload.interview_type, payload.transcript,
        current_job, company_id, job_id=job_id,
    )


# ── Recording Upload & Playback ────────────────────────────────────────────

@app.post("/api/interview/recording/upload")
async def upload_recording(
    token: str = Form(...),
    interview_type: str = Form("technical"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Receive the browser-recorded WebM, persist to R2 + temp_files."""
    email, company_id = _candidate_ref_for_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")

    candidate_doc = database.get_candidate_doc(email, company_id) or {}
    _ensure_invitation_active(token, candidate_doc)
    job_id = candidate_doc.get("job_id")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty recording file.")

    recording_meta = await asyncio.to_thread(
        r2_storage.upload_recording, email, interview_type, file_bytes
    )
    database.set_candidate_interview_recording(
        email, interview_type, recording_meta, company_id, job_id
    )
    return {"ok": True, "recording": recording_meta}


@app.get("/api/interview/recording/local/{filename}")
def serve_local_recording(filename: str):
    """Serve a recording file from temp_files/ for local development/testing."""
    safe = Path(filename).name  # prevent path traversal
    project_root = Path(__file__).resolve().parent.parent
    # Check temp_files/hr/ first, then fall back to temp_files/
    file_path = project_root / "temp_files" / "hr" / safe
    if not file_path.is_file():
        file_path = project_root / "temp_files" / safe
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Recording file not found.")
    return FileResponse(str(file_path), media_type="video/webm", content_disposition_type="inline")


@app.get("/api/interview/recording/{email}/{interview_type}")
def get_recording_url(
    email: str,
    interview_type: str,
    user: dict = Depends(require_permission("conduct_interviews")),
) -> dict[str, Any]:
    """Return a presigned URL (or local path) so HR can play the recording."""
    company_id = str(user["company_id"]) if user.get("company_id") else None
    doc = database.get_candidate_doc(email, company_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    interview = doc.get(f"{interview_type}_interview") or {}
    recording = interview.get("recording")
    if not recording:
        raise HTTPException(status_code=404, detail="No recording available for this interview.")

    r2_key = recording.get("r2_key", "")
    presigned_url = r2_storage.get_recording_presigned_url(r2_key)
    return {
        "url": presigned_url,
        "local_path": recording.get("local_path"),
        "size_bytes": recording.get("size_bytes", 0),
        "r2_configured": r2_storage.is_configured(),
    }


# ── Live Voice Interview (WebSocket relay) ─────────────────────────────────

CLOSING_PHRASES = (
    "interview is now complete",
    "interview is complete",
    "interview is now finished",
    "this concludes the interview",
)

# Gemini's Live API uses automatic voice-activity detection (VAD) by default.
# The browser streams mic PCM continuously and the server forwards it to Gemini,
# which detects the candidate's speech. Gemini does NOT finalize a turn on silence
# alone here, so once the candidate stops talking we send `audio_stream_end` to
# flush the buffered audio (the documented "hybrid VAD" pattern) and trigger the
# model's reply. Manual activity_start/activity_end windowing was fragile and
# crashed with "1007 Precondition check failed".
SPEECH_THRESHOLD = 0.008  # normalised RMS above which we treat audio as speech
SILENCE_FLUSH = 1.0  # seconds of low-energy audio before finalizing the turn


def _pcm_rms(data: bytes) -> float:
    """Normalised RMS of 16-bit little-endian PCM (0.0..1.0)."""
    if not data or len(data) % 2 != 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data)
    if not samples:
        return 0.0
    total = 0.0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples)) / 32768.0


def _interview_is_complete(transcript: list[dict]) -> bool:
    """Detect the interviewer's closing phrase to trigger auto-evaluation."""
    for message in reversed(transcript):
        if message.get("role") == "interviewer":
            text = str(message.get("content", "") or "").lower()
            return any(phrase in text for phrase in CLOSING_PHRASES)
    return False


@app.websocket("/ws/interview/{token}")
async def interview_live_ws(websocket: WebSocket, token: str) -> None:
    await websocket.accept()

    email, company_id = _candidate_ref_for_token(token)
    if not email:
        await websocket.send_json({"type": "error", "message": "Invitation not found or invalid."})
        await websocket.close()
        return

    candidate_doc = database.get_candidate_doc(email, company_id)
    try:
        _ensure_invitation_active(token, candidate_doc or {})
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "message": exc.detail, "expired": exc.status_code == 410})
        await websocket.close(code=1008)
        return
    job_id = (candidate_doc or {}).get("job_id")
    candidates = database.load_candidates(company_id, job_id=job_id)
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        await websocket.send_json({"type": "error", "message": "Candidate not found."})
        await websocket.close()
        return

    current_job = (
        database.get_job_by_id(str(company_id), job_id) if company_id and job_id else None
    ) or database.load_job(company_id) or DEFAULT_JOB
    doc = candidate_doc or {}
    invitation = doc.get("invitation") or {}
    hr_invitation = doc.get("hr_invitation") or {}
    if invitation.get("token") == token:
        interview_type = invitation.get("type", "technical")
    elif hr_invitation.get("token") == token:
        interview_type = "hr"
    else:
        interview_type = "technical"

    system_prompt = get_interviewer_prompt(interview_type, current_job, resume)
    relay = GeminiLiveRelay(system_prompt=system_prompt)

    if not relay.available:
        await websocket.send_json(
            {"type": "error", "message": "Gemini Live is not configured (GEMINI_API_KEY missing)."}
        )
        await websocket.close()
        return

    transcript: list[dict] = []
    user_buffer: list[str] = []
    model_buffer: list[str] = []

    def flush_user_turn() -> None:
        text = " ".join(user_buffer).strip()
        if text:
            transcript.append({"role": "candidate", "content": text})
            database.append_transcript_turn(email, "candidate", text, company_id=company_id, job_id=job_id)
        user_buffer.clear()

    def flush_model_turn() -> None:
        text = " ".join(model_buffer).strip()
        if text:
            transcript.append({"role": "interviewer", "content": text})
            database.append_transcript_turn(email, "interviewer", text, company_id=company_id, job_id=job_id)
        model_buffer.clear()

    async def send_ws(payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            pass

    async def client_loop(to_gemini: asyncio.Queue, done: asyncio.Event) -> None:
        try:
            while not done.is_set():
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                mtype = msg.get("type")
                print(
                    f"WS<- {mtype}"
                    + (f" len={len(msg.get('data') or '')}" if mtype == "audio" else ""),
                    flush=True,
                )
                if mtype == "audio":
                    data = base64.b64decode(msg.get("data") or "")
                    await to_gemini.put(("audio", data))
                elif mtype == "answer":
                    answer_text = (msg.get("text") or "").strip()
                    question = (msg.get("question") or "").strip()
                    if answer_text:
                        turn = {
                            "role": "candidate",
                            "content": answer_text,
                            "type": "written",
                        }
                        if question:
                            turn["question"] = question
                        transcript.append(turn)
                        database.append_transcript_turn(
                            email,
                            "candidate",
                            answer_text,
                            {"type": "written", "question": question},
                            company_id=company_id,
                            job_id=job_id,
                        )
                        await to_gemini.put(
                            (
                                "text",
                                "The candidate submitted a written answer for the coding question. "
                                "Acknowledge their answer briefly. If there are more custom questions "
                                "remaining, say something like 'Let's move on to the next question' and "
                                "ask the next one. If this was the last one, continue the normal flow.",
                            )
                        )
                    else:
                        await to_gemini.put(
                            (
                                "text",
                                "The candidate clicked Submit without writing any answer. Tell them: "
                                "'I haven't received a written answer. You can either type your answer "
                                "in the answer box and click Submit, or if you prefer we can move on to "
                                "the next question.' Then wait for their choice.",
                            )
                        )
                elif mtype == "end":
                    done.set()
        except (WebSocketDisconnect, RuntimeError):
            done.set()

    async def send_loop(session, to_gemini: asyncio.Queue, done: asyncio.Event, state: dict) -> None:
        last_speech = 0.0
        try:
            while not done.is_set():
                try:
                    kind, payload = await asyncio.wait_for(to_gemini.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if last_speech and not state["model_active"] and now - last_speech > SILENCE_FLUSH:
                        await relay.audio_stream_end(session)
                        last_speech = 0.0
                        print("WS! flushed (silence timeout)", flush=True)
                    continue
                now = time.monotonic()
                if kind == "audio":
                    if not state["model_active"]:
                        # Stream everything to Gemini; its automatic VAD detects the
                        # speech. When the candidate falls silent long enough we send
                        # audio_stream_end so Gemini finalizes the turn and replies.
                        if _pcm_rms(payload) >= SPEECH_THRESHOLD:
                            last_speech = now
                        elif last_speech and now - last_speech > SILENCE_FLUSH:
                            await relay.audio_stream_end(session)
                            last_speech = 0.0
                            print("WS! flushed (silence)", flush=True)
                        await relay.send_audio(session, payload)
                    # else: model is speaking; drop the mic feed so its own voice
                    # cannot make it barge itself in (echo).
                elif kind == "text":
                    # Inject a textual instruction into the live session (e.g. to
                    # acknowledge a written answer and move to the next question).
                    await session.send_client_content(
                        turns={"role": "user", "parts": [{"text": payload}]},
                        turn_complete=True,
                    )
        except Exception:
            import traceback

            traceback.print_exc()
            await send_ws({"type": "error", "message": "Live session failed."})
            done.set()

    async def receive_loop(session, done: asyncio.Event, state: dict) -> None:
        try:
            state["model_active"] = True
            await relay.begin_interview(session)
            model_turn_started = False
            while not done.is_set():
                async for message in session.receive():
                    sc = message.server_content
                    if not sc:
                        continue
                    if getattr(sc, "interrupted", False):
                        await send_ws({"type": "interrupt"})
                    if sc.model_turn:
                        if not model_turn_started:
                            model_turn_started = True
                            state["model_active"] = True
                            await send_ws({"type": "model_turn_start"})
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                encoded = base64.b64encode(part.inline_data.data).decode("ascii")
                                await send_ws({"type": "audio", "data": encoded})
                    if sc.input_transcription and sc.input_transcription.text:
                        user_buffer.append(sc.input_transcription.text.strip())
                        await send_ws({"type": "transcript", "role": "candidate", "text": sc.input_transcription.text.strip()})
                    if sc.output_transcription and sc.output_transcription.text:
                        model_buffer.append(sc.output_transcription.text.strip())
                        await send_ws({"type": "transcript", "role": "interviewer", "text": sc.output_transcription.text.strip()})
                    if sc.turn_complete:
                        state["model_active"] = False
                        break
                flush_user_turn()
                flush_model_turn()
                model_turn_started = False
                await send_ws({"type": "turn_complete"})
                if _interview_is_complete(transcript):
                    result = await asyncio.to_thread(
                        _run_interview_evaluation,
                        email, resume, interview_type, list(transcript), current_job, company_id, job_id,
                    )
                    if result.get("blocked"):
                        await send_ws({
                            "type": "error",
                            "message": result.get("message", "Insufficient interview credits."),
                            "blocked": True,
                            "credits": result.get("credits"),
                            "required": result.get("required"),
                        })
                    else:
                        await send_ws({"type": "evaluation", "result": result})
                    done.set()
                    try:
                        await websocket.close(code=1000)
                    except Exception:
                        pass
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await send_ws({"type": "error", "message": str(exc)})
            done.set()

    try:
        async with relay.connect() as session:
            to_gemini: asyncio.Queue = asyncio.Queue()
            done: asyncio.Event = asyncio.Event()
            await send_ws({"type": "ready"})
            state: dict = {"model_active": False}
            tasks = [
                asyncio.create_task(client_loop(to_gemini, done)),
                asyncio.create_task(send_loop(session, to_gemini, done, state)),
                asyncio.create_task(receive_loop(session, done, state)),
            ]
            try:
                await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
    except Exception as exc:
        await send_ws({"type": "error", "message": str(exc)})
    finally:
        await send_ws({"type": "closed"})
        try:
            await websocket.close()
        except Exception:
            pass


# ── Workspace Payload ───────────────────────────────────────────────────────

def _active_drive_id(company_id: str | None) -> str | None:
    if not company_id:
        return None
    active = database.get_active_drive(company_id)
    if active:
        return active
    jobs = database.list_jobs(company_id)
    return jobs[0]["job_id"] if jobs else None


def _resolve_effective_job_id(company_id: str | None, job_id: str | None = None) -> str | None:
    if not company_id:
        return None
    if job_id and database.get_job_by_id(company_id, job_id):
        database.set_active_drive(company_id, job_id)
        return job_id
    active = database.get_active_drive(company_id)
    if active and database.get_job_by_id(company_id, active):
        return active
    jobs = database.list_jobs(company_id)
    if jobs:
        database.set_active_drive(company_id, jobs[0]["job_id"])
        return jobs[0]["job_id"]
    return None


def _workspace_payload(
    company_id: str | None = None,
    user: dict | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    effective_job_id = _resolve_effective_job_id(company_id, job_id) if company_id else None
    drive = database.get_job_by_id(company_id, effective_job_id) if company_id and effective_job_id else None
    stored_job = drive
    current_job = stored_job or DEFAULT_JOB
    job_doc = database.get_job_doc(company_id, effective_job_id) if company_id and effective_job_id else {}
    _auto_fail_missed_deadlines(company_id, effective_job_id, job_doc or {})
    hr_deadline = (job_doc or {}).get("hr_deadline")
    technical_deadline = (job_doc or {}).get("technical_deadline")
    hr_deadline_passed = _deadline_has_passed(hr_deadline)
    technical_deadline_passed = _deadline_has_passed(technical_deadline)
    candidate_resumes = (
        database.load_candidates(company_id, job_id=effective_job_id)
        if company_id
        else database.load_candidates()
    )
    # Batch-fetch candidate docs to avoid N+1 lookups
    candidate_emails = [r.email for r in candidate_resumes]
    docs_by_email = database.get_candidate_docs_batch(
        candidate_emails, company_id, effective_job_id
    ) if candidate_emails else {}

    # Prefer persisted scores; fallback to rescoring if missing
    def _get_persisted_score(email: str, resume):
        doc = docs_by_email.get(email) or {}
        scoring = doc.get("scoring") or {}
        if scoring.get("score") is not None and scoring.get("breakdown") is not None:
            return type("Persisted", (), {
                "score": type("S", (), {
                    "overall": scoring["score"],
                    "breakdown": scoring["breakdown"],
                    "weights": scoring.get("weights") or {},
                    "explanation": scoring.get("explanation") or "",
                })(),
                "to_row": lambda self, r=resume: {
                    "candidate_id": r.candidate_id,
                    "name": r.name,
                    "email": r.email,
                    "phone": r.phone,
                    "score": self.score.overall,
                    "reasons": scoring.get("reasons") or [],
                },
                "candidate": r,
            })()
        return None

    results = []
    for r in candidate_resumes:
        ps = _get_persisted_score(r.email, r)
        if ps:
            results.append(ps)
        else:
            # Fallback: score and persist for future loads
            scored_list = score_candidates_for_drive(
                [r], current_job, company_id or "", effective_job_id or ""
            )
            for sr in scored_list:
                try:
                    database.set_candidate_scoring(
                        sr.candidate.email,
                        {
                            "score": sr.score.overall,
                            "breakdown": sr.score.breakdown,
                            "weights": getattr(sr.score, "weights", {}) or {},
                            "reasons": sr.to_row().get("reasons", []),
                            "explanation": getattr(sr.score, "explanation", ""),
                        },
                        company_id,
                        effective_job_id,
                    )
                except Exception:
                    pass
                results.append(sr)

    rows = []

    for result in results:
        row = result.to_row()
        row["fileName"] = result.candidate.file_name
        row["linkedin"] = result.candidate.linkedin
        row["github"] = result.candidate.github
        derived_links = extract_other_links(result.candidate.raw_text, result.candidate.linkedin)
        row["otherLinks"] = list({
            link["url"]: link
            for link in clean_other_links(result.candidate.other_links) + derived_links
            if link.get("url")
        }.values())
        row["education"] = result.candidate.education
        row["extractedSkills"] = result.candidate.skills
        # Trim large text from list payload for performance
        row.pop("resumeText", None)
        row["jobTitle"] = result.candidate.job_title
        row["location"] = result.candidate.location
        row["professionalSummary"] = result.candidate.summary
        row["parsingProvider"] = result.candidate.parsing_provider
        row["noText"] = bool(
            result.candidate.parsing_provider == "none"
            or (result.candidate.raw_text or "").startswith("[NO_TEXT_EXTRACTED]")
            or _is_text_empty(result.candidate.raw_text)
        )
        # Keep breakdown small if present; don't force large blobs
        if hasattr(result, "score") and getattr(result.score, "breakdown", None) is not None:
            row["breakdown"] = result.score.breakdown
        row["uploadedAt"] = result.candidate.uploaded_at.isoformat()
        doc = docs_by_email.get(result.candidate.email) or {}
        row["pipelineStage"] = doc.get("pipelineStage", "uploaded")
        hr_inv = doc.get("hr_invitation") or {}
        tech_inv = doc.get("invitation") or {}
        row["invitation"] = _normalise_invitation(tech_inv)
        row["hr_invitation"] = _normalise_invitation(hr_inv)
        row["interview"] = doc.get("interview")
        row["technical_interview"] = doc.get("technical_interview")
        row["hr_interview"] = doc.get("hr_interview")
        row["interview_transcript"] = doc.get("interview_transcript") or []
        row["email_sent"] = doc.get("email_sent") or {}
        row["overrides"] = doc.get("overrides") or []
        row["tech_round_locked"] = _deadline_is_active(hr_deadline)
        row["late_entry"] = bool(hr_deadline_passed and not hr_inv.get("token"))
        row["deadline_source"] = {
            "hr": hr_inv.get("deadline_source", "drive" if hr_inv.get("token") else None),
            "technical": tech_inv.get("deadline_source", "drive" if tech_inv.get("token") else None),
        }
        row["per_candidate_expires_at"] = {
            "hr": hr_inv.get("expires_at") if hr_inv.get("deadline_source") == "per_candidate" else None,
            "technical": tech_inv.get("expires_at") if tech_inv.get("deadline_source") == "per_candidate" else None,
        }
        row["recording"] = (doc.get("technical_interview") or {}).get("recording") or (doc.get("hr_interview") or {}).get("recording")
        rows.append(row)

    metrics = compute_drive_metrics(
        candidate_resumes, company_id or "", effective_job_id or "", current_job
    )
    metrics.pop("candidate_count", None)

    drives = []
    if company_id:
        for d in database.list_jobs(company_id):
            jid = d["job_id"]
            pending_req = database.get_jd_request(company_id, jid)
            is_pending = bool(pending_req and pending_req.get("status") == "pending")
            drives.append({
                "job_id": jid,
                "title": d.get("title", ""),
                "department": d.get("department", ""),
                "status": d.get("status", "active"),
                "candidate_count": database.count_candidates(company_id, job_id=jid),
                "has_pending_request": is_pending,
                "pending_request_type": pending_req.get("target_status") if is_pending else None,
            })

    company_info = {"name": "AI Hiring Platform", "plan": "starter", "role": "user"}
    if user:
        company_info["role"] = user.get("role", "user")
        if user.get("company_id"):
            cid = str(user["company_id"])
            company = database.get_company_by_id(cid)
            if company:
                company_info["name"] = company.get("name", "Unknown")
                company_info["plan"] = company.get("plan", "starter")
                company_info["max_users"] = company.get("max_users")
                company_info["max_candidates"] = company.get("max_candidates") or database.get_plan_limits(company.get("plan", "starter"))["max_candidates"]
                company_info["current_users"] = database.count_company_users(cid)
                company_info["credits"] = database.get_company_credits(cid)
                prices = database.get_plan_prices()
                company_info["plan_price"] = prices.get(company.get("plan", "starter"))

    return {
        "company": company_info,
        "job": asdict(stored_job) if stored_job else None,
        "job_id": effective_job_id,
        "drives": drives,
        "metrics": metrics,
        "jd_requests": _jd_requests_for_user(company_id, user),
        "screening": {
            "provider": "AI-powered",
            "message": "AI screening fallback is active." if ranking_service.last_error else "",
        },
        "deadlines": {
            "hr": hr_deadline,
            "technical": technical_deadline,
            "hr_passed": hr_deadline_passed,
            "technical_passed": technical_deadline_passed,
        },
        "candidates": rows,
    }


def _jd_requests_for_user(company_id: str | None, user: dict | None) -> list[dict]:
    """Return JD change requests relevant to the current user.

    Admins see all pending+resolved requests for the company so they can act.
    Sub-users see only the requests they submitted.
    """
    if not company_id or not user:
        return []
    if user.get("role") in ("super_admin", "company_admin"):
        requests = database.list_jd_requests(company_id)
    else:
        requests = [
            r for r in database.list_jd_requests(company_id)
            if r.get("requested_by_email") == user.get("email")
        ]
    cleaned = []
    for r in requests:
        c = _clean_mongo(r)
        if c.get("target_status") in ("edit", "delete") and c.get("job_id"):
            current_doc = database.get_job_doc(company_id, c["job_id"])
            if current_doc:
                c["current"] = _clean_mongo({k: v for k, v in current_doc.items() if k != "_id"})
        cleaned.append(c)
    return sorted(
        cleaned,
        key=lambda r: r.get("requested_at") or "",
        reverse=True,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clean_mongo(val):
    """Recursively convert Mongo ObjectId / datetime to JSON-serializable values."""
    if isinstance(val, dict):
        return {k: _clean_mongo(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean_mongo(item) for item in val]
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if type(val).__name__ == "ObjectId":
        return str(val)
    return val


def _sanitized_questions(custom_questions: list[dict]) -> list[dict]:
    """Candidate-safe view of the custom question bank (no expected points)."""
    result = []
    for index, item in enumerate(custom_questions, start=1):
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        result.append(
            {
                "id": f"q{index}",
                "question": question,
                "topic": str(item.get("topic", "General")).strip() or "General",
                "difficulty": str(item.get("difficulty", "medium")).strip() or "medium",
            }
        )
    return result


def _run_interview_evaluation(
    email: str, resume: ParsedResume, interview_type: str, transcript: list[dict],
    current_job: JobDescription | None = None, company_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Score an interview transcript and persist the result + pipeline stage."""
    job = current_job or DEFAULT_JOB
    round_type = "technical" if interview_type == "technical" else "hr"
    minutes = (
        job.technical_interview_duration
        if interview_type == "technical"
        else job.hr_interview_duration
    )

    # ── BUG 37: Idempotency guard — if the interview was already evaluated,
    # return the existing result so credits are never consumed twice. ──────────
    interview_field = "technical_interview" if interview_type == "technical" else "hr_interview"
    existing_doc = database.get_candidate_doc(email, company_id, job_id) or {}
    existing_interview = existing_doc.get(interview_field) or {}
    if existing_interview.get("status") == "completed":
        existing_eval = existing_interview.get("evaluation") or {}
        return {"email": email, "interview_type": interview_type, **existing_eval}

    if company_id:
        consume_result = database.consume_credits(str(company_id), minutes)
        credits_bucket = database.get_company_credits(str(company_id))
        if not consume_result.get("ok"):
            database.log_usage(
                email, str(company_id),
                minutes=minutes, round_type=round_type, action="blocked",
                detail=f"Required {minutes} credits, had {consume_result.get('remaining', 0)}",
            )
            log_activity(
                action="credits.insufficient",
                category="credits",
                actor={"_id": "system", "email": "system", "role": "system", "company_id": company_id},
                target_type="company",
                target_id=str(company_id),
                target_label=email,
                metadata={"required": minutes, "remaining": consume_result.get("remaining", 0)},
                severity="critical",
            )
            return {
                "blocked": True,
                "credits": credits_bucket,
                "required": minutes,
                "message": (
                    f"Insufficient interview credits. This {round_type} round requires "
                    f"{minutes} credits but only {consume_result.get('remaining', 0)} remain."
                ),
            }

    if interview_type == "technical":
        result = technical_evaluator.evaluate(resume.raw_text, transcript)
        result.setdefault("provider_used", "gemini" if technical_evaluator.api_key else "local")
        if technical_evaluator.last_error:
            result["provider_error"] = technical_evaluator.last_error
    else:
        result = hr_evaluator.evaluate(resume.raw_text, transcript)
        result.setdefault("provider_used", "gemini" if hr_evaluator.api_key else "local")
        if hr_evaluator.last_error:
            result["provider_error"] = hr_evaluator.last_error

    # Preserve existing recording metadata if the interview doc already has one
    existing_doc = database.get_candidate_doc(email, company_id, job_id) or {}
    existing_interview = existing_doc.get(
        "technical_interview" if interview_type == "technical" else "hr_interview"
    ) or {}
    recording = existing_interview.get("recording")

    interview = {
        "status": "completed",
        "type": interview_type,
        "decision": str(result.get("decision", "FAIL")).upper(),
        "score": result.get("final_round_score", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": result,
    }
    if recording:
        interview["recording"] = recording

    if interview_type == "technical":
        database.set_candidate_technical_interview(email, interview, company_id, job_id)
    else:
        database.set_candidate_hr_interview(email, interview, company_id, job_id)

    if company_id:
        database.log_usage(
            email, str(company_id),
            minutes=minutes, round_type=round_type, action="consume",
            detail=f"{round_type} interview evaluation",
        )
        log_activity(
            action="credits.consumed",
            category="credits",
            actor={"_id": "system", "email": "system", "role": "system", "company_id": company_id},
            target_type="company",
            target_id=str(company_id),
            target_label=email,
            metadata={"minutes": minutes, "round_type": round_type},
        )

    return {"email": email, "interview_type": interview_type, **result}


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise_deadline(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    parsed = _parse_deadline(value)
    if not parsed:
        raise HTTPException(status_code=400, detail="Deadline must be a valid ISO 8601 datetime.")
    # BUG 32: reject deadlines that are already in the past.
    if parsed <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Deadline cannot be in the past. Please choose a future date and time.",
        )
    return parsed.isoformat()


def _deadline_has_passed(value: str | None) -> bool:
    parsed = _parse_deadline(value)
    return bool(parsed and parsed <= datetime.now(timezone.utc))


def _deadline_is_active(value: str | None) -> bool:
    parsed = _parse_deadline(value)
    return bool(parsed and parsed > datetime.now(timezone.utc))


def _invitation_for_token(token: str, candidate_doc: dict) -> dict | None:
    for field in ("invitation", "hr_invitation"):
        invitation = candidate_doc.get(field) or {}
        if invitation.get("token") == token:
            return invitation
    return None


def _ensure_invitation_active(token: str, candidate_doc: dict) -> dict:
    invitation = _invitation_for_token(token, candidate_doc)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    if _deadline_has_passed(invitation.get("expires_at")):
        raise HTTPException(
            status_code=410,
            detail="This interview invitation has expired. Please contact the hiring team.",
        )
    return invitation


def _auto_fail_missed_deadlines(company_id: str | None, job_id: str | None, job_doc: dict) -> None:
    if not company_id or not job_id:
        return
    for resume in database.load_candidates(company_id, job_id=job_id):
        doc = database.get_candidate_doc(resume.email, company_id, job_id) or {}
        for interview_type, invitation_key, interview_key in (
            ("hr", "hr_invitation", "hr_interview"),
            ("technical", "invitation", "technical_interview"),
        ):
            invitation = doc.get(invitation_key) or {}
            interview = doc.get(interview_key) or {}
            if invitation.get("token") and interview.get("status") != "completed" and _deadline_has_passed(invitation.get("expires_at")):
                failed = {
                    "status": "completed",
                    "type": interview_type,
                    "decision": "FAIL",
                    "score": 0,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "auto_failed": True,
                    "reason": "Interview deadline passed before completion.",
                }
                if interview_type == "hr":
                    database.set_candidate_hr_interview(resume.email, failed, company_id, job_id)
                else:
                    database.set_candidate_technical_interview(resume.email, failed, company_id, job_id)


def _candidate_ref_for_token(token: str) -> tuple[str | None, str | None]:
    """Resolve (email, company_id) from a globally-unique interview token.

    Public interview endpoints have no authenticated user, so the token is the
    only tenant signal. Returning company_id lets callers scope every candidate
    read/write to the owning company.
    """
    if not token:
        return None, None
    doc = database._candidates.find_one(
        {"$or": [{"invitation.token": token}, {"hr_invitation.token": token}]},
        {"email": 1, "company_id": 1},
    )
    if not doc:
        return None, None
    return doc.get("email"), doc.get("company_id")


def _email_for_token(token: str) -> str | None:
    """Find candidate email by interview token (email-only convenience wrapper)."""
    email, _ = _candidate_ref_for_token(token)
    return email


def _parse_uploaded_bytes(file_name: str, contents: bytes) -> ParsedResume:
    suffix = Path(file_name).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{suffix or 'unknown'}'. Allowed formats: PDF, DOCX, TXT, PNG, JPG, JPEG.",
        )
    stream = BytesIO(contents)
    stream.name = file_name

    if suffix in {".docx", ".pdf", ".png", ".jpg", ".jpeg"}:
        return parse_uploaded_resume_with_ai(stream, raw_bytes=contents)
    return parse_resume_text_with_ai(file_name, contents.decode("utf-8", errors="ignore"))


def _enforce_candidate_limit(company_id: str | None) -> None:
    """Enforce company-wide total candidate limit based on company plan."""
    if not company_id:
        return
    count = database.count_company_candidates(company_id)
    company = database.get_company_by_id(company_id) or {}
    plan = company.get("plan", "starter")
    max_candidates = company.get("max_candidates")
    if max_candidates is None:
        max_candidates = database.get_plan_limits(plan).get("max_candidates", 100)
    if count >= max_candidates:
        raise HTTPException(
            status_code=403,
            detail=f"Candidate limit reached ({count}/{max_candidates}). Upgrade your plan to add more candidates.",
        )


# ── Resume upload batch status ──────────────────────────────────────────────

@app.get("/api/resumes/upload/active")
def active_resume_batches(
    user: dict = Depends(require_permission("manage_resumes")),
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    if not company_id:
        return {"batches": []}
    batches = database.get_active_resume_batches(company_id)
    return {"batches": [_clean_mongo(b) for b in batches]}


@app.get("/api/resumes/upload/{batch_id}")
def resume_batch_status(
    batch_id: str,
    user: dict = Depends(require_permission("manage_resumes")),
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    jobs = database.get_resume_jobs_by_batch(batch_id, company_id)
    if not jobs:
        raise HTTPException(status_code=404, detail="Batch not found")
    cleaned = [_clean_mongo(j) for j in jobs]
    statuses = [j["status"] for j in cleaned]
    if all(s in ("done", "failed") for s in statuses):
        batch_status = "complete"
    elif any(s == "processing" for s in statuses):
        batch_status = "processing"
    else:
        batch_status = "queued"
    return {
        "batchId": batch_id,
        "status": batch_status,
        "total": len(cleaned),
        "done": sum(1 for s in statuses if s == "done"),
        "failed": sum(1 for s in statuses if s == "failed"),
        "jobs": cleaned,
    }


# ── Static frontend hosting (production) ────────────────────────────────────

_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"
_ASSETS_DIR = _DIST_DIR / "assets"

if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        """Serve the built React SPA for any non-API, non-socket route."""
        if full_path.split("/")[0] in {"api", "ws", "assets", "docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404)
        index_file = _DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse(content="Frontend not built. Run `npm run build` in frontend/ and redeploy.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
