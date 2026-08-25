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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, Depends
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
from backend.services.ranking import score_candidates
from backend.services.resume_parser import parse_resume_text, parse_uploaded_resume
from backend.services.Technical.technical_evaluator import TechnicalInterviewEvaluator
from backend.services import r2_storage
from backend.storage import database
from backend.auth.security import (
    get_current_user,
    hash_password,
    log_activity,
    require_authenticated,
    require_company_admin,
)
from backend.auth.routes import router as auth_router
from backend.admin.routes import admin_router, company_router


app = FastAPI(title="AI Hiring Platform API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register auth & admin routers ───────────────────────────────────────────
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(company_router)

# ── Shared services (stateless, safe to share) ─────────────────────────────
ranking_service = AIRankingService()
hr_evaluator = HREvaluator()
technical_evaluator = TechnicalInterviewEvaluator()
question_processor = QuestionProcessor()


# ── Startup: seed Super Admin ──────────────────────────────────────────────

@app.on_event("startup")
def seed_super_admin():
    """Create the initial Super Admin from .env if none exists."""
    if database.count_super_admins() > 0:
        return  # Already seeded

    email = os.getenv("SUPER_ADMIN_EMAIL", "admin@aihiring.com")
    password = os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123456")

    if database.get_user_by_email(email):
        return  # Email already taken

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

    # Log the seeding event
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
    custom_questions: list[dict] = Field(default_factory=list)


class ManualResumePayload(BaseModel):
    file_name: str = "manual_resume.txt"
    text: str


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
def workspace(user: dict = Depends(require_authenticated)) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    return _workspace_payload(company_id, user)


@app.put("/api/job")
def update_job(
    payload: JobPayload,
    user: dict = Depends(require_company_admin),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    job = JobDescription(**payload.model_dump())
    database.save_job(job, company_id)
    log_activity(
        action="job.updated",
        category="job",
        actor=user,
        target_type="job",
        target_label=job.title,
        request=request,
    )
    return _workspace_payload(company_id, user)


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
    user: dict = Depends(require_authenticated),
    request: Request = None,
) -> dict[str, Any]:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Resume text is required.")
    company_id = str(user["company_id"]) if user.get("company_id") else None
    resume = parse_resume_text(payload.file_name, payload.text)
    database.upsert_candidate(resume, company_id=company_id)
    log_activity(
        action="candidate.uploaded",
        category="candidate",
        actor=user,
        target_type="candidate",
        target_label=f"{resume.full_name} ({resume.email})",
        request=request,
    )
    return _workspace_payload(company_id, user)


@app.post("/api/resumes/upload")
async def upload_resumes(
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_authenticated),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    file_names = []
    for file in files:
        resume = _parse_uploaded_bytes(file.filename or "resume.txt", await file.read())
        database.upsert_candidate(resume, company_id=company_id)
        file_names.append(file.filename)
    log_activity(
        action="candidate.bulk_uploaded",
        category="candidate",
        actor=user,
        metadata={"count": len(files), "file_names": file_names},
        request=request,
    )
    return _workspace_payload(company_id, user)


@app.post("/api/resumes/sample")
def load_sample_resumes(
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    database.clear_candidates(company_id)
    for index, text in enumerate(SAMPLE_RESUMES):
        resume = parse_resume_text(f"sample_resume_{index + 1}.txt", text)
        database.upsert_candidate(resume, company_id=company_id)
    return _workspace_payload(company_id, user)


@app.delete("/api/resumes")
def clear_resumes(
    user: dict = Depends(require_company_admin),
    request: Request = None,
) -> dict[str, Any]:
    company_id = str(user["company_id"]) if user.get("company_id") else None
    database.clear_candidates(company_id)
    log_activity(
        action="candidate.all_cleared",
        category="candidate",
        actor=user,
        severity="critical",
        request=request,
    )
    return _workspace_payload(company_id, user)


# ── Invitation ──────────────────────────────────────────────────────────────

@app.post("/api/candidates/{email}/invite")
def invite_candidate(
    email: str,
    interview_type: str = "technical",
    user: dict = Depends(require_authenticated),
    request: Request = None,
) -> dict[str, Any]:
    """Generate an interview invitation link. interview_type can be 'technical' or 'hr'."""
    company_id = str(user["company_id"]) if user.get("company_id") else None
    candidates = database.load_candidates(company_id)
    if not any(c.email == email for c in candidates):
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
    return _workspace_payload(company_id, user)


# ── Interview Session (token-based, no login required) ─────────────────────

@app.get("/api/interview/session/{token}")
def interview_session(token: str) -> dict[str, Any]:
    """Public endpoint — candidates access via invitation token, no auth needed."""
    email = _email_for_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")

    candidate_doc = database.get_candidate_doc(email)
    if not candidate_doc:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Load resume from DB
    candidates = database.load_candidates(candidate_doc.get("company_id"))
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    # Load company job
    company_id = candidate_doc.get("company_id")
    current_job = database.load_job(company_id) or DEFAULT_JOB

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
    email = _email_for_token(payload.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    candidate_doc = database.get_candidate_doc(email)
    company_id = candidate_doc.get("company_id") if candidate_doc else None
    candidates = database.load_candidates(company_id)
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    current_job = database.load_job(company_id) or DEFAULT_JOB
    return _run_interview_evaluation(email, resume, payload.interview_type, payload.transcript, current_job)


# ── Recording Upload & Playback ────────────────────────────────────────────

@app.post("/api/interview/recording/upload")
async def upload_recording(
    token: str = Form(...),
    interview_type: str = Form("technical"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Receive the browser-recorded WebM, persist to R2 + temp_files."""
    email = _email_for_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty recording file.")

    recording_meta = await asyncio.to_thread(
        r2_storage.upload_recording, email, interview_type, file_bytes
    )
    database.set_candidate_interview_recording(email, interview_type, recording_meta)
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
    user: dict = Depends(require_authenticated),
) -> dict[str, Any]:
    """Return a presigned URL (or local path) so HR can play the recording."""
    doc = database.get_candidate_doc(email)
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

    email = _email_for_token(token)
    if not email:
        await websocket.send_json({"type": "error", "message": "Invitation not found or invalid."})
        await websocket.close()
        return

    candidate_doc = database.get_candidate_doc(email)
    company_id = candidate_doc.get("company_id") if candidate_doc else None
    candidates = database.load_candidates(company_id)
    resume = next((c for c in candidates if c.email == email), None)
    if not resume:
        await websocket.send_json({"type": "error", "message": "Candidate not found."})
        await websocket.close()
        return

    current_job = database.load_job(company_id) or DEFAULT_JOB
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
            database.append_transcript_turn(email, "candidate", text)
        user_buffer.clear()

    def flush_model_turn() -> None:
        text = " ".join(model_buffer).strip()
        if text:
            transcript.append({"role": "interviewer", "content": text})
            database.append_transcript_turn(email, "interviewer", text)
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
                        _run_interview_evaluation, email, resume, interview_type, list(transcript), current_job
                    )
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

def _workspace_payload(company_id: str | None = None, user: dict | None = None) -> dict[str, Any]:
    current_job = database.load_job(company_id) or DEFAULT_JOB
    candidate_resumes = database.load_candidates(company_id)
    results = score_candidates(candidate_resumes, current_job, ranking_service)
    rows = []
    hr_invited = 0
    hr_interviewed = 0
    hr_passed = 0
    tech_invited = 0
    tech_interviewed = 0
    tech_passed = 0
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
        row["interview_transcript"] = doc.get("interview_transcript") or []
        row["recording"] = (doc.get("technical_interview") or {}).get("recording") or (doc.get("hr_interview") or {}).get("recording")

        stage = row["pipelineStage"]
        # HR pipeline stages
        if stage in {"hr_invited", "hr_passed", "hr_failed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_invited += 1
        if stage in {"hr_passed", "hr_failed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_interviewed += 1
        if stage in {"hr_passed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_passed += 1
        # Technical pipeline stages (only after HR passed)
        if stage in {"invited", "tech_passed", "tech_failed", "hired"}:
            tech_invited += 1
        if stage in {"tech_passed", "tech_failed", "hired"}:
            tech_interviewed += 1
        if stage in {"tech_passed", "hired"}:
            tech_passed += 1
        if stage == "hired":
            hired += 1

        rows.append(row)

    shortlisted = len([result for result in results if result.status == "Shortlisted"])
    rejected = len([result for result in results if result.status == "Rejected"])
    average = round(sum(result.score.total_score for result in results) / len(results)) if results else 0

    # Build company info from user context
    company_info = {"name": "AI Hiring Platform", "plan": "starter", "role": "user"}
    if user:
        company_info["role"] = user.get("role", "user")
        if user.get("company_id"):
            company = database.get_company_by_id(str(user["company_id"]))
            if company:
                company_info["name"] = company.get("name", "Unknown")
                company_info["plan"] = company.get("plan", "starter")

    return {
        "company": company_info,
        "job": asdict(current_job),
        "metrics": {
            "uploaded": len(candidate_resumes),
            "shortlisted": shortlisted,
            "rejected": rejected,
            "averageScore": average,
            "hrInvited": hr_invited,
            "hrInterviewed": hr_interviewed,
            "hrPassed": hr_passed,
            "techInvited": tech_invited,
            "techInterviewed": tech_interviewed,
            "techPassed": tech_passed,
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
    current_job: JobDescription | None = None,
) -> dict[str, Any]:
    """Score an interview transcript and persist the result + pipeline stage."""
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
    existing_doc = database.get_candidate_doc(email) or {}
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
        database.set_candidate_technical_interview(email, interview)
    else:
        database.set_candidate_hr_interview(email, interview)

    return {"email": email, "interview_type": interview_type, **result}


def _email_for_token(token: str) -> str | None:
    """Find candidate email by interview token. Searches all candidates."""
    if not token:
        return None
    # Search across all candidates (token is globally unique)
    for doc in database._candidates.find(
        {"$or": [{"invitation.token": token}, {"hr_invitation.token": token}]},
        {"email": 1},
    ):
        return doc.get("email")
    return None


def _parse_uploaded_bytes(file_name: str, contents: bytes) -> ParsedResume:
    suffix = Path(file_name).suffix.lower()
    stream = BytesIO(contents)
    stream.name = file_name

    if suffix in {".txt", ".docx", ".pdf"}:
        return parse_uploaded_resume(stream)
    return parse_resume_text(file_name, contents.decode("utf-8", errors="ignore"))
