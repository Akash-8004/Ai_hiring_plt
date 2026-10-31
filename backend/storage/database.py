"""MongoDB persistence layer — candidates, jobs, users, companies, audit log.

All tenant-scoped functions accept a `company_id` parameter to enforce data
isolation between companies.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import re
from typing import Any
from uuid import uuid4

from bson import ObjectId
from pymongo import DESCENDING, MongoClient, ReturnDocument

from backend.config import load_env
from backend.core.models import JobDescription, ParsedResume
from backend.core.sanitizer import sanitize_dict_fields

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
_email_logs = _db["email_logs"]
_jd_requests = _db["jd_change_requests"]
_resume_jobs = _db["resume_jobs"]
_interview_usage = _db["interview_usage"]

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
    _email_logs.create_index([("to_email", 1), ("sent_at", DESCENDING)])
    _email_logs.create_index([("status", 1)])
    _jd_requests.create_index([("company_id", 1), ("job_id", 1)], unique=True)
    # BUG 24: indexes for faster stats and list_companies queries
    _candidates.create_index("technical_interview.status")
    _candidates.create_index("hr_interview.status")
    _companies.create_index([("created_at", DESCENDING)])
    _companies.create_index("status")
    _users.create_index("company_id")
    _resume_jobs.create_index("batchId")
    _resume_jobs.create_index([("status", 1), ("created_at", 1)])
    _resume_jobs.create_index([("company_id", 1), ("status", 1)])
    _resume_jobs.create_index("expireAt", expireAfterSeconds=0)
    try:
        _db.create_collection("interview_usage")
    except Exception:
        pass
    _interview_usage = _db["interview_usage"]
    _interview_usage.create_index("event_id", unique=True)
    _interview_usage.create_index([("company_id", 1), ("created_at", 1)])
    _interview_usage.create_index([("candidate_email", 1), ("interview_type", 1)])
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# USER CRUD
# ═══════════════════════════════════════════════════════════════════════════

def get_user_by_email(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    user = _users.find_one({"email": email})
    if user:
        return user
    # Fallback for any legacy rows still stored with mixed case.
    return _users.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})


def normalize_user_emails() -> dict:
    """Lowercase every stored user email so login and duplicate checks are case-insensitive.

    Case-variant collisions (e.g. both john@x.com and John@x.com already exist) are
    left untouched so nobody gets locked out — the case-insensitive fallback in
    get_user_by_email still resolves them. Skipped emails are reported in the result.
    """
    normalized = 0
    skipped_duplicates: list[str] = []
    try:
        raw_emails = [u.get("email") or "" for u in _users.find({}, {"email": 1})]
    except Exception:
        return {"normalized": 0, "skipped_duplicates": []}
    for raw in raw_emails:
        lowered = raw.strip().lower()
        if not lowered or lowered == raw:
            continue
        if _users.find_one({"email": lowered}):
            skipped_duplicates.append(lowered)
            continue
        _users.update_one({"email": raw}, {"$set": {"email": lowered}})
        normalized += 1
    return {"normalized": normalized, "skipped_duplicates": skipped_duplicates}


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


def rotate_session_token(user_id: str, old_token: str, new_token: str) -> bool:
    """Atomically swap the active session token only if it still matches
    ``old_token``. Returns True if the rotation succeeded, False if the session
    was already replaced (stolen-token replay race or concurrent refresh).
    """
    result = _users.update_one(
        {"_id": ObjectId(user_id), "active_session_token": old_token},
        {"$set": {"active_session_token": new_token}},
    )
    return result.modified_count == 1


def update_user_password(user_id: str, password_hash: str) -> None:
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": password_hash}},
    )


def set_user_password_reset_token(
    user_id: str, token_hash: str, expires_at: datetime
) -> None:
    """Persist a one-time password-reset token hash + expiry on the user doc."""
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "password_reset_token_hash": token_hash,
            "password_reset_expires_at": expires_at,
        }},
    )


def get_user_by_reset_token_hash(token_hash: str) -> dict | None:
    """Look up a user by their pending password-reset token hash."""
    if not token_hash:
        return None
    return _users.find_one({"password_reset_token_hash": token_hash})


def clear_user_password_reset_token(user_id: str) -> None:
    """Remove any pending password-reset token (single-use enforcement)."""
    _users.update_one(
        {"_id": ObjectId(user_id)},
        {"$unset": {
            "password_reset_token_hash": "",
            "password_reset_expires_at": "",
        }},
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


def update_user_profile(user_id: str, updates: dict) -> dict | None:
    """Update user name/email/role. Returns the updated doc (sensitive fields stripped)."""
    try:
        result = _users.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        if result:
            result["_id"] = str(result["_id"])
            result.pop("password_hash", None)
            result.pop("active_session_token", None)
            if result.get("company_id"):
                result["company_id"] = str(result["company_id"])
        return result
    except Exception:
        return None


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
    return list(_companies.find({"status": {"$ne": "archived"}}).sort("created_at", DESCENDING))


def list_archived_companies() -> list[dict]:
    return list(_companies.find({"status": "archived"}).sort("deleted_at", DESCENDING))


def list_companies_with_counts() -> list[dict]:
    """List non-archived companies with user counts in a single aggregation (BUG 24 N+1 fix)."""
    pipeline = [
        {"$match": {"status": {"$ne": "archived"}}},
        {"$sort": {"created_at": DESCENDING}},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "company_id",
            "as": "_users_lookup",
        }},
        {"$addFields": {
            "current_users": {"$size": "$_users_lookup"},
        }},
        {"$project": {"_users_lookup": 0}},
    ]
    results = []
    current_period = _month_period()
    for c in _companies.aggregate(pipeline):
        c["_id"] = str(c["_id"])
        # Read credits directly from the doc, auto-reset if period changed
        credits = c.get("credits") or {}
        if credits.get("period") != current_period:
            credits = reset_company_credits_if_due(c["_id"])
        if "adjustments" not in credits:
            allowance = credits.get("allowance", 0)
            remaining = credits.get("remaining", 0)
            used = credits.get("used", 0)
            credits["adjustments"] = remaining + used - allowance
        if "remainder_seconds" not in credits:
            credits["remainder_seconds"] = 0
        c["credits"] = credits
        results.append(c)
    return results


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


def delete_company(company_id: str, deleted_by: str = "") -> dict:
    """Soft-delete (archive) a company. Data is preserved for inspection/restore.

    The company is flagged as archived and its users are suspended so they
    cannot log in. No documents are actually removed.
    """
    cid = ObjectId(company_id)
    now = datetime.now(timezone.utc)
    _companies.update_one(
        {"_id": cid},
        {"$set": {
            "status": "archived",
            "deleted_at": now,
            "deleted_by": deleted_by,
        }},
    )
    users_suspended = _users.update_many(
        {"company_id": cid, "status": {"$ne": "suspended"}},
        {"$set": {"status": "suspended"}},
    ).modified_count
    return {"archived": True, "users_suspended": users_suspended}


def restore_company(company_id: str, restored_by: str = "") -> dict:
    """Restore an archived company back to active. Reactivates its users."""
    cid = ObjectId(company_id)
    _companies.update_one(
        {"_id": cid},
        {
            "$set": {"status": "active"},
            "$unset": {"deleted_at": "", "deleted_by": ""},
        },
    )
    users_reactivated = _users.update_many(
        {"company_id": cid, "status": "suspended"},
        {"$set": {"status": "active"}},
    ).modified_count
    return {"restored": True, "users_reactivated": users_reactivated}


def permanent_delete_company(company_id: str) -> dict:
    """Hard-delete a company and ALL associated data. Irreversible (BUG 25)."""
    cid = ObjectId(company_id)
    users_deleted = _users.delete_many({"company_id": cid}).deleted_count
    candidates_deleted = _candidates.delete_many({"company_id": company_id}).deleted_count
    jobs_deleted = _jobs.delete_many({"company_id": company_id}).deleted_count
    usage_deleted = _usage_log.delete_many({"company_id": company_id}).deleted_count
    email_logs_deleted = _email_logs.delete_many({"metadata.company_id": company_id}).deleted_count
    company_deleted = _companies.delete_one({"_id": cid}).deleted_count
    return {
        "company_deleted": company_deleted,
        "users_deleted": users_deleted,
        "candidates_deleted": candidates_deleted,
        "jobs_deleted": jobs_deleted,
        "usage_logs_deleted": usage_deleted,
        "email_logs_deleted": email_logs_deleted,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CREDITS & USAGE
# ═══════════════════════════════════════════════════════════════════════════

def _month_period(dt: datetime | None = None) -> str:
    when = dt or datetime.now(timezone.utc)
    # Monthly credit resets roll over on the IST month (not UTC), so
    # companies on IST get fresh credits at midnight on the 1st.
    return when.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m")


def _fresh_credits_bucket(allowance: int, period: str | None = None) -> dict:
    period = period or _month_period()
    return {
        "period": period,
        "allowance": allowance,
        "used": 0,
        "remaining": allowance,
        "overage": 0,
        "adjustments": 0,
        "remainder_seconds": 0,
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
            "max_candidates": overrides.get("max_candidates", defaults["max_candidates"]),
            "max_credits": overrides.get("max_credits", defaults["max_credits"]),
        }
    return result


def get_plan_limits(plan: str) -> dict:
    cfg = get_plans_config().get(plan) or get_plans_config()["starter"]
    return {
        "max_users": cfg["max_users"],
        "max_candidates": cfg["max_candidates"],
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
        for key in ("max_users", "max_candidates", "max_credits"):
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
        if "adjustments" not in credits:
            allowance = credits.get("allowance", 0)
            remaining = credits.get("remaining", 0)
            used = credits.get("used", 0)
            credits["adjustments"] = remaining + used - allowance
        if "remainder_seconds" not in credits:
            credits["remainder_seconds"] = 0
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
    adjustments = credits.get("adjustments")
    if adjustments is None:
        adjustments = old_remaining + credits.get("used", 0) - old_allowance
    bucket = {
        "period": current_period,
        "allowance": new_allowance,
        "used": credits.get("used", 0),
        "remaining": new_remaining,
        "overage": overage,
        "adjustments": adjustments,
        "remainder_seconds": credits.get("remainder_seconds", 0),
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
            {"$inc": {"credits.remaining": delta, "credits.adjustments": delta}},
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
                    "credits.adjustments": -actual,
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


# ── Stats cache (10s TTL) ───────────────────────────────────────────────────
import time as _time
import threading as _threading

_stats_cache: dict | None = None
_stats_cache_ts: float = 0.0
_stats_cache_lock = _threading.Lock()
_STATS_CACHE_TTL = 10  # seconds


def get_platform_stats() -> dict:
    """Platform-wide KPIs — uses $facet to minimise round-trips and a 10s TTL cache.

    Round-trip budget (was 7, now 2-3):
      1. _companies $facet  → total / active / suspended / archived counts
      2. _candidates $facet → total + completed-interview count
      3. _users estimated_document_count (no filter, single fast call)
    """
    global _stats_cache, _stats_cache_ts

    now = _time.monotonic()
    if _stats_cache is not None and (now - _stats_cache_ts) < _STATS_CACHE_TTL:
        return _stats_cache

    with _stats_cache_lock:
        # Double-check after acquiring the lock
        now = _time.monotonic()
        if _stats_cache is not None and (now - _stats_cache_ts) < _STATS_CACHE_TTL:
            return _stats_cache

        # ── 1) Companies: single $facet for all four counts ─────────────
        company_pipeline = [{"$facet": {
            "total":     [{"$match": {"status": {"$ne": "archived"}}}, {"$count": "n"}],
            "active":    [{"$match": {"status": "active"}},            {"$count": "n"}],
            "suspended": [{"$match": {"status": "suspended"}},         {"$count": "n"}],
            "archived":  [{"$match": {"status": "archived"}},          {"$count": "n"}],
        }}]
        company_result = list(_companies.aggregate(company_pipeline))
        cr = company_result[0] if company_result else {}

        def _extract(facet_result: list) -> int:
            return facet_result[0]["n"] if facet_result else 0

        # ── 2) Candidates: total + completed-interview count ────────────
        candidate_pipeline = [{"$facet": {
            "total": [{"$count": "n"}],
            "interviews": [
                {"$match": {"$or": [
                    {"technical_interview.status": "completed"},
                    {"hr_interview.status": "completed"},
                ]}},
                {"$count": "n"},
            ],
        }}]
        candidate_result = list(_candidates.aggregate(candidate_pipeline))
        cand = candidate_result[0] if candidate_result else {}

        # ── 3) Users: no filter, fast estimated count ───────────────────
        total_users = _users.estimated_document_count()

        stats = {
            "total_companies":     _extract(cr.get("total", [])),
            "active_companies":    _extract(cr.get("active", [])),
            "suspended_companies": _extract(cr.get("suspended", [])),
            "archived_companies":  _extract(cr.get("archived", [])),
            "total_users":         total_users,
            "total_candidates":    _extract(cand.get("total", [])),
            "total_interviews":    _extract(cand.get("interviews", [])),
        }

        _stats_cache = stats
        _stats_cache_ts = _time.monotonic()
        return stats


# ═══════════════════════════════════════════════════════════════════════════
# JOB — tenant-scoped, multi-drive
# ═══════════════════════════════════════════════════════════════════════════

_JOB_DESCRIPTION_FIELDS = {
    "title", "department", "location", "experience_years",
    "required_skills", "nice_to_have_skills", "education",
    "description", "threshold", "hr_interview_duration",
    "technical_interview_duration", "custom_questions", "hr_deadline", "technical_deadline",
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
        "hr_deadline": job.hr_deadline,
        "technical_deadline": job.technical_deadline,
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
        if existing:
            doc["hr_deadline"] = existing.get("hr_deadline")
            doc["technical_deadline"] = existing.get("technical_deadline")
    _jobs.replace_one({"company_id": cid, "job_id": job_id}, doc, upsert=True)
    stored = _jobs.find_one({"company_id": cid, "job_id": job_id}) or doc
    return stored


def get_job_by_id(company_id: str, job_id: str) -> JobDescription | None:
    doc = _jobs.find_one({"company_id": str(company_id), "job_id": job_id})
    if not doc:
        return None
    return _dict_to_job(doc)


def set_job_deadline(company_id: str, job_id: str, interview_type: str, deadline: str | None) -> None:
    field = "hr_deadline" if interview_type == "hr" else "technical_deadline"
    _jobs.update_one(
        {"company_id": str(company_id), "job_id": job_id},
        {"$set": {field: deadline, "updated_at": datetime.now(timezone.utc)}},
    )


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


def count_company_candidates(company_id: str) -> int:
    return _candidates.count_documents({"company_id": str(company_id)})


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
        "jobs_used": count_jobs(cid),
        "active_job_id": active_job_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# JD CHANGE REQUESTS — sub-user proposals awaiting company-admin approval
# ═══════════════════════════════════════════════════════════════════════════

def get_jd_request(company_id: str, job_id: str) -> dict | None:
    """Return the pending (or latest) JD change request for a job drive."""
    return _jd_requests.find_one({"company_id": str(company_id), "job_id": job_id})


def get_jd_request_by_id(request_id: str) -> dict | None:
    try:
        return _jd_requests.find_one({"_id": ObjectId(request_id)})
    except Exception:
        return None


def list_jd_requests(company_id: str | None = None, status: str | None = None) -> list[dict]:
    query: dict = {}
    if company_id:
        query["company_id"] = str(company_id)
    if status:
        query["status"] = status
    return list(_jd_requests.find(query).sort("requested_at", 1))


def upsert_jd_request(
    company_id: str,
    job_id: str,
    proposed: dict,
    target_status: str,
    requested_by: dict,
) -> dict:
    """Create or replace the pending JD change request for a job drive.

    There is at most one request per ``(company_id, job_id)``. Submitting a new
    proposal while one is still pending replaces it.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "company_id": str(company_id),
        "job_id": job_id,
        "target_status": target_status,   # "create" | "edit"
        "proposed": proposed,             # proposed JobDescription fields
        "status": "pending",
        "requested_by_id": requested_by.get("id"),
        "requested_by_email": requested_by.get("email"),
        "requested_by_name": requested_by.get("name"),
        "requested_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
    }
    _jd_requests.update_one(
        {"company_id": str(company_id), "job_id": job_id},
        {"$set": doc},
        upsert=True,
    )
    return get_jd_request(company_id, job_id)


