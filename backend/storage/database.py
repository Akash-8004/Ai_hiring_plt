"""MongoDB persistence layer — candidates, jobs, users, companies, audit log.

All tenant-scoped functions accept a `company_id` parameter to enforce data
isolation between companies.
"""

import os
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import DESCENDING, MongoClient

from backend.config import load_env
from backend.core.models import JobDescription, ParsedResume

load_env()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)["ai_hiring"]

# ── Collections ─────────────────────────────────────────────────────────────
_candidates = _db["candidates"]
_jobs = _db["job"]
_users = _db["users"]
_companies = _db["companies"]
_audit_log = _db["audit_log"]

# ── Indexes ─────────────────────────────────────────────────────────────────
try:
    # Legacy builds put a GLOBAL unique index on candidate email, which breaks
    # multi-tenancy (two companies can't hold the same candidate). Drop it and
    # replace with a per-company compound unique index.
    try:
        _candidates.drop_index("email_1")
    except Exception:
        pass  # Index may not exist on fresh databases.
    _candidates.create_index([("company_id", 1), ("email", 1)], unique=True)
    _candidates.create_index("company_id")
    _users.create_index("email", unique=True)
    _companies.create_index("slug", unique=True)
    _audit_log.create_index([("timestamp", DESCENDING)])
    _audit_log.create_index([("company_id", 1), ("timestamp", DESCENDING)])
    _jobs.create_index("company_id")
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# USER CRUD
# ═══════════════════════════════════════════════════════════════════════════

def get_user_by_email(email: str) -> dict | None:
    return _users.find_one({"email": email})


def get_user_by_id(user_id: str) -> dict | None:
    try:
        return _users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def insert_user(doc: dict) -> str:
    """Insert a user document and return the string ID."""
    # Convert company_id string to ObjectId for storage if needed
    if doc.get("company_id") and not isinstance(doc["company_id"], ObjectId):
        doc["company_id"] = ObjectId(doc["company_id"])
    result = _users.insert_one(doc)
    return str(result.inserted_id)


def update_user_session(
    user_id: str,
    refresh_token: str | None,
    last_login: datetime | None = None,
) -> None:
    if last_login:
        _users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"active_session_token": refresh_token, "last_login": last_login},
             "$inc": {"login_count": 1}},
        )
    else:
        _users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"active_session_token": refresh_token}},
        )


def update_user_password(user_id: str, password_hash: str) -> None:
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": password_hash}},
    )


def update_user_status(user_id: str, status: str) -> None:
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"status": status}},
    )


def list_users_by_company(company_id: str) -> list[dict]:
    try:
        return list(_users.find({"company_id": ObjectId(company_id)}))
    except Exception:
        return []


def list_all_users() -> list[dict]:
    return list(_users.find())


def count_company_users(company_id: str) -> int:
    try:
        return _users.count_documents({"company_id": ObjectId(company_id)})
    except Exception:
        return 0


def count_super_admins() -> int:
    return _users.count_documents({"role": "super_admin"})


# ═══════════════════════════════════════════════════════════════════════════
# COMPANY CRUD
# ═══════════════════════════════════════════════════════════════════════════

def insert_company(doc: dict) -> str:
    result = _companies.insert_one(doc)
    return str(result.inserted_id)


def get_company_by_id(company_id: str) -> dict | None:
    try:
        return _companies.find_one({"_id": ObjectId(company_id)})
    except Exception:
        return None


def get_company_by_slug(slug: str) -> dict | None:
    return _companies.find_one({"slug": slug})


def list_companies() -> list[dict]:
    return list(_companies.find().sort("created_at", DESCENDING))


def update_company(company_id: str, updates: dict) -> None:
    _companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": updates},
    )


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

def insert_audit_log(entry: dict) -> None:
    try:
        _audit_log.insert_one(entry)
    except Exception:
        pass  # Audit logging should never crash the main flow


