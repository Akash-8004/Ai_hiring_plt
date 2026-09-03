import array
import asyncio
import base64
import json
import math
import os
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.core.models import JobDescription, ParsedResume
from backend.core.sample_data import DEFAULT_JOB, SAMPLE_RESUMES
from backend.live.relay import GeminiLiveRelay
from backend.services.ai_ranker import AIRankingService
from backend.services.HR_Round.hr_evaluator import HREvaluator
from backend.services.Technical.interviewer import get_interviewer_prompt
from backend.services.Technical.question_processor import QuestionProcessor
from backend.services.drive_metrics import compute_drive_metrics, score_candidates_for_drive
from backend.services.resume_parser import parse_resume_text, parse_uploaded_resume
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


app = FastAPI(title="AI Hiring Platform API", version="0.2.0")

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


# ── Startup: seed Super Admin ──────────────────────────────────────────────

@app.on_event("startup")
def seed_super_admin():
    """Create the initial Super Admin from .env if none exists."""
    if database.count_super_admins() == 0:
        email = os.getenv("SUPER_ADMIN_EMAIL", "admin@aihiring.com")
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


# ── Pydantic Models ────────────────────────────────────────────────────────

class JobPayload(BaseModel):
    title: str
    department: str
    location: str
    experience_years: int = Field(ge=0, le=30)
    required_skills: list[str]
    nice_to_have_skills: list[str] = []
    education: str
    description: str
    threshold: int = Field(ge=40, le=100)
    hr_interview_duration: int = Field(default=7, ge=3, le=60)
    technical_interview_duration: int = Field(default=5, ge=3, le=60)
    custom_questions: list[dict] = Field(default_factory=list)
    job_id: str | None = None


class ManualResumePayload(BaseModel):
    file_name: str = "manual_resume.txt"
    text: str


class RejectJdPayload(BaseModel):
    note: str = ""


class ProcessQuestionsPayload(BaseModel):
    text: str = ""


