import array
import asyncio
import base64
import json
import math
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.core.models import JobDescription, ParsedResume
from backend.core.sample_data import DEFAULT_JOB, SAMPLE_RESUMES
from backend.live.relay import GeminiLiveRelay
from backend.services.ai_ranker import AIRankingService
from backend.services.interview_agent import InterviewAgent
from backend.services.Technical.interviewer import get_interviewer_prompt
from backend.services.Technical.question_processor import QuestionProcessor
from backend.services.ranking import score_candidates
from backend.services.resume_parser import parse_resume_text, parse_uploaded_resume
from backend.services.Technical.technical_evaluator import TechnicalInterviewEvaluator
from backend.storage import database


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
question_processor = QuestionProcessor()
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


@app.post("/api/job/questions/process")
async def process_questions_file(file: UploadFile = File(...)) -> dict[str, Any]:
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
def process_questions_text(payload: ProcessQuestionsPayload) -> dict[str, Any]:
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
    email = _email_for_token(payload.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invitation not found or invalid.")
    resume = next((c for c in candidate_resumes if c.email == email), None)
    if not resume:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return _run_interview_evaluation(email, resume, payload.interview_type, payload.transcript)


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
    resume = next((c for c in candidate_resumes if c.email == email), None) if email else None
    if not email or not resume:
        await websocket.send_json({"type": "error", "message": "Invitation not found or invalid."})
        await websocket.close()
        return

    doc = database.get_candidate_doc(email) or {}
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
                        _run_interview_evaluation, email, resume, interview_type, list(transcript)
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
        row["interview_transcript"] = doc.get("interview_transcript") or []

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
    email: str, resume: ParsedResume, interview_type: str, transcript: list[dict]
) -> dict[str, Any]:
    """Score an interview transcript and persist the result + pipeline stage."""
    if interview_type == "technical":
        result = technical_evaluator.evaluate(resume.raw_text, transcript)
        result.setdefault("provider_used", "gemini" if technical_evaluator.api_key else "local")
        if technical_evaluator.last_error:
            result["provider_error"] = technical_evaluator.last_error
    else:
        result = interview_agent.evaluate_interview(resume.raw_text, transcript)
        result.setdefault("provider_used", "gemini" if interview_agent.api_key else "local")
        if interview_agent.last_error:
            result["provider_error"] = interview_agent.last_error

    interview = {
        "status": "completed",
        "type": interview_type,
        "decision": str(result.get("decision", "FAIL")).upper(),
        "score": result.get("final_round_score", 0),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": result,
    }

    if interview_type == "technical":
        database.set_candidate_technical_interview(email, interview)
    else:
        database.set_candidate_hr_interview(email, interview)

    return {"email": email, "interview_type": interview_type, **result}


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