def resolve_jd_request(
    company_id: str,
    job_id: str,
    decision: str,          # "approved" | "rejected"
    reviewed_by: dict,
    note: str | None = None,
) -> dict | None:
    """Mark a pending request as approved or rejected without deleting it."""
    now = datetime.now(timezone.utc)
    _jd_requests.update_one(
        {"company_id": str(company_id), "job_id": job_id, "status": "pending"},
        {"$set": {
            "status": decision,
            "reviewed_by_id": reviewed_by.get("id"),
            "reviewed_by_email": reviewed_by.get("email"),
            "reviewed_at": now,
            "review_note": note,
        }},
    )
    return get_jd_request(company_id, job_id)


def has_pending_jd_request(company_id: str, job_id: str) -> bool:
    doc = _jd_requests.find_one(
        {"company_id": str(company_id), "job_id": job_id, "status": "pending"}
    )
    return doc is not None


# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATES — tenant-scoped
# ═══════════════════════════════════════════════════════════════════════════

# Free-text candidate fields kept plain-text on write/read (BUG 25) — mirrors
# the lead-form strip-on-write policy (BUG 28).
_CANDIDATE_SANITIZED_FIELDS = (
    "file_name",
    "full_name",
    "education",
    "job_title",
    "location",
    "summary",
)


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


