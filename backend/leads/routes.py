import hashlib
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.auth.security import check_lead_rate_limit, log_activity, require_super_admin
from backend.services import email_service
from backend.services.email_templates import demo_confirmation_email
from backend.storage import database

router = APIRouter(tags=["leads"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ── Anti-abuse: lightweight server-side math CAPTCHA (no external service) ──
_CAPTCHA_TTL_SECONDS = 600.0
_captcha_challenges: dict[str, dict] = {}


def _cleanup_captchas() -> None:
    now = time.time()
    for token, challenge in list(_captcha_challenges.items()):
        if challenge["exp"] < now:
            _captcha_challenges.pop(token, None)


@router.get("/api/public/captcha")
def new_captcha() -> dict:
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    token = secrets.token_urlsafe(16)
    _captcha_challenges[token] = {
        "answer_hash": hashlib.sha256(str(a + b).encode("utf-8")).hexdigest(),
        "exp": time.time() + _CAPTCHA_TTL_SECONDS,
    }
    _cleanup_captchas()
    return {"token": token, "question": f"{a} + {b} = ?"}


def _validate_captcha(token: str, answer: str) -> tuple[bool, str]:
    """Consume and validate a CAPTCHA challenge. Challenges are single-use."""
    challenge = _captcha_challenges.pop(token.strip(), None)
    if not challenge or challenge["exp"] < time.time():
        return False, "Security check expired. Please refresh and try again."
    expected = hashlib.sha256(answer.strip().encode("utf-8")).hexdigest()
    if not secrets.compare_digest(expected, challenge["answer_hash"]):
        return False, "Incorrect security check. Please try again."
    return True, ""


class LeadCreateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default="", max_length=100)
    contact_name: str = Field(min_length=1, max_length=120)
    work_email: str = Field(max_length=254)
    phone: str = Field(default="", max_length=30)
    team_size: str = Field(default="", max_length=50)
    hiring_volume: str = Field(default="", max_length=50)
    message: str = Field(default="", max_length=5000)
    captcha_token: str = Field(default="", max_length=128)
    captcha_answer: str = Field(default="", max_length=10)


class LeadUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|contacted|converted|closed)$")
    note: str | None = None
    converted_company_id: str | None = None


def _serialize_lead(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    if out.get("created_at") and hasattr(out["created_at"], "isoformat"):
        out["created_at"] = out["created_at"].isoformat()
    for note in out.get("notes") or []:
        if note.get("at") and hasattr(note["at"], "isoformat"):
            note["at"] = note["at"].isoformat()
    return out


@router.post("/api/public/leads")
def create_lead(payload: LeadCreateRequest, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    check_lead_rate_limit(ip)

    ok, captcha_error = _validate_captcha(payload.captcha_token, payload.captcha_answer)
    if not ok:
        raise HTTPException(status_code=400, detail=captcha_error)

    email = payload.work_email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    doc = {
        "company_name": payload.company_name.strip(),
        "industry": payload.industry.strip(),
        "contact_name": payload.contact_name.strip(),
        "work_email": email,
        "phone": payload.phone.strip(),
        "team_size": payload.team_size.strip(),
        "hiring_volume": payload.hiring_volume.strip(),
        "message": payload.message.strip(),
        "status": "new",
        "created_at": datetime.now(timezone.utc),
        "notes": [],
        "converted_company_id": None,
    }
    lead_id = database.insert_lead(doc)
    log_activity(
        action="lead.created",
        category="lead",
        actor={"_id": "public", "email": email, "role": "public", "company_id": None},
        target_type="lead",
        target_id=lead_id,
        target_label=payload.company_name.strip(),
        metadata={"contact_name": payload.contact_name.strip()},
        request=request,
    )

    # ── Send a confirmation email (best-effort; never block lead creation) ──
    email_sent = False
    try:
        subject, html_body, plain_body = demo_confirmation_email(
            contact_name=payload.contact_name.strip(),
            company_name=payload.company_name.strip(),
            work_email=email,
            team_size=payload.team_size.strip(),
            hiring_volume=payload.hiring_volume.strip(),
            message=payload.message,
        )
        result = email_service.send_email(email, subject, html_body, plain_body)
        email_sent = result.get("ok", False)
        email_service.log_email_send(
            to_email=email,
            subject=subject,
            email_type="demo_confirmation",
            status="sent" if email_sent else "failed",
            error_message=result.get("error"),
            metadata={
                "company_name": payload.company_name.strip(),
                "lead_id": lead_id,
            },
        )
    except Exception:
        pass

    return {"ok": True, "lead_id": lead_id, "email_sent": email_sent}


@router.get("/api/public/plans")
def public_plans() -> dict:
    config = database.get_plans_config()
    tiers = []
    for plan_id, cfg in config.items():
        tiers.append({
            "id": plan_id,
            "label": plan_id.capitalize(),
            "max_users": cfg["max_users"],
            "max_candidates": cfg["max_candidates"],
            "max_credits": cfg["max_credits"],
            "price": cfg["price"],
        })
    return {"plans": tiers}


@router.get("/api/admin/leads")
def admin_list_leads(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_super_admin),
) -> dict:
    result = database.list_leads(status=status, page=page, limit=limit)
    result["leads"] = [_serialize_lead(l) for l in result["leads"]]
    return result


@router.get("/api/admin/leads/{lead_id}")
def admin_get_lead(lead_id: str, user: dict = Depends(require_super_admin)) -> dict:
    lead = database.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _serialize_lead(lead)


@router.put("/api/admin/leads/{lead_id}")
def admin_update_lead(
    lead_id: str,
    body: LeadUpdateRequest,
    request: Request,
    user: dict = Depends(require_super_admin),
) -> dict:
    lead = database.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    updates: dict = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.converted_company_id is not None:
        updates["converted_company_id"] = body.converted_company_id
    if body.note and body.note.strip():
        updates["append_note"] = {"text": body.note.strip(), "by": user.get("email", "")}

    if not updates:
        return {"ok": True, "lead": _serialize_lead(lead)}

    if not database.update_lead(lead_id, updates):
        raise HTTPException(status_code=404, detail="Lead not found")

    updated = database.get_lead_by_id(lead_id)
    log_activity(
        action="lead.updated",
        category="lead",
        actor=user,
        target_type="lead",
        target_id=lead_id,
        target_label=lead.get("company_name"),
        metadata={"status": body.status},
        request=request,
    )
    return {"ok": True, "lead": _serialize_lead(updated)}


@router.delete("/api/admin/leads/{lead_id}")
def admin_delete_lead(
    lead_id: str,
    request: Request,
    user: dict = Depends(require_super_admin),
) -> dict:
    lead = database.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.delete_lead(lead_id)
    log_activity(
        action="lead.deleted",
        category="lead",
        actor=user,
        target_type="lead",
        target_id=lead_id,
        target_label=lead.get("company_name"),
        request=request,
    )
    return {"ok": True}
