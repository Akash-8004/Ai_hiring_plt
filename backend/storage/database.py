"""MongoDB persistence layer — candidates, jobs, users, companies, audit log.

All tenant-scoped functions accept a `company_id` parameter to enforce data
isolation between companies.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from pymongo import DESCENDING, MongoClient, ReturnDocument

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
_usage_log = _db["usage_log"]
_plans_config = _db["plans_config"]
_leads = _db["leads"]

# ── Indexes ─────────────────────────────────────────────────────────────────
try:
    # Legacy builds put a GLOBAL unique index on candidate email, which breaks
    # multi-tenancy (two companies can't hold the same candidate). Drop it and
    # replace with a per-company compound unique index.
    try:
        _candidates.drop_index("email_1")
    except Exception:
        pass
    try:
        _candidates.drop_index("company_id_1_email_1")
    except Exception:
        pass
    _candidates.create_index([("company_id", 1), ("job_id", 1), ("email", 1)], unique=True)
    _candidates.create_index("company_id")
    _candidates.create_index("job_id")
    _users.create_index("email", unique=True)
    _companies.create_index("slug", unique=True)
    _audit_log.create_index([("timestamp", DESCENDING)])
    _audit_log.create_index([("company_id", 1), ("timestamp", DESCENDING)])
    _jobs.create_index([("company_id", 1), ("job_id", 1)], unique=True)
    _jobs.create_index("company_id")
    _usage_log.create_index([("company_id", 1), ("created_at", DESCENDING)])
    _leads.create_index("work_email")
    _leads.create_index("status")
    _leads.create_index([("created_at", DESCENDING)])
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


def update_user_permissions(user_id: str, permissions: list[str]) -> None:
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"permissions": permissions}},
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
# USER & COMPANY DELETION (Super Admin only)
# ═══════════════════════════════════════════════════════════════════════════

def get_user_by_object_id(user_id: ObjectId) -> dict | None:
    return _users.find_one({"_id": user_id})


def delete_user_by_id(user_id: str) -> bool:
    """Permanently delete a single user document. Returns True if it existed."""
    try:
        result = _users.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def delete_company_sub_users(company_id: str) -> int:
    """Delete all sub_user role members of a company. Returns the count removed."""
    try:
        return _users.delete_many(
            {"company_id": ObjectId(company_id), "role": "sub_user"}
        ).deleted_count
    except Exception:
        return 0


def delete_company_admin_chain(company_id: str) -> dict:
    """Delete the company_admin and all sub_users of a company.

    Keeps the company row, candidates, and jobs intact — used when deleting a
    single company admin account must also remove every account it manages.
    Returns the number of users removed.
    """
    removed = 0
    for user in _users.find({"company_id": ObjectId(company_id)}):
        if user.get("role") in ("company_admin", "sub_user"):
            if _users.delete_one({"_id": user["_id"]}).deleted_count:
                removed += 1
    return {"users_removed": removed}


def delete_company(company_id: str) -> dict:
    """Permanently delete a company and all of its tenant-scoped data.

    Order matters: child collections are removed before the company row so that
    if a later step fails the company still exists for a retry. The audit log is
    intentionally retained for compliance and accountability.
    """
    cid = ObjectId(company_id)
    result = {
        "users": 0,
        "candidates": 0,
        "jobs": 0,
        "usage_logs": 0,
    }
    result["users"] = _users.delete_many({"company_id": cid}).deleted_count
    result["candidates"] = _candidates.delete_many({"company_id": cid}).deleted_count
    result["jobs"] = _jobs.delete_many({"company_id": cid}).deleted_count
    result["usage_logs"] = _usage_log.delete_many({"company_id": cid}).deleted_count
    result["company_removed"] = _companies.delete_one({"_id": cid}).deleted_count
    return result


# ═══════════════════════════════════════════════════════════════════════════
# CREDITS & USAGE
# ═══════════════════════════════════════════════════════════════════════════

def _month_period(dt: datetime | None = None) -> str:
    when = dt or datetime.now(timezone.utc)
    return when.strftime("%Y-%m")


def _fresh_credits_bucket(allowance: int, period: str | None = None) -> dict:
    period = period or _month_period()
    return {
        "period": period,
        "allowance": allowance,
        "used": 0,
        "remaining": allowance,
        "overage": 0,
    }


def _company_allowance(company: dict) -> int:
    plan = company.get("plan", "starter")
    return get_plan_limits(plan)["max_credits"]


def get_plans_config() -> dict:
    from backend.auth.models import PLAN_LIMITS, PLAN_PRICES

    doc = _plans_config.find_one({"_id": "pricing"}) or {}
    stored_limits = doc.get("limits", {})
    stored_prices = doc.get("prices", {})
    result = {}
    for plan_id, defaults in PLAN_LIMITS.items():
        overrides = stored_limits.get(plan_id, {})
        result[plan_id] = {
            "price": stored_prices.get(plan_id, PLAN_PRICES.get(plan_id)),
            "max_users": overrides.get("max_users", defaults["max_users"]),
            "max_jobs": overrides.get("max_jobs", defaults["max_jobs"]),
            "max_credits": overrides.get("max_credits", defaults["max_credits"]),
        }
    return result


def get_plan_limits(plan: str) -> dict:
    cfg = get_plans_config().get(plan) or get_plans_config()["starter"]
    return {
        "max_users": cfg["max_users"],
        "max_jobs": cfg["max_jobs"],
        "max_credits": cfg["max_credits"],
    }


def set_plans_config(plan_updates: dict) -> dict:
    doc = _plans_config.find_one({"_id": "pricing"}) or {}
    prices = dict(doc.get("prices", {}))
    limits = {k: dict(v) for k, v in doc.get("limits", {}).items()}
    for plan_id, fields in plan_updates.items():
        if fields.get("price") is not None or "price" in fields:
            prices[plan_id] = fields.get("price")
        tier_limits = limits.setdefault(plan_id, {})
        for key in ("max_users", "max_jobs", "max_credits"):
            if fields.get(key) is not None:
                tier_limits[key] = fields[key]
    _plans_config.update_one(
        {"_id": "pricing"},
        {"$set": {"prices": prices, "limits": limits, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return get_plans_config()


def init_company_credits(company_id: str, allowance: int) -> None:
    _companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"credits": _fresh_credits_bucket(allowance)}},
    )


def reset_company_credits_if_due(company_id: str) -> dict:
    company = get_company_by_id(company_id)
    if not company:
        return _fresh_credits_bucket(0)
    current_period = _month_period()
    credits = company.get("credits") or {}
    if credits.get("period") == current_period:
        return credits
    allowance = _company_allowance(company)
    bucket = _fresh_credits_bucket(allowance, current_period)
    _companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"credits": bucket}},
    )
    try:
        insert_audit_log({
            "actor_id": "system",
            "actor_email": "system",
            "actor_role": "system",
            "company_id": ObjectId(company_id),
            "action": "credits.reset",
            "category": "credits",
            "severity": "info",
            "target_type": "company",
            "target_id": company_id,
            "target_label": company.get("name", ""),
            "metadata": {"period": current_period, "allowance": allowance},
            "timestamp": datetime.now(timezone.utc),
        })
        log_usage(
            "", company_id,
            minutes=0, round_type="hr", action="reset",
            detail=f"Monthly reset for {current_period}, allowance {allowance}",
        )
    except Exception:
        pass
    return bucket


def get_company_credits(company_id: str) -> dict:
    return reset_company_credits_if_due(company_id)


def apply_plan_credit_change(company_id: str, new_allowance: int) -> dict:
    company = get_company_by_id(company_id)
    if not company:
        return _fresh_credits_bucket(new_allowance)
    current_period = _month_period()
    credits = company.get("credits") or {}
    if credits.get("period") != current_period:
        bucket = _fresh_credits_bucket(new_allowance, current_period)
        _companies.update_one(
            {"_id": ObjectId(company_id)},
            {"$set": {"credits": bucket}},
        )
        return bucket
    old_allowance = credits.get("allowance", 0)
    diff = new_allowance - old_allowance
    old_remaining = credits.get("remaining", 0)
    new_remaining = max(0, old_remaining + diff)
    overage = credits.get("overage", 0)
    if diff < 0:
        overage += old_remaining - new_remaining
    bucket = {
        "period": current_period,
        "allowance": new_allowance,
        "used": credits.get("used", 0),
        "remaining": new_remaining,
        "overage": overage,
    }
    _companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"credits": bucket}},
    )
    return bucket


def consume_credits(company_id: str, minutes: int) -> dict:
    reset_company_credits_if_due(company_id)
    updated = _companies.find_one_and_update(
        {
            "_id": ObjectId(company_id),
            "credits.remaining": {"$gte": minutes},
        },
        {"$inc": {"credits.remaining": -minutes, "credits.used": minutes}},
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        credits = updated.get("credits", {})
        return {"ok": True, "remaining": credits.get("remaining", 0), "reason": ""}
    company = get_company_by_id(company_id)
    remaining = (company or {}).get("credits", {}).get("remaining", 0)
    return {"ok": False, "remaining": remaining, "reason": "insufficient"}


def adjust_company_credits(company_id: str, delta: int) -> dict:
    reset_company_credits_if_due(company_id)
    company = get_company_by_id(company_id)
    if not company:
        return _fresh_credits_bucket(0)
    credits = company.get("credits", {})
    if delta >= 0:
        _companies.update_one(
            {"_id": ObjectId(company_id)},
            {"$inc": {"credits.remaining": delta}},
        )
    else:
        removal = abs(delta)
        old_remaining = credits.get("remaining", 0)
        actual = min(old_remaining, removal)
        blocked = removal - actual
        _companies.update_one(
            {"_id": ObjectId(company_id)},
            {
                "$inc": {
                    "credits.remaining": -actual,
                    "credits.overage": blocked,
                }
            },
        )
    return get_company_credits(company_id)


def log_usage(
    candidate_email: str,
    company_id: str,
    *,
    minutes: int,
    round_type: str,
    action: str,
    detail: str = "",
    actor_id: str | None = None,
) -> None:
    try:
        _usage_log.insert_one({
            "company_id": ObjectId(company_id),
            "candidate_email": candidate_email,
            "round_type": round_type,
            "minutes": minutes,
            "action": action,
            "detail": detail,
            "actor_id": actor_id,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass


def get_usage_log(
    company_id: str,
    page: int = 1,
    limit: int = 50,
    round_type: str | None = None,
) -> dict:
    query: dict = {"company_id": ObjectId(company_id)}
    if round_type:
        query["round_type"] = round_type
    total = _usage_log.count_documents(query)
    skip = (page - 1) * limit
    entries = list(
        _usage_log.find(query)
        .sort("created_at", DESCENDING)
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

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "entries": [_clean(e) for e in entries],
    }


def get_plan_prices() -> dict:
    return {plan_id: cfg["price"] for plan_id, cfg in get_plans_config().items()}


def set_plan_prices(prices: dict) -> dict:
    plan_updates = {plan_id: {"price": price} for plan_id, price in prices.items()}
    return set_plans_config(plan_updates)


def get_platform_credit_stats() -> dict:
    try:
        pipeline = [
            {"$match": {"credits": {"$exists": True}}},
            {
                "$group": {
                    "_id": None,
                    "total_allowance": {"$sum": "$credits.allowance"},
                    "total_used": {"$sum": "$credits.used"},
                    "total_remaining": {"$sum": "$credits.remaining"},
                }
            },
        ]
        totals = list(_companies.aggregate(pipeline))
        summary = totals[0] if totals else {}
        plan_pipeline = [
            {"$match": {"credits": {"$exists": True}}},
            {
                "$group": {
                    "_id": "$plan",
                    "companies": {"$sum": 1},
                    "credits_used": {"$sum": "$credits.used"},
                }
            },
        ]
        per_plan = {
            row["_id"]: {"companies": row["companies"], "credits_used": row["credits_used"]}
            for row in _companies.aggregate(plan_pipeline)
        }
        return {
            "total_allowance": summary.get("total_allowance", 0),
            "total_used": summary.get("total_used", 0),
            "total_remaining": summary.get("total_remaining", 0),
            "per_plan": per_plan,
        }
    except Exception:
        return {
            "total_allowance": 0,
            "total_used": 0,
            "total_remaining": 0,
            "per_plan": {},
        }


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
# JOB — tenant-scoped, multi-drive
# ═══════════════════════════════════════════════════════════════════════════

_JOB_DESCRIPTION_FIELDS = {
    "title", "department", "location", "experience_years",
    "required_skills", "nice_to_have_skills", "education",
    "description", "threshold", "hr_interview_duration",
    "technical_interview_duration", "custom_questions",
}


def _job_to_dict(
    job: JobDescription,
    company_id: str,
    job_id: str,
    status: str = "active",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
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
        "hr_interview_duration": job.hr_interview_duration,
        "technical_interview_duration": job.technical_interview_duration,
        "custom_questions": job.custom_questions,
        "job_id": job_id,
        "company_id": str(company_id),
        "status": status,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }
    return doc


def _dict_to_job(doc: dict) -> JobDescription:
    return JobDescription(**{k: v for k, v in doc.items() if k in _JOB_DESCRIPTION_FIELDS})


def list_jobs(company_id: str) -> list[dict]:
    docs = list(_jobs.find({"company_id": str(company_id), "job_id": {"$exists": True}}).sort("created_at", 1))
    result = []
    for doc in docs:
        result.append({
            "job_id": doc.get("job_id"),
            "title": doc.get("title", ""),
            "department": doc.get("department", ""),
            "status": doc.get("status", "active"),
            "created_at": doc.get("created_at"),
        })
    return result


def upsert_job(job: JobDescription, company_id: str, job_id: str | None = None) -> dict:
    cid = str(company_id)
    now = datetime.now(timezone.utc)
    if not job_id:
        job_id = str(uuid4())
        doc = _job_to_dict(job, cid, job_id, status="active", created_at=now, updated_at=now)
    else:
        existing = _jobs.find_one({"company_id": cid, "job_id": job_id})
        created = existing.get("created_at", now) if existing else now
        status = existing.get("status", "active") if existing else "active"
        doc = _job_to_dict(job, cid, job_id, status=status, created_at=created, updated_at=now)
    _jobs.replace_one({"company_id": cid, "job_id": job_id}, doc, upsert=True)
    stored = _jobs.find_one({"company_id": cid, "job_id": job_id}) or doc
    return stored


def get_job_by_id(company_id: str, job_id: str) -> JobDescription | None:
    doc = _jobs.find_one({"company_id": str(company_id), "job_id": job_id})
    if not doc:
        return None
    return _dict_to_job(doc)


def get_job_doc(company_id: str, job_id: str) -> dict | None:
    return _jobs.find_one({"company_id": str(company_id), "job_id": job_id})


def load_job(company_id: str | None = None, job_id: str | None = None) -> JobDescription | None:
    if company_id and job_id:
        return get_job_by_id(str(company_id), job_id)
    if company_id:
        active = get_active_drive(str(company_id))
        if active:
            job = get_job_by_id(str(company_id), active)
            if job:
                return job
        legacy = _jobs.find_one({"company_id": str(company_id), "job_id": {"$exists": False}})
        if legacy:
            return _dict_to_job(legacy)
        first = _jobs.find_one({"company_id": str(company_id), "job_id": {"$exists": True}})
        if first:
            return _dict_to_job(first)
        return None
    doc = _jobs.find_one({"_id": "current"})
    if not doc:
        return None
    return _dict_to_job(doc)


def save_job(job: JobDescription, company_id: str | None = None) -> None:
    if company_id:
        active = get_active_drive(str(company_id))
        if active:
            upsert_job(job, str(company_id), job_id=active)
        else:
            upsert_job(job, str(company_id))
    else:
        doc = _job_to_dict(job, "", str(uuid4()))
        _jobs.replace_one({"_id": "current"}, doc, upsert=True)


def count_jobs(company_id: str) -> int:
    return _jobs.count_documents({"company_id": str(company_id), "job_id": {"$exists": True}})


def set_active_drive(company_id: str, job_id: str | None) -> None:
    _companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"active_job_id": job_id}},
    )


def get_active_drive(company_id: str) -> str | None:
    company = get_company_by_id(company_id)
    if not company:
        return None
    return company.get("active_job_id")


def delete_job(company_id: str, job_id: str) -> int:
    cid = str(company_id)
    job_result = _jobs.delete_one({"company_id": cid, "job_id": job_id})
    cand_result = _candidates.delete_many({"company_id": cid, "job_id": job_id})
    return job_result.deleted_count + cand_result.deleted_count


def backfill_job_drives() -> dict:
    summary: dict[str, dict] = {}
    for company in list_companies():
        company_id = str(company["_id"])
        legacy_doc = _jobs.find_one({
            "company_id": company_id,
            "job_id": {"$exists": False},
            "_id": {"$ne": "current"},
        })
        if not legacy_doc:
            continue
        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        job = _dict_to_job(legacy_doc)
        upsert_job(job, company_id, job_id=job_id)
        _jobs.delete_one({"_id": legacy_doc["_id"]})
        if not get_active_drive(company_id):
            set_active_drive(company_id, job_id)
        cand_updated = _candidates.update_many(
            {"company_id": company_id, "job_id": {"$exists": False}},
            {"$set": {"job_id": job_id}},
        ).modified_count
        summary[company_id] = {
            "job_id": job_id,
            "candidates_stamped": cand_updated,
        }
        insert_audit_log({
            "actor_id": "system",
            "actor_email": "system",
            "actor_role": "system",
            "company_id": ObjectId(company_id),
            "action": "job.drive_backfilled",
            "category": "job",
            "severity": "info",
            "target_type": "company",
            "target_id": company_id,
            "target_label": company.get("name", ""),
            "metadata": {"job_id": job_id, "candidates_stamped": cand_updated},
            "timestamp": now,
        })
    return summary


def get_drive_overview(company_id: str) -> dict:
    from backend.core.sample_data import DEFAULT_JOB
    from backend.services.drive_metrics import compute_drive_metrics

    cid = str(company_id)
    company = get_company_by_id(cid) or {}
    active_job_id = get_active_drive(cid)
    max_jobs = company.get("max_jobs", 3)
    drives_out = []
    for drive in list_jobs(cid):
        jid = drive["job_id"]
        job_doc = get_job_doc(cid, jid) or {}
        cands = load_candidates(cid, job_id=jid)
        job = get_job_by_id(cid, jid) or DEFAULT_JOB
        drives_out.append({
            "job_id": jid,
            "title": drive.get("title", ""),
            "department": drive.get("department", ""),
            "location": job_doc.get("location", job.location),
            "experience_years": job_doc.get("experience_years", job.experience_years),
            "status": drive.get("status", "active"),
            "created_at": drive.get("created_at"),
            "active": jid == active_job_id,
            "candidate_count": len(cands),
            "metrics": compute_drive_metrics(cands, cid, jid, job),
        })
    return {
        "drives": drives_out,
        "max_jobs": max_jobs,
        "jobs_used": count_jobs(cid),
        "active_job_id": active_job_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATES — tenant-scoped
# ═══════════════════════════════════════════════════════════════════════════

def _candidate_filter(email: str, company_id: str | None = None, job_id: str | None = None) -> dict:
    filt: dict = {"email": email}
    if company_id:
        filt["company_id"] = str(company_id)
    if company_id and job_id:
        filt["job_id"] = job_id
    return filt


def _candidate_query(company_id: str | None = None, job_id: str | None = None) -> dict:
    query: dict = {}
    if company_id:
        query["company_id"] = str(company_id)
    if job_id:
        query["job_id"] = job_id
    return query


def load_candidates(company_id: str | None = None, job_id: str | None = None) -> list[ParsedResume]:
    resumes = []
    valid_fields = {
        "file_name", "full_name", "email", "phone", "skills",
        "experience_years", "education", "linkedin", "github",
        "raw_text", "uploaded_at",
    }
    query = _candidate_query(company_id, job_id)
    for doc in _candidates.find(query):
        doc["uploaded_at"] = doc.get("uploaded_at") or datetime.now(timezone.utc)
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
    job_id: str | None = None,
) -> None:
    doc = _resume_to_dict(resume)
    doc["pipelineStage"] = pipeline_stage
    if company_id:
        doc["company_id"] = str(company_id)
    if job_id:
        doc["job_id"] = job_id
    _candidates.replace_one(_candidate_filter(resume.email, company_id, job_id), doc, upsert=True)


def clear_candidates(company_id: str | None = None, job_id: str | None = None) -> None:
    query = _candidate_query(company_id, job_id)
    if query:
        _candidates.delete_many(query)
    else:
        _candidates.delete_many({})


def get_candidate_doc(email: str, company_id: str | None = None, job_id: str | None = None) -> dict | None:
    doc = _candidates.find_one(_candidate_filter(email, company_id, job_id))
    if not doc:
        if company_id and not job_id:
            doc = _candidates.find_one({"company_id": str(company_id), "email": email})
        if not doc:
            return None
    doc.pop("_id", None)
    return doc


def set_candidate_invitation(
    email: str, invitation: dict, company_id: str | None = None, job_id: str | None = None,
) -> None:
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {"invitation": invitation, "pipelineStage": "invited"}},
    )


def set_candidate_hr_invitation(
    email: str, invitation: dict, company_id: str | None = None, job_id: str | None = None,
) -> None:
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {"hr_invitation": invitation, "pipelineStage": "hr_invited"}},
    )


def set_candidate_technical_interview(
    email: str, interview: dict, company_id: str | None = None, job_id: str | None = None,
) -> None:
    stage = "hired" if interview.get("decision") == "PASS" else "tech_failed"
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {"technical_interview": interview, "pipelineStage": stage}},
    )


def set_candidate_hr_interview(
    email: str, interview: dict, company_id: str | None = None, job_id: str | None = None,
) -> None:
    stage = "hr_passed" if interview.get("decision") == "PASS" else "hr_failed"
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {"hr_interview": interview, "pipelineStage": stage}},
    )


def set_candidate_interview_recording(
    email: str,
    interview_type: str,
    recording_meta: dict,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    field = f"{interview_type}_interview"
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {f"{field}.recording": recording_meta}},
    )


def set_candidate_score(
    email: str,
    score_dict: dict,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {"cached_score": score_dict}},
    )


def clear_candidate_scores(company_id: str | None = None, job_id: str | None = None) -> int:
    query = _candidate_query(company_id, job_id)
    result = _candidates.update_many(query, {"$unset": {"cached_score": ""}})
    return result.modified_count


def append_transcript_turn(
    email: str,
    role: str,
    text: str,
    extra: dict | None = None,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    content = (text or "").strip()
    if not content:
        return
    turn = {
        "role": role,
        "content": content,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        turn.update(extra)
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$push": {"interview_transcript": turn}},
    )


# ═══════════════════════════════════════════════════════════════════════════
# LEADS (demo requests)
# ═══════════════════════════════════════════════════════════════════════════

def insert_lead(doc: dict) -> str:
    result = _leads.insert_one(doc)
    return str(result.inserted_id)


def get_lead_by_id(lead_id: str) -> dict | None:
    try:
        doc = _leads.find_one({"_id": ObjectId(lead_id)})
    except Exception:
        return None
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def list_leads(status: str | None = None, page: int = 1, limit: int = 50) -> dict:
    query: dict = {}
    if status:
        query["status"] = status
    total = _leads.count_documents(query)
    skip = max(0, (page - 1) * limit)
    cursor = _leads.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
    leads = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        leads.append(doc)
    return {"leads": leads, "total": total, "page": page, "limit": limit}


def update_lead(lead_id: str, updates: dict) -> bool:
    try:
        oid = ObjectId(lead_id)
    except Exception:
        return False
    note = updates.pop("append_note", None)
    set_fields = {k: v for k, v in updates.items() if v is not None}
    if note:
        note_entry = {
            "text": note.get("text", ""),
            "by": note.get("by", ""),
            "at": datetime.now(timezone.utc),
        }
        result = _leads.update_one(
            {"_id": oid},
            {"$set": set_fields, "$push": {"notes": note_entry}},
        )
    elif set_fields:
        result = _leads.update_one({"_id": oid}, {"$set": set_fields})
    else:
        return _leads.find_one({"_id": oid}) is not None
    return result.matched_count > 0


def delete_lead(lead_id: str) -> bool:
    try:
        result = _leads.delete_one({"_id": ObjectId(lead_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def count_leads(status: str | None = None) -> int:
    query: dict = {}
    if status:
        query["status"] = status
    return _leads.count_documents(query)