def load_candidates(
    company_id: str | None = None,
    job_id: str | None = None,
    projection: dict | None = None,
) -> list[ParsedResume]:
    resumes = []
    valid_fields = {
        "file_name", "full_name", "email", "phone", "skills",
        "experience_years", "education", "linkedin", "github",
        "raw_text", "job_title", "location", "summary", "parsing_provider", "uploaded_at",
        "other_links",
    }
    query = _candidate_query(company_id, job_id)
    if projection is None:
        # Exclude large nested transcripts/recordings by default for fast lightweight transfer
        projection = {
            "interview_transcript": 0,
            "hr_interview.transcript": 0,
            "technical_interview.transcript": 0,
            "technical_interview.recording": 0,
            "hr_interview.recording": 0,
        }
    for doc in _candidates.find(query, projection):
        doc["uploaded_at"] = doc.get("uploaded_at") or datetime.now(timezone.utc)
        clean_doc = {k: v for k, v in doc.items() if k in valid_fields}
        clean_doc.setdefault("phone", "Not found")
        clean_doc.setdefault("linkedin", "")
        clean_doc.setdefault("github", "")
        clean_doc.setdefault("job_title", "")
        clean_doc.setdefault("location", "")
        clean_doc.setdefault("summary", "")
        clean_doc.setdefault("parsing_provider", "legacy")
        clean_doc.setdefault("other_links", [])
        # Sanitize legacy rows that were persisted before strip-on-write existed
        sanitize_dict_fields(clean_doc, _CANDIDATE_SANITIZED_FIELDS)
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
        "job_title": resume.job_title,
        "location": resume.location,
        "summary": resume.summary,
        "parsing_provider": resume.parsing_provider,
        "other_links": resume.other_links,
        "uploaded_at": resume.uploaded_at,
    }


