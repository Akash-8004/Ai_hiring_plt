import os
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient

from backend.src.models import JobDescription, ParsedResume


def _load_dotenv() -> None:
    for parent_idx in (1, 2):
        env_path = Path(__file__).resolve().parents[parent_idx] / ".env"
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

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


def set_candidate_stage(email: str, stage: str) -> None:
    _candidates.update_one(
        {"email": email},
        {"$set": {"pipelineStage": stage, "updated_at": datetime.utcnow()}},
    )


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


def set_candidate_interview(email: str, interview: dict) -> None:
    _candidates.update_one(
        {"email": email},
        {"$set": {"interview": interview, "pipelineStage": "interviewed"}},
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
