import json
import os
import secrets
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.src.ai_ranker import AIRankingService
from backend.src import database
from backend.src.interview_agent import InterviewAgent
from backend.src.models import JobDescription, ParsedResume
from backend.src.resume_parser import parse_resume_text, parse_uploaded_resume
from backend.src.sample_data import DEFAULT_JOB, SAMPLE_RESUMES
from backend.src.storage import score_candidates

from backend.technical_interview.evaluator import TechnicalInterviewEvaluator
from backend.technical_interview.interviewer import generate_interviewer_turn, get_interviewer_prompt


app = FastAPI(title="AI Hiring Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ranking_service = AIRankingService()
interview_agent = InterviewAgent()
technical_evaluator = TechnicalInterviewEvaluator()
current_job = database.load_job() or DEFAULT_JOB
candidate_resumes: list[ParsedResume] = database.load_candidates()


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


class ManualResumePayload(BaseModel):
    file_name: str = "manual_resume.txt"
    text: str


class EvaluationPayload(BaseModel):
    token: str
    transcript: list[dict[str, str]] = Field(default_factory=list)
    interview_type: str = "hr"


class ChatPayload(BaseModel):
    token: str
    transcript: list[dict[str, str]] = Field(default_factory=list)
    user_message: str = ""
    interview_type: str = "technical"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspace")
def workspace() -> dict[str, Any]:
    return _workspace_payload()


@app.put("/api/job")
def update_job(payload: JobPayload) -> dict[str, Any]:
    global current_job
    current_job = JobDescription(**payload.model_dump())
    database.save_job(current_job)
    return _workspace_payload()


@app.post("/api/resumes/manual")
def add_manual_resume(payload: ManualResumePayload) -> dict[str, Any]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Resume text is required.")
    resume = parse_resume_text(payload.file_name, payload.text)
    candidate_resumes.append(resume)
    database.upsert_candidate(resume)
    return _workspace_payload()


@app.post("/api/resumes/upload")
async def upload_resumes(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    for file in files:
        resume = _parse_uploaded_bytes(file.filename or "resume.txt", await file.read())
        candidate_resumes.append(resume)
        database.upsert_candidate(resume)
    return _workspace_payload()


@app.post("/api/resumes/sample")
def load_sample_resumes() -> dict[str, Any]:
    candidate_resumes.clear()
    database.clear_candidates()
    for index, text in enumerate(SAMPLE_RESUMES):
        resume = parse_resume_text(f"sample_resume_{index + 1}.txt", text)
        candidate_resumes.append(resume)
        database.upsert_candidate(resume)
    return _workspace_payload()


@app.delete("/api/resumes")
def clear_resumes() -> dict[str, Any]:
    candidate_resumes.clear()
    database.clear_candidates()
    return _workspace_payload()


# ── Invitation ──────────────────────────────────────────────────────────────

@app.post("/api/candidates/{email}/invite")
def invite_candidate(email: str, interview_type: str = "technical") -> dict[str, Any]:
    """Generate an interview invitation link. interview_type can be 'technical' or 'hr'."""
    if not any(c.email == email for c in candidate_resumes):
        raise HTTPException(status_code=404, detail="Candidate not found.")
    token = secrets.token_urlsafe(12)
    invitation = {
        "token": token,
        "type": interview_type,
        "link": f"http://127.0.0.1:5173/?interview={token}&type={interview_type}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Store under the right invitation key
    if interview_type == "hr":
        database.set_candidate_hr_invitation(email, invitation)
    else:
        database.set_candidate_invitation(email, invitation)
    return _workspace_payload()


# ── Interview Session ───────────────────────────────────────────────────────

@app.get("/api/interview/session/{token}")
def interview_session(token: str) -> dict[str, Any]:
    email = _email_for_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    resume = next((c for c in candidate_resumes if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    doc = database.get_candidate_doc(email) or {}

    # Determine interview type from the invitation
    invitation = doc.get("invitation") or {}
    hr_invitation = doc.get("hr_invitation") or {}
    if invitation.get("token") == token:
        interview_type = invitation.get("type", "technical")
        interview_data = doc.get("technical_interview") or {}
    elif hr_invitation.get("token") == token:
        interview_type = "hr"
        interview_data = doc.get("hr_interview") or doc.get("interview") or {}
    else:
        interview_type = "technical"
        interview_data = {}

    # Build appropriate system prompt
    system_prompt = get_interviewer_prompt(interview_type, current_job, resume)

    return {
        "token": token,
        "candidateName": resume.full_name,
        "jobTitle": current_job.title,
        "companyName": "Acme Talent Labs",
        "resumeText": resume.raw_text,
        "interviewType": interview_type,
        "systemPrompt": system_prompt,
        "completed": interview_data.get("status") == "completed",
        "decision": interview_data.get("decision"),
        "score": interview_data.get("score"),
    }


# ── Chat Turn Endpoint ──────────────────────────────────────────────────────

@app.post("/api/interview/chat")
def interview_chat(payload: ChatPayload) -> dict[str, Any]:
    email = _email_for_token(payload.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    resume = next((c for c in candidate_resumes if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    interview_type = payload.interview_type
    system_prompt = get_interviewer_prompt(interview_type, current_job, resume)

    content = generate_interviewer_turn(system_prompt, payload.transcript, payload.user_message)
    return {"role": "interviewer", "content": content}


# ── Evaluation ──────────────────────────────────────────────────────────────

@app.post("/api/interview/evaluate")
def evaluate_interview(payload: EvaluationPayload) -> dict[str, Any]:
    email = _email_for_token(payload.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    resume = next((c for c in candidate_resumes if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    interview_type = payload.interview_type

    # Use appropriate evaluator
    if interview_type == "technical":
        result = technical_evaluator.evaluate(resume.raw_text, payload.transcript)
        result.setdefault("provider_used", "gemini" if technical_evaluator.api_key else "local")
        if technical_evaluator.last_error:
            result["provider_error"] = technical_evaluator.last_error
    else:
        result = interview_agent.evaluate_interview(resume.raw_text, payload.transcript)
        result.setdefault("provider_used", "gemini" if interview_agent.api_key else "local")
        if interview_agent.last_error:
            result["provider_error"] = interview_agent.last_error

    interview = {
        "status": "completed",
        "type": interview_type,
        "decision": result.get("decision", "FAIL"),
        "score": result.get("final_round_score", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": result,
    }

    # Store in the right field
    if interview_type == "technical":
        database.set_candidate_technical_interview(email, interview)
    else:
        database.set_candidate_hr_interview(email, interview)

    return {"email": email, "interview_type": interview_type, **result}


# ── Workspace Payload ───────────────────────────────────────────────────────

def _workspace_payload() -> dict[str, Any]:
    results = score_candidates(candidate_resumes, current_job, ranking_service)
    rows = []
    invited = 0
    tech_interviewed = 0
    tech_passed = 0
    hr_interviewed = 0
    hired = 0

    for result in results:
        row = result.to_row()
        row["fileName"] = result.candidate.file_name
        row["linkedin"] = result.candidate.linkedin
        row["github"] = result.candidate.github
        row["breakdown"] = result.score.breakdown
        row["uploadedAt"] = result.candidate.uploaded_at.isoformat()
        doc = database.get_candidate_doc(result.candidate.email) or {}
        row["pipelineStage"] = doc.get("pipelineStage", "uploaded")
        row["invitation"] = doc.get("invitation")
        row["hr_invitation"] = doc.get("hr_invitation")
        row["interview"] = doc.get("interview")
        row["technical_interview"] = doc.get("technical_interview")
        row["hr_interview"] = doc.get("hr_interview")

        stage = row["pipelineStage"]
        if stage in {"invited", "tech_passed", "tech_failed", "hr_failed", "hired"}:
            invited += 1
        if stage in {"tech_passed", "tech_failed", "hr_failed", "hired"}:
            tech_interviewed += 1
        if stage in {"tech_passed", "hr_failed", "hired"}:
            tech_passed += 1
        if stage in {"hr_failed", "hired"}:
            hr_interviewed += 1
        if stage == "hired":
            hired += 1

        rows.append(row)

    shortlisted = len([result for result in results if result.status == "Shortlisted"])
    rejected = len([result for result in results if result.status == "Rejected"])
    average = round(sum(result.score.total_score for result in results) / len(results)) if results else 0

    return {
        "company": {
            "name": "Acme Talent Labs",
            "plan": "Growth",
            "role": "Company Admin",
        },
        "job": asdict(current_job),
        "metrics": {
            "uploaded": len(candidate_resumes),
            "shortlisted": shortlisted,
            "rejected": rejected,
            "averageScore": average,
            "invited": invited,
            "techInterviewed": tech_interviewed,
            "techPassed": tech_passed,
            "hrInterviewed": hr_interviewed,
            "hired": hired,
        },
        "screening": {
            "provider": ranking_service.last_provider_used,
            "model": ranking_service.model,
            "message": ranking_service.last_error,
        },
        "candidates": rows,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _email_for_token(token: str) -> str | None:
    if not token:
        return None
    for email in _candidate_emails():
        doc = database.get_candidate_doc(email) or {}
        # Check both technical invitation and HR invitation
        invitation = doc.get("invitation") or {}
        hr_invitation = doc.get("hr_invitation") or {}
        if invitation.get("token") == token or hr_invitation.get("token") == token:
            return email
    return None


def _candidate_emails() -> list[str]:
    return [c.email for c in candidate_resumes]


def _parse_uploaded_bytes(file_name: str, contents: bytes) -> ParsedResume:
    suffix = Path(file_name).suffix.lower()
    stream = BytesIO(contents)
    stream.name = file_name

    if suffix in {".txt", ".docx", ".pdf"}:
        return parse_uploaded_resume(stream)
    return parse_resume_text(file_name, contents.decode("utf-8", errors="ignore"))