def upsert_candidate(
    resume: ParsedResume,
    pipeline_stage: str = "uploaded",
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """Insert a new candidate or update resume fields for an existing one.

    On re-upload (same email + company + job), only the resume-sourced fields
    are refreshed.  Pipeline state, invitations, interview results, transcripts,
    recordings, and email-sent flags are **preserved** so that a resume update
    never silently destroys a candidate's progress.  (BUG 29 fix)
    """
    filt = _candidate_filter(resume.email, company_id, job_id)
    resume_fields = _resume_to_dict(resume)
    if company_id:
        resume_fields["company_id"] = str(company_id)
    if job_id:
        resume_fields["job_id"] = job_id
    # BUG 25: strip-on-write so stored values are consistent plain text,
    # regardless of which caller/parser produced the resume fields.
    sanitize_dict_fields(resume_fields, _CANDIDATE_SANITIZED_FIELDS)

    # $set always updates resume data; $setOnInsert sets pipeline stage only on
    # first insert so a re-upload cannot reset an in-progress candidate.
    _candidates.update_one(
        filt,
        {
            "$set": resume_fields,
            "$setOnInsert": {"pipelineStage": pipeline_stage},
        },
        upsert=True,
    )


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


def set_candidate_invitation_expiry(
    email: str,
    interview_type: str,
    expires_at: str,
    deadline_source: str = "per_candidate",
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    invitation_field = "hr_invitation" if interview_type == "hr" else "invitation"
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {
            "$set": {
                f"{invitation_field}.expires_at": expires_at,
                f"{invitation_field}.deadline_source": deadline_source,
            }
        },
    )


def set_candidate_email_sent(
    email: str, interview_type: str, company_id: str | None = None, job_id: str | None = None,
) -> None:
    """Mark email as sent for a candidate's interview type (hr or technical)."""
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {f"email_sent.{interview_type}": True}},
    )


