import os
from datetime import datetime

from pymongo import MongoClient

from backend.config import load_env
from backend.core.models import JobDescription, ParsedResume


load_env()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)["ai_hiring"]
_candidates = _db["candidates"]
_jobs = _db["job"]

try:
    _candidates.create_index("email", unique=True)
except Exception:
    pass


def load_job() -> JobDescription | None:
    doc = _jobs.find_one({"_id": "current"})
    if not doc:
        return None
    doc.pop("_id", None)
    return JobDescription(**{k: v for k, v in doc.items() if k != "_id"})


def save_job(job: JobDescription) -> None:
    doc = {
        "title": job.title,
        "department": job.department,
        "location": job.location,
        "experience_years": job.experience_years,
        "required_skills": job.required_skills,
        "nice_to_have_skills": job.nice_to_have_skills,
        "education": job.education,
        "description": job.description,
        "threshold": job.threshold,
        "custom_questions": job.custom_questions,
    }
    _jobs.replace_one({"_id": "current"}, doc, upsert=True)


def load_candidates() -> list[ParsedResume]:
    resumes = []
    valid_fields = {
        "file_name",
        "full_name",
        "email",
        "phone",
        "skills",
        "experience_years",
        "education",
        "linkedin",
        "github",
        "raw_text",
        "uploaded_at",
    }
    for doc in _candidates.find():
        doc["uploaded_at"] = doc.get("uploaded_at") or datetime.utcnow()
        clean_doc = {k: v for k, v in doc.items() if k in valid_fields}
        if clean_doc.get("email"):
            resumes.append(ParsedResume(**clean_doc))
    return resumes


def _resume_to_dict(resume: ParsedResume) -> dict:
    return {
        "file_name": resume.file_name,
        "full_name": resume.full_name,
        "email": resume.email,
        "phone": resume.phone,
        "skills": resume.skills,
        "experience_years": resume.experience_years,
        "education": resume.education,
        "linkedin": resume.linkedin,
        "github": resume.github,
        "raw_text": resume.raw_text,
        "uploaded_at": resume.uploaded_at,
    }


def upsert_candidate(resume: ParsedResume, pipeline_stage: str = "uploaded") -> None:
    doc = _resume_to_dict(resume)
    doc["pipelineStage"] = pipeline_stage
    _candidates.replace_one({"email": resume.email}, doc, upsert=True)


def clear_candidates() -> None:
    _candidates.delete_many({})


def get_candidate_doc(email: str) -> dict | None:
    doc = _candidates.find_one({"email": email})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def set_candidate_invitation(email: str, invitation: dict) -> None:
    _candidates.update_one(
        {"email": email},
        {"$set": {"invitation": invitation, "pipelineStage": "invited"}},
    )


def set_candidate_hr_invitation(email: str, invitation: dict) -> None:
    _candidates.update_one(
        {"email": email},
        {"$set": {"hr_invitation": invitation}},
    )


def set_candidate_technical_interview(email: str, interview: dict) -> None:
    stage = "tech_passed" if interview.get("decision") == "PASS" else "tech_failed"
    _candidates.update_one(
        {"email": email},
        {"$set": {"technical_interview": interview, "pipelineStage": stage}},
    )


def set_candidate_hr_interview(email: str, interview: dict) -> None:
    stage = "hired" if interview.get("decision") == "PASS" else "hr_failed"
    _candidates.update_one(
        {"email": email},
        {"$set": {"hr_interview": interview, "pipelineStage": stage}},
    )


def append_transcript_turn(email: str, role: str, text: str, extra: dict | None = None) -> None:
    """Persist one interview turn as it happens so a closed tab never loses it.
    `extra` can carry metadata such as `type` ("written") or the `question`
    a typed answer was replying to."""
    content = (text or "").strip()
    if not content:
        return
    turn = {
        "role": role,
        "content": content,
        "at": datetime.utcnow().isoformat(),
    }
    if extra:
        turn.update(extra)
    _candidates.update_one(
        {"email": email},
        {"$push": {"interview_transcript": turn}},
    )