def query_audit_log(filters: dict, page: int = 1, limit: int = 50) -> dict:
    """Query audit log with filtering and pagination."""
    query: dict = {}

    if filters.get("company_id"):
        # Audit entries store company_id as an ObjectId (see log_activity), so a
        # raw string filter never matches. Coerce, falling back to the raw value.
        try:
            query["company_id"] = ObjectId(filters["company_id"])
        except Exception:
            query["company_id"] = filters["company_id"]
    if filters.get("actor_id"):
        query["actor_id"] = filters["actor_id"]
    if filters.get("category"):
        query["category"] = filters["category"]
    if filters.get("action"):
        query["action"] = filters["action"]
    if filters.get("severity"):
        query["severity"] = filters["severity"]

    # Date range
    if filters.get("from_date") or filters.get("to_date"):
        date_filter: dict = {}
        if filters.get("from_date"):
            date_filter["$gte"] = datetime.fromisoformat(filters["from_date"])
        if filters.get("to_date"):
            date_filter["$lte"] = datetime.fromisoformat(filters["to_date"])
        query["timestamp"] = date_filter

    # Full-text search across key fields
    if filters.get("search"):
        search = filters["search"]
        query["$or"] = [
            {"actor_email": {"$regex": search, "$options": "i"}},
            {"target_label": {"$regex": search, "$options": "i"}},
            {"action": {"$regex": search, "$options": "i"}},
        ]

    total = _audit_log.count_documents(query)
    skip = (page - 1) * limit
    logs = list(
        _audit_log.find(query)
        .sort("timestamp", DESCENDING)
        .skip(skip)
        .limit(limit)
    )

    def _clean(val):
        if isinstance(val, ObjectId):
            return str(val)
        if isinstance(val, datetime):
            return val.isoformat()
        if isinstance(val, dict):
            return {k: _clean(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_clean(item) for item in val]
        return val

    cleaned_logs = [_clean(log) for log in logs]
    return {"total": total, "page": page, "limit": limit, "logs": cleaned_logs}


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM STATS
# ═══════════════════════════════════════════════════════════════════════════

def get_platform_stats() -> dict:
    return {
        "total_companies": _companies.count_documents({}),
        "active_companies": _companies.count_documents({"status": "active"}),
        "suspended_companies": _companies.count_documents({"status": "suspended"}),
        "total_users": _users.count_documents({}),
        "total_candidates": _candidates.count_documents({}),
        "total_interviews": _candidates.count_documents({
            "$or": [
                {"technical_interview.status": "completed"},
                {"hr_interview.status": "completed"},
            ]
        }),
    }


# ═══════════════════════════════════════════════════════════════════════════
# JOB — tenant-scoped
# ═══════════════════════════════════════════════════════════════════════════

def load_job(company_id: str | None = None) -> JobDescription | None:
    """Load the current job for a company. Falls back to legacy lookup."""
    if company_id:
        doc = _jobs.find_one({"company_id": company_id})
    else:
        doc = _jobs.find_one({"_id": "current"})
    if not doc:
        return None
    doc.pop("_id", None)
    doc.pop("company_id", None)
    valid = {
        "title", "department", "location", "experience_years",
        "required_skills", "nice_to_have_skills", "education",
        "description", "threshold", "custom_questions",
    }
    return JobDescription(**{k: v for k, v in doc.items() if k in valid})


def save_job(job: JobDescription, company_id: str | None = None) -> None:
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
    if company_id:
        doc["company_id"] = company_id
        _jobs.replace_one({"company_id": company_id}, doc, upsert=True)
    else:
        _jobs.replace_one({"_id": "current"}, doc, upsert=True)


# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATES — tenant-scoped
# ═══════════════════════════════════════════════════════════════════════════

def _candidate_filter(email: str, company_id: str | None = None) -> dict:
    """Build a candidate lookup filter, scoped to a company when known.

    Candidate email is unique *per company* (compound index), so callers that
    know the tenant must pass `company_id` to avoid touching another tenant's
    candidate. Callers without it (legacy/global paths) fall back to email-only.
    """
    if company_id:
        return {"company_id": company_id, "email": email}
    return {"email": email}


def load_candidates(company_id: str | None = None) -> list[ParsedResume]:
    resumes = []
    valid_fields = {
        "file_name", "full_name", "email", "phone", "skills",
        "experience_years", "education", "linkedin", "github",
        "raw_text", "uploaded_at",
    }
    query = {"company_id": company_id} if company_id else {}
    for doc in _candidates.find(query):
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


def upsert_candidate(
    resume: ParsedResume,
    pipeline_stage: str = "uploaded",
    company_id: str | None = None,
) -> None:
    doc = _resume_to_dict(resume)
    doc["pipelineStage"] = pipeline_stage
    if company_id:
        doc["company_id"] = company_id
    _candidates.replace_one(_candidate_filter(resume.email, company_id), doc, upsert=True)


def clear_candidates(company_id: str | None = None) -> None:
    if company_id:
        _candidates.delete_many({"company_id": company_id})
    else:
        _candidates.delete_many({})


def get_candidate_doc(email: str, company_id: str | None = None) -> dict | None:
    doc = _candidates.find_one(_candidate_filter(email, company_id))
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def set_candidate_invitation(email: str, invitation: dict, company_id: str | None = None) -> None:
    _candidates.update_one(
        _candidate_filter(email, company_id),
        {"$set": {"invitation": invitation, "pipelineStage": "invited"}},
    )


def set_candidate_hr_invitation(email: str, invitation: dict, company_id: str | None = None) -> None:
    _candidates.update_one(
        _candidate_filter(email, company_id),
        {"$set": {"hr_invitation": invitation, "pipelineStage": "hr_invited"}},
    )


def set_candidate_technical_interview(email: str, interview: dict, company_id: str | None = None) -> None:
    stage = "hired" if interview.get("decision") == "PASS" else "tech_failed"
    _candidates.update_one(
        _candidate_filter(email, company_id),
        {"$set": {"technical_interview": interview, "pipelineStage": stage}},
    )


def set_candidate_hr_interview(email: str, interview: dict, company_id: str | None = None) -> None:
    stage = "hr_passed" if interview.get("decision") == "PASS" else "hr_failed"
    _candidates.update_one(
        _candidate_filter(email, company_id),
        {"$set": {"hr_interview": interview, "pipelineStage": stage}},
    )


def set_candidate_interview_recording(
    email: str,
    interview_type: str,
    recording_meta: dict,
    company_id: str | None = None,
) -> None:
    """Persist recording metadata inside the interview document."""
    field = f"{interview_type}_interview"
    _candidates.update_one(
        _candidate_filter(email, company_id),
        {"$set": {f"{field}.recording": recording_meta}},
    )


def append_transcript_turn(
    email: str,
    role: str,
    text: str,
    extra: dict | None = None,
    company_id: str | None = None,
) -> None:
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
        _candidate_filter(email, company_id),
        {"$push": {"interview_transcript": turn}},
    )