class EvaluationPayload(BaseModel):
    token: str
    transcript: list[dict[str, str]] = Field(default_factory=list)
    interview_type: str = "hr"


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
    else:
        if not database.get_job_by_id(company_id, effective_job_id):
            raise HTTPException(status_code=404, detail="Drive not found")
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
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    """List JD change requests for the caller's company.

    Company admins see all requests; sub-users see only the requests they
    submitted (so they can track their own pending proposals).
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
    job = JobDescription(**proposed)

    if target_status == "create":
        stored = database.upsert_job(job, company_id, job_id=job_id)
        effective_job_id = stored["job_id"]
        database.set_active_drive(company_id, effective_job_id)
    else:
        if not database.get_job_by_id(company_id, job_id):
            raise HTTPException(status_code=404, detail="Drive not found")
        effective_job_id = job_id
        database.upsert_job(job, company_id, job_id=job_id)

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
    questions = await asyncio.to_thread(question_processor.process_file, file)
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
    questions = question_processor.process_text(payload.text)
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
    resume = parse_resume_text(payload.file_name, payload.text)
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


@app.post("/api/resumes/upload")
async def upload_resumes(
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_permission("manage_resumes")),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first")
    file_names = []
    for file in files:
        resume = _parse_uploaded_bytes(file.filename or "resume.txt", await file.read())
        _enforce_candidate_limit(company_id)
        database.upsert_candidate(resume, company_id=company_id, job_id=job_id)
        file_names.append(file.filename)
    log_activity(
        action="candidate.bulk_uploaded",
        category="candidate",
        actor=user,
        metadata={"count": len(files), "file_names": file_names},
        request=request,
    )
    return _workspace_payload(company_id, user, job_id=job_id)


@app.post("/api/resumes/sample")
def load_sample_resumes(
    user: dict = Depends(require_permission("manage_resumes")),
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first")
    database.clear_candidates(company_id, job_id=job_id)
    for index, text in enumerate(SAMPLE_RESUMES):
        resume = parse_resume_text(f"sample_resume_{index + 1}.txt", text)
        _enforce_candidate_limit(company_id)
        database.upsert_candidate(resume, company_id=company_id, job_id=job_id)
    return _workspace_payload(company_id, user, job_id=job_id)


@app.delete("/api/resumes")
def clear_resumes(
    user: dict = Depends(require_company_admin),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job_id = _active_drive_id(company_id)
    if not job_id:
        raise HTTPException(status_code=400, detail="Create a job drive first")
    database.clear_candidates(company_id, job_id=job_id)
    log_activity(
        action="candidate.all_cleared",
        category="candidate",
        actor=user,
        severity="critical",
        request=request,
    )
    return _workspace_payload(company_id, user, job_id=job_id)


# ── Invitation ──────────────────────────────────────────────────────────────

@app.post("/api/candidates/{email}/invite")
def invite_candidate(
    email: str,
    interview_type: str = "technical",
    send_email: bool = False,
    user: dict = Depends(require_permission("conduct_interviews")),
    request: Request = None,
) -> dict[str, Any]:
    """Generate an interview invitation link. interview_type can be 'technical' or 'hr'."""
    company_id = str(user["company_id"]) if user.get("company_id") else None
    candidate_doc = database.get_candidate_doc(email, company_id)
    if not candidate_doc:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    job_id = candidate_doc.get("job_id")
    token = secrets.token_urlsafe(12)
    invitation = {
        "token": token,
        "type": interview_type,
        "link": f"http://127.0.0.1:5173/?interview={token}&type={interview_type}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Store under the right invitation key
    if interview_type == "hr":
        database.set_candidate_hr_invitation(email, invitation, company_id, job_id)
    else:
        database.set_candidate_invitation(email, invitation, company_id, job_id)
    log_activity(
        action=f"candidate.invited_{interview_type}",
        category="candidate",
        actor=user,
        target_type="candidate",
        target_id=email,
        target_label=email,
        metadata={"interview_type": interview_type},
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
                app_url = os.getenv("APP_URL", "http://localhost:5173")
                email_link = f"{app_url}/?interview={token}&type={interview_type}"
                subject, html_body, plain_body = interview_invite_email(
                    candidate_name, interview_type, email_link,
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

    system_prompt = get_interviewer_prompt(interview_type, current_job, resume)

    return {
        "token": token,
        "candidateName": resume.full_name,
        "jobTitle": current_job.title,
        "companyName": company_name,
        "resumeText": resume.raw_text,
        "interviewType": interview_type,
        "systemPrompt": system_prompt,
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
    current_job = drive or (database.load_job(company_id) if company_id else None) or DEFAULT_JOB
    candidate_resumes = (
        database.load_candidates(company_id, job_id=effective_job_id)
        if company_id
        else database.load_candidates()
    )
    results = score_candidates_for_drive(
        candidate_resumes, current_job, company_id or "", effective_job_id or ""
    )
    rows = []

    for result in results:
        row = result.to_row()
        row["fileName"] = result.candidate.file_name
        row["linkedin"] = result.candidate.linkedin
        row["github"] = result.candidate.github
        row["breakdown"] = result.score.breakdown
        row["uploadedAt"] = result.candidate.uploaded_at.isoformat()
        doc = database.get_candidate_doc(
            result.candidate.email, company_id, effective_job_id
        ) or {}
        row["pipelineStage"] = doc.get("pipelineStage", "uploaded")
        row["invitation"] = doc.get("invitation")
        row["hr_invitation"] = doc.get("hr_invitation")
        row["interview"] = doc.get("interview")
        row["technical_interview"] = doc.get("technical_interview")
        row["hr_interview"] = doc.get("hr_interview")
        row["interview_transcript"] = doc.get("interview_transcript") or []
        row["email_sent"] = doc.get("email_sent") or {}
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
                "candidate_count": len(database.load_candidates(company_id, job_id=jid)),
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
        "job": asdict(current_job),
        "job_id": effective_job_id,
        "drives": drives,
        "metrics": metrics,
        "jd_requests": _jd_requests_for_user(company_id, user),
        "screening": {
            "provider": ranking_service.last_provider_used,
            "model": ranking_service.model,
            "message": ranking_service.last_error,
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
    stream = BytesIO(contents)
    stream.name = file_name

    if suffix in {".txt", ".docx", ".pdf"}:
        return parse_uploaded_resume(stream)
    return parse_resume_text(file_name, contents.decode("utf-8", errors="ignore"))


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

