import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.auth.security import log_activity, require_super_admin
from backend.storage import database

router = APIRouter(tags=["leads"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadCreateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    industry: str = ""
    contact_name: str = Field(min_length=1, max_length=120)
    work_email: str
    phone: str = ""
    team_size: str = ""
    hiring_volume: str = ""
    message: str = ""


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
    return {"ok": True, "lead_id": lead_id}


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