def record_candidate_override(
    email: str, entry: dict, company_id: str | None = None, job_id: str | None = None,
) -> None:
    """Append one admin pipeline-override record to the candidate's history.

    Uses ``$push`` so the full override history is preserved — a later invite
    must never erase the fact that an earlier gate was bypassed.
    """
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$push": {"overrides": entry}},
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


def claim_candidate_hired_notification(
    email: str, company_id: str | None = None, job_id: str | None = None,
) -> bool:
    """Atomically claim the right to send the "candidate hired" notification.

    Returns ``True`` exactly once per candidate — the first caller wins. Later
    calls (evaluation re-run, admin resend, etc.) return ``False`` and must
    not send again.
    """
    result = _candidates.update_one(
        {
            **_candidate_filter(email, company_id, job_id),
            "hired_notification_sent": {"$ne": True},
        },
        {"$set": {"hired_notification_sent": True}},
    )
    return result.matched_count == 1


def _interview_field(interview_type: str) -> str:
    return "hr_interview" if interview_type == "hr" else "technical_interview"


def mark_interview_started(
    email: str,
    interview_type: str,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """Record the start of a live interview attempt.

    The attempt is consumed the moment the relay connects, so closing the tab
    cannot be used to preview questions and retry. Deliberately does NOT touch
    ``pipelineStage`` (unlike ``set_candidate_*_interview``): merely starting an
    interview must not move a candidate's pipeline stage.
    """
    field = _interview_field(interview_type)
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {
            "$set": {
                f"{field}.status": "in_progress",
                f"{field}.started_at": datetime.now(timezone.utc).isoformat(),
            },
            "$inc": {f"{field}.attempts_used": 1},
        },
    )


def set_candidate_interview_evaluation_ready(
    email: str,
    interview_type: str,
    ready: bool | None,
    media: dict | None = None,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """Persist media evidence and whether the interview may be evaluated."""
    field = _interview_field(interview_type)
    update: dict = {}
    if ready is not None:
        update[f"{field}.evaluation_ready"] = bool(ready)
    if media is not None:
        update[f"{field}.media"] = media
    if not update:
        return
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": update},
    )


def mark_interview_abandoned(
    email: str,
    interview_type: str,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """Stamp an abandonment on an interview that never reached 'completed'.

    The status is intentionally left as 'in_progress' so the public session
    endpoint keeps reporting the link as locked. The guard against the
    ``completed`` status makes this a no-op for a normally finished interview.
    """
    field = _interview_field(interview_type)
    _candidates.update_one(
        {
            **_candidate_filter(email, company_id, job_id),
            f"{field}.status": {"$ne": "completed"},
        },
        {"$set": {f"{field}.abandoned_at": datetime.now(timezone.utc).isoformat()}},
    )


def reset_candidate_interview(
    email: str,
    interview_type: str,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    """Re-open a started-but-unfinished interview so it can be taken again."""
    field = _interview_field(interview_type)
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {
            "$unset": {
                f"{field}.status": "",
                f"{field}.started_at": "",
                f"{field}.abandoned_at": "",
            },
            "$set": {f"{field}.attempts_used": 0},
        },
    )


def set_candidate_scoring(
    email: str,
    scoring: dict,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    score_val = scoring.get("score")
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {
            "$set": {
                "scoring": scoring,
                "scoring.score": score_val,
                "scoring.breakdown": scoring.get("breakdown"),
                "scoring.scored_at": datetime.now(timezone.utc).isoformat(),
                "cached_score": {
                    "total_score": score_val if score_val is not None else 0,
                    "recommendation": "Shortlist" if (score_val or 0) >= 80 else "Review / Reject",
                    "matched_skills": scoring.get("matched_skills", []),
                    "missing_skills": scoring.get("missing_skills", []),
                    "breakdown": scoring.get("breakdown", {}),
                    "summary": scoring.get("explanation", ""),
                },
            }
        },
    )


def set_candidate_interview_recording(
    email: str,
    interview_type: str,
    recording_meta: dict,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    interview_field = "technical_interview" if interview_type == "technical" else "hr_interview"
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$set": {f"{interview_field}.recording": recording_meta}},
    )


def set_candidate_score(
    email: str,
    score_dict: dict,
    company_id: str | None = None,
    job_id: str | None = None,
) -> None:
    score_val = score_dict.get("total_score")
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {
            "$set": {
                "cached_score": score_dict,
                "scoring": {
                    "score": score_val if score_val is not None else 0,
                    "breakdown": score_dict.get("breakdown", {}),
                    "reasons": [],
                    "explanation": score_dict.get("summary", ""),
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        },
    )


def clear_candidate_scores(company_id: str | None = None, job_id: str | None = None) -> int:
    query = _candidate_query(company_id, job_id)
    result = _candidates.update_many(query, {"$unset": {"cached_score": "", "scoring": ""}})
    return result.modified_count


def get_scoring_fields(job_data: Any) -> dict[str, Any]:
    """Extract and normalize fields that directly impact candidate scoring."""
    if not job_data:
        return {}
    if hasattr(job_data, "__dataclass_fields__"):
        data = asdict(job_data)
    elif hasattr(job_data, "__dict__"):
        data = job_data.__dict__
    elif isinstance(job_data, dict):
        data = job_data
    else:
        return {}

    def _norm_list(val: Any) -> list[str]:
        if isinstance(val, list):
            return sorted(str(x).strip().lower() for x in val if str(x).strip())
        return []

    return {
        "title": str(data.get("title", "")).strip().lower(),
        "required_skills": _norm_list(data.get("required_skills")),
        "nice_to_have_skills": _norm_list(data.get("nice_to_have_skills")),
        "experience_years": int(data.get("experience_years") or 0),
        "education": str(data.get("education", "")).strip().lower(),
        "description": " ".join(str(data.get("description", "")).split()).lower(),
        "threshold": int(data.get("threshold") or 80),
    }


def append_transcript_turn(
    email: str,
    role: str,
    text: str,
    extra: dict | None = None,
    company_id: str | None = None,
    job_id: str | None = None,
    interview_type: str | None = None,
) -> None:
    content = (text or "").strip()
    if not content:
        return
    turn = {
        "role": role,
        "content": content,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if interview_type:
        turn["interview"] = interview_type
    if extra:
        turn.update(extra)
    _candidates.update_one(
        _candidate_filter(email, company_id, job_id),
        {"$push": {"interview_transcript": turn}},
    )


def get_candidate_docs_batch(
    emails: list[str],
    company_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, dict]:
    """Batch-fetch candidate documents keyed by email."""
    if not emails:
        return {}
    filt: dict = {"email": {"$in": list(dict.fromkeys(emails))}}
    if company_id:
        filt["company_id"] = str(company_id)
    if job_id:
        filt["job_id"] = job_id
    result: dict[str, dict] = {}
    for doc in _candidates.find(filt):
        result[doc.get("email")] = doc
    return result


# Backward compatibility alias
get_candidate_docs_by_email_batch = get_candidate_docs_batch


def count_candidates(company_id: str | None = None, job_id: str | None = None) -> int:
    """Count candidates efficiently."""
    query: dict[str, Any] = {}
    if company_id:
        query["company_id"] = str(company_id)
    if job_id:
        query["job_id"] = job_id
    try:
        return _candidates.count_documents(query)
    except Exception:
        return len(list(_candidates.find(query, {"_id": 1})))


def count_candidates_by_job(company_id: str | None = None) -> dict[str, int]:
    """Return a mapping of job_id -> candidate count using a single aggregation."""
    if not company_id:
        return {}
    pipeline = [
        {"$match": {"company_id": str(company_id), "job_id": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$job_id", "count": {"$sum": 1}}},
    ]
    results: dict[str, int] = {}
    try:
        for doc in _candidates.aggregate(pipeline):
            results[str(doc["_id"])] = doc["count"]
    except Exception:
        pass
    return results


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


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL LOGS
# ═══════════════════════════════════════════════════════════════════════════

def insert_email_log(doc: dict) -> str:
    """Insert an email log document and return the string ID."""
    result = _email_logs.insert_one(doc)
    return str(result.inserted_id)


def get_email_logs(filters: dict, page: int = 1, limit: int = 25) -> dict:
    """Query email logs with pagination.

    Supported filter keys: ``email_type``, ``status``, ``to_email``.
    """
    query: dict = {}
    if filters.get("email_type"):
        query["email_type"] = filters["email_type"]
    if filters.get("status"):
        query["status"] = filters["status"]
    if filters.get("to_email"):
        query["to_email"] = filters["to_email"]

    total = _email_logs.count_documents(query)
    skip = (page - 1) * limit
    entries = list(
        _email_logs.find(query)
        .sort("sent_at", DESCENDING)
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


def find_recent_email_log(
    to_email: str,
    email_type: str,
    company_id: str,
    seconds: int = 60,
) -> dict | None:
    """Check if an email of the given type was sent recently (BUG 21 dedup)."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return _email_logs.find_one({
        "to_email": to_email,
        "email_type": email_type,
        "metadata.company_id": company_id,
        "status": "sent",
        "sent_at": {"$gte": cutoff},
    })


# ═══════════════════════════════════════════════════════════════════════════
# RESUME JOBS
# ═══════════════════════════════════════════════════════════════════════════

def insert_resume_job(doc: dict) -> None:
    _resume_jobs.insert_one(doc)


def claim_resume_job() -> dict | None:
    return _resume_jobs.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "processing", "claimed_at": datetime.now(timezone.utc)}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


def update_resume_job(job_id, update: dict) -> None:
    _resume_jobs.update_one({"_id": job_id}, {"$set": update})


def get_resume_jobs_by_batch(batch_id: str, company_id: str | None = None) -> list[dict]:
    query = {"batchId": batch_id}
    if company_id:
        query["company_id"] = company_id
    return list(_resume_jobs.find(query, {"spool_path": 0}).sort("created_at", 1))


def get_active_resume_batches(company_id: str) -> list[dict]:
    pipeline = [
        {"$match": {"company_id": company_id, "status": {"$in": ["queued", "processing"]}}},
        {"$group": {
            "_id": "$batchId",
            "total": {"$sum": 1},
            "created_at": {"$min": "$created_at"},
        }},
        {"$sort": {"created_at": -1}},
    ]
    batches = []
    for row in _resume_jobs.aggregate(pipeline):
        bid = row["_id"]
        all_jobs = list(_resume_jobs.find({"batchId": bid}, {"spool_path": 0}).sort("created_at", 1))
        statuses = [j["status"] for j in all_jobs]
        batches.append({
            "batchId": bid,
            "status": "processing" if any(s == "processing" for s in statuses) else "queued",
            "total": len(all_jobs),
            "done": sum(1 for s in statuses if s == "done"),
            "failed": sum(1 for s in statuses if s == "failed"),
            "created_at": row["created_at"],
            "jobs": all_jobs,
        })
    return batches


def requeue_stale_resume_jobs(lease_seconds: int = 300) -> int:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=lease_seconds)
    result = _resume_jobs.update_many(
        {"status": "processing", "claimed_at": {"$lt": cutoff}},
        {"$set": {"status": "queued", "claimed_at": None}},
    )
    return result.modified_count


CREDIT_PER_SECONDS = 600.0  # 10 minutes = 1 credit


SECONDS_PER_CREDIT = 600


def compute_cumulative_credits(previous_remainder_seconds: int, duration_seconds: int) -> tuple[int, int]:
    """Return (credits_to_consume, new_remainder_seconds) for one interview.

    Credits accumulate across candidates: 1 credit is debited per full block of
    600 seconds (10 minutes). Leftover seconds carry forward to the next
    interview for the same company.
    """
    prev = max(0, int(previous_remainder_seconds or 0))
    dur = max(0, int(duration_seconds or 0))
    total = prev + dur
    return total // SECONDS_PER_CREDIT, total % SECONDS_PER_CREDIT


def record_interview_usage(
    *,
    company_id: str,
    candidate_email: str,
    interview_type: str,
    event_id: str,
    duration_seconds: float | int,
    started_at: str | datetime | None = None,
    ended_at: str | datetime | None = None,
    metadata: dict | None = None,
) -> dict:
    """Record completed interview usage and apply cumulative credits (1 credit = 600s).
    Returns dict with credits consumed, remainder seconds, etc. Idempotent by event_id.
    """
    try:
        duration_seconds = int(float(duration_seconds))
    except (TypeError, ValueError):
        duration_seconds = 0
    if duration_seconds < 0:
        duration_seconds = 0
    now = datetime.now(timezone.utc)
    if isinstance(started_at, str):
        try:
            started_at_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except Exception:
            started_at_dt = now
    elif isinstance(started_at, datetime):
        started_at_dt = started_at.astimezone(timezone.utc) if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    else:
        started_at_dt = now
    if isinstance(ended_at, str):
        try:
            ended_at_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        except Exception:
            ended_at_dt = now
    elif isinstance(ended_at, datetime):
        ended_at_dt = ended_at.astimezone(timezone.utc) if ended_at.tzinfo else ended_at.replace(tzinfo=timezone.utc)
    else:
        ended_at_dt = now
    existing = _interview_usage.find_one({"event_id": event_id})
    if existing and existing.get("status") != "pending":
        return {
            "credits_consumed": existing.get("credits_consumed", 0),
            "previous_remainder_seconds": existing.get("previous_remainder_seconds", 0),
            "new_remainder_seconds": existing.get("new_remainder_seconds", 0),
            "total_duration_seconds": existing.get("duration_seconds", 0),
            "idempotent": True,
        }
    cid = ObjectId(company_id)
    company = get_company_by_id(company_id)
    if not company:
        return {"credits_consumed": 0, "error": "company_not_found", "idempotent": False}
    if not existing:
        try:
            _interview_usage.insert_one({
                "event_id": event_id,
                "company_id": cid,
                "candidate_email": candidate_email,
                "interview_type": interview_type,
                "duration_seconds": int(duration_seconds),
                "status": "pending",
                "created_at": now,
            })
        except Exception:
            # Another worker inserted the same event first; fall through to the
            # atomic claim below.
            pass

    # Atomically claim the event so two concurrent deliveries of the same
    # completion can never both debit credits. A stale claim (worker crashed
    # mid-processing) is re-claimable after 5 minutes.
    from datetime import timedelta
    claimed = _interview_usage.find_one_and_update(
        {"event_id": event_id, "status": "pending"},
        {"$set": {"status": "processing", "claimed_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        claimed = _interview_usage.find_one_and_update(
            {
                "event_id": event_id,
                "status": "processing",
                "claimed_at": {"$lt": now - timedelta(minutes=5)},
            },
            {"$set": {"claimed_at": now}},
            return_document=ReturnDocument.AFTER,
        )
    if not claimed:
        existing = _interview_usage.find_one({"event_id": event_id})
        if existing:
            return {
                "credits_consumed": existing.get("credits_consumed", 0),
                "previous_remainder_seconds": existing.get("previous_remainder_seconds", 0),
                "new_remainder_seconds": existing.get("new_remainder_seconds", 0),
                "total_duration_seconds": existing.get("duration_seconds", 0),
                "idempotent": True,
            }
    reset_company_credits_if_due(company_id)
    updated = _companies.find_one_and_update(
        {"_id": cid},
        [
            {"$set": {
                "_prev": {"$ifNull": ["$credits.remainder_seconds", 0]},
                "_remaining": {"$ifNull": ["$credits.remaining", 0]},
                "_used": {"$ifNull": ["$credits.used", 0]},
            }},
            {"$set": {"_total": {"$add": ["$_prev", int(duration_seconds)]}}},
            {"$set": {"_needed": {"$toInt": {"$floor": {"$divide": ["$_total", SECONDS_PER_CREDIT]}}}}},
            {"$set": {"_ok": {"$gte": ["$_remaining", "$_needed"]}}},
            {"$set": {
                "credits.remaining": {"$cond": ["$_ok", {"$subtract": ["$_remaining", "$_needed"]}, "$_remaining"]},
                "credits.used": {"$cond": ["$_ok", {"$add": ["$_used", "$_needed"]}, "$_used"]},
                "credits.remainder_seconds": {"$cond": ["$_ok", {"$mod": ["$_total", 600]}, "$_total"]},
                "credits.last_event_id": event_id,
                "credits.last_consumed_credits": {"$cond": ["$_ok", "$_needed", 0]},
                "credits.last_previous_remainder_seconds": "$_prev",
                "credits.last_new_remainder_seconds": {"$cond": ["$_ok", {"$mod": ["$_total", 600]}, "$_total"]},
            }},
            {"$unset": ["_prev", "_remaining", "_used", "_total", "_needed", "_ok"]},
        ],
        return_document=ReturnDocument.AFTER,
    )
    if updated and updated.get("credits", {}).get("last_event_id") == event_id:
        credits_to_consume = int(updated["credits"].get("last_consumed_credits", 0))
        prev_remainder = int(updated["credits"].get("last_previous_remainder_seconds", 0))
        new_remainder = int(updated["credits"].get("last_new_remainder_seconds", 0))
    else:
        credits_to_consume = 0
        prev_remainder = 0
        new_remainder = 0
    usage_doc = {
        "event_id": event_id,
        "company_id": cid,
        "candidate_email": candidate_email,
        "interview_type": interview_type,
        "duration_seconds": int(duration_seconds),
        "duration_minutes": round(int(duration_seconds) / 60.0, 4),
        "previous_remainder_seconds": prev_remainder,
        "new_remainder_seconds": new_remainder,
        "credits_consumed": credits_to_consume,
        "started_at": started_at_dt,
        "ended_at": ended_at_dt,
        "created_at": now,
        "status": "processed",
        "metadata": metadata or {},
    }
    try:
        _interview_usage.update_one({"event_id": event_id}, {"$set": usage_doc})
    except Exception:
        pass
    try:
        log_usage(
            candidate_email,
            company_id,
            minutes=round(int(duration_seconds) / 60.0, 2),
            round_type=interview_type,
            action="interview.completed",
            detail=f"actual_seconds={int(duration_seconds)} credits={credits_to_consume}",
        )
    except Exception:
        pass
    return {
        "credits_consumed": credits_to_consume,
        "previous_remainder_seconds": prev_remainder,
        "new_remainder_seconds": new_remainder,
        "total_duration_seconds": int(duration_seconds),
        "idempotent": False,
    }


def get_interview_usage(
    company_id: str,
    page: int = 1,
    limit: int = 50,
    interview_type: str | None = None,
) -> dict:
    query: dict = {"company_id": ObjectId(company_id), "status": "processed"}
    if interview_type:
        query["interview_type"] = interview_type
    total = _interview_usage.count_documents(query)
    skip = (page - 1) * limit
    entries = list(
        _interview_usage.find(query)
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
