"""Super Admin API routes + Company Admin user-management routes.

Super Admin endpoints (/api/admin/*):
  - Company CRUD, suspension, platform stats, audit log, user listing

Company Admin endpoints (/api/company/*):
  - Create sub-users (within plan limits, NO super admin approval needed)
  - List own team members, suspend/activate own sub-users
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.auth.models import (
    PLAN_LIMITS,
    AdjustCreditsRequest,
    CreateCompanyRequest,
    CreateSubUserRequest,
    ResetUserPasswordRequest,
    UpdateCompanyRequest,
    UpdatePlanPricingRequest,
    UpdateSubUserPermissionsRequest,
    VALID_PERMISSIONS,
)
from backend.auth.security import (
    hash_password,
    log_activity,
    require_authenticated,
    require_company_admin,
    require_permission,
    require_super_admin,
)
from backend.storage import database

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
company_router = APIRouter(prefix="/api/company", tags=["company"])


# ═══════════════════════════════════════════════════════════════════════════
# SUPER ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════════════


@admin_router.get("/stats")
def platform_stats(user: dict = Depends(require_super_admin)):
    """Platform-wide KPIs."""
    return database.get_platform_stats()


@admin_router.get("/companies")
def list_companies(user: dict = Depends(require_super_admin)):
    """List all companies with user counts."""
    companies = database.list_companies()
    for c in companies:
        c["_id"] = str(c["_id"])
        c["current_users"] = database.count_company_users(str(c["_id"]))
        c["credits"] = database.get_company_credits(str(c["_id"]))
    return {"companies": companies}


@admin_router.post("/companies")
def create_company(body: CreateCompanyRequest, user: dict = Depends(require_super_admin), request: Request = None):
    """Onboard a new company + create its admin user."""
    # Check if company name or admin email already exists
    if database.get_company_by_slug(_slugify(body.company_name)):
        raise HTTPException(status_code=400, detail="A company with this name already exists")
    if database.get_user_by_email(body.admin_email):
        raise HTTPException(status_code=400, detail="Admin email already in use")

    limits = PLAN_LIMITS.get(body.plan, PLAN_LIMITS["starter"])

    company_doc = {
        "name": body.company_name,
        "slug": _slugify(body.company_name),
        "industry": body.industry,
        "contact_email": body.contact_email,
        "contact_phone": body.contact_phone,
        "plan": body.plan,
        "status": "active",
        "max_users": limits["max_users"],
        "max_jobs": limits["max_jobs"],
        "created_at": datetime.now(timezone.utc),
        "created_by": str(user.get("_id", user.get("id", ""))),
        "settings": {
            "company_logo_url": "",
            "primary_color": "#6366f1",
            "interview_branding_name": body.company_name,
        },
    }
    company_id = database.insert_company(company_doc)
    database.init_company_credits(company_id, limits["max_credits"])

    admin_doc = {
        "email": body.admin_email,
        "password_hash": hash_password(body.admin_password),
        "full_name": body.admin_name,
        "role": "company_admin",
        "company_id": company_id,
        "status": "active",
        "permissions": ["manage_jobs", "manage_resumes", "conduct_interviews", "view_pipeline", "manage_users"],
        "created_by": str(user.get("_id", user.get("id", ""))),
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "login_count": 0,
        "active_session_token": None,
    }
    database.insert_user(admin_doc)

    log_activity(
        action="company.created",
        category="user_mgmt",
        actor=user,
        target_type="company",
        target_id=str(company_id),
        target_label=body.company_name,
        metadata={"plan": body.plan, "admin_email": body.admin_email},
        request=request,
    )

    return {
        "ok": True,
        "company_id": str(company_id),
        "company_name": body.company_name,
        "admin_email": body.admin_email,
        "message": f"Company created. Share credentials with {body.admin_email}",
    }


@admin_router.get("/companies/{company_id}")
def get_company(company_id: str, user: dict = Depends(require_super_admin)):
    """View company details."""
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company["_id"] = str(company["_id"])
    company["current_users"] = database.count_company_users(company_id)
    return company


@admin_router.put("/companies/{company_id}")
def update_company(
    company_id: str,
    body: UpdateCompanyRequest,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    """Update company plan, limits, or details."""
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    updates = {}
    changes = {}
    plan_changed = False
    if body.plan is not None:
        limits = PLAN_LIMITS.get(body.plan, PLAN_LIMITS["starter"])
        changes["plan"] = {"from": company["plan"], "to": body.plan}
        updates["plan"] = body.plan
        updates["max_users"] = limits["max_users"]
        updates["max_jobs"] = limits["max_jobs"]
        plan_changed = body.plan != company.get("plan")
    if body.max_users is not None:
        updates["max_users"] = body.max_users
    if body.max_jobs is not None:
        updates["max_jobs"] = body.max_jobs
    if body.industry is not None:
        updates["industry"] = body.industry
    if body.contact_phone is not None:
        updates["contact_phone"] = body.contact_phone

    if updates:
        database.update_company(company_id, updates)

    if plan_changed and body.plan is not None:
        new_limits = PLAN_LIMITS.get(body.plan, PLAN_LIMITS["starter"])
        database.apply_plan_credit_change(company_id, new_limits["max_credits"])

    if body.credits_adjustment is not None and body.credits_adjustment != 0:
        database.adjust_company_credits(company_id, body.credits_adjustment)
        database.log_usage(
            "", company_id,
            minutes=abs(body.credits_adjustment),
            round_type="hr",
            action="add" if body.credits_adjustment > 0 else "consume",
            detail=f"Manual adjustment via company update: {body.credits_adjustment}",
            actor_id=str(user.get("_id", user.get("id", ""))),
        )
        log_activity(
            action="credits.adjusted",
            category="credits",
            actor=user,
            target_type="company",
            target_id=company_id,
            target_label=company["name"],
            metadata={"delta": body.credits_adjustment},
            severity="warning",
            request=request,
        )

    if body.price_adjustments:
        database.set_plan_prices(body.price_adjustments)
        log_activity(
            action="plans.pricing_updated",
            category="billing",
            actor=user,
            metadata={"prices": body.price_adjustments},
            request=request,
        )

    if updates or plan_changed or body.credits_adjustment or body.price_adjustments:
        if updates:
            log_activity(
                action="company.updated",
                category="user_mgmt",
                actor=user,
                target_type="company",
                target_id=company_id,
                target_label=company["name"],
                metadata={"changes": changes} if changes else {"updates": list(updates.keys())},
                request=request,
            )

    return {"ok": True}


@admin_router.post("/companies/{company_id}/suspend")
def suspend_company(company_id: str, user: dict = Depends(require_super_admin), request: Request = None):
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    database.update_company(company_id, {"status": "suspended"})
    log_activity(
        action="company.suspended",
        category="user_mgmt",
        actor=user,
        target_type="company",
        target_id=company_id,
        target_label=company["name"],
        severity="critical",
        request=request,
    )
    return {"ok": True}


@admin_router.post("/companies/{company_id}/activate")
def activate_company(company_id: str, user: dict = Depends(require_super_admin), request: Request = None):
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    database.update_company(company_id, {"status": "active"})
    log_activity(
        action="company.activated",
        category="user_mgmt",
        actor=user,
        target_type="company",
        target_id=company_id,
        target_label=company["name"],
        request=request,
    )
    return {"ok": True}


@admin_router.get("/companies/{company_id}/users")
def list_company_users(company_id: str, user: dict = Depends(require_super_admin)):
    users = database.list_users_by_company(company_id)
    for u in users:
        u["_id"] = str(u["_id"])
        u.pop("password_hash", None)
        u.pop("active_session_token", None)
        if u.get("company_id"):
            u["company_id"] = str(u["company_id"])
    return {"users": users}


@admin_router.delete("/companies/{company_id}")
def delete_company(
    company_id: str,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    """Permanently delete a company and all of its tenant-scoped data."""
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    result = database.delete_company(company_id)
    log_activity(
        action="company.deleted",
        category="user_mgmt",
        actor=user,
        target_type="company",
        target_id=company_id,
        target_label=company["name"],
        metadata={
            "deleted_users": result.get("users", 0),
            "deleted_candidates": result.get("candidates", 0),
            "deleted_jobs": result.get("jobs", 0),
            "deleted_usage_logs": result.get("usage_logs", 0),
        },
        severity="critical",
        request=request,
    )
    return {"ok": True, "cascaded": result}


@admin_router.get("/companies/{company_id}/activity")
def company_activity(
    company_id: str,
    category: str | None = None,
    severity: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_super_admin),
):
    """Audit log filtered to a specific company."""
    filters = {"company_id": company_id}
    if category:
        filters["category"] = category
    if severity:
        filters["severity"] = severity
    return database.query_audit_log(filters, page, limit)


@admin_router.get("/users")
def list_all_users(user: dict = Depends(require_super_admin)):
    users = database.list_all_users()
    for u in users:
        u["_id"] = str(u["_id"])
        u.pop("password_hash", None)
        u.pop("active_session_token", None)
        if u.get("company_id"):
            u["company_id"] = str(u["company_id"])
    return {"users": users}


@admin_router.post("/users/{user_id}/suspend")
def suspend_user(user_id: str, user: dict = Depends(require_super_admin), request: Request = None):
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot suspend a Super Admin")
    database.update_user_status(user_id, "suspended")
    log_activity(
        action="user.suspended",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        severity="critical",
        request=request,
    )
    return {"ok": True}


@admin_router.post("/users/{user_id}/activate")
def activate_user(user_id: str, user: dict = Depends(require_super_admin), request: Request = None):
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    database.update_user_status(user_id, "active")
    log_activity(
        action="user.activated",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        request=request,
    )
    return {"ok": True}


@admin_router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    """Permanently delete a user account.

    A company_admin deletion cascades to every sub_user in the same company.
    Super Admin accounts can never be deleted.
    """
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot delete a Super Admin")

    metadata = {
        "deleted_email": target["email"],
        "deleted_role": target["role"],
    }

    if target["role"] == "company_admin" and target.get("company_id"):
        cascade = database.delete_company_admin_chain(str(target["company_id"]))
        metadata["cascaded_sub_users"] = cascade.get("users_removed", 0)
    else:
        database.delete_user_by_id(user_id)

    log_activity(
        action="user.deleted",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        metadata=metadata,
        severity="critical",
        request=request,
    )
    return {"ok": True, "deleted_email": target["email"], "metadata": metadata}


@admin_router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: str,
    body: ResetUserPasswordRequest,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    """Super Admin resets a user's password without knowing the current one."""
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot reset another Super Admin's password")

    new_hash = hash_password(body.new_password)
    database.update_user_password(user_id, new_hash)

    log_activity(
        action="user.password_reset",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        metadata={"reset_by": user.get("email", "")},
        severity="critical",
        request=request,
    )

    return {"ok": True, "new_password": body.new_password}


@admin_router.get("/companies/{company_id}/usage")
def admin_company_usage(
    company_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    round_type: str | None = None,
    user: dict = Depends(require_super_admin),
):
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    credits = database.get_company_credits(company_id)
    prices = database.get_plan_prices()
    usage = database.get_usage_log(company_id, page, limit, round_type)
    return {
        "credits": credits,
        "plan_price": prices.get(company.get("plan", "starter")),
        "usage": usage,
    }


@admin_router.post("/companies/{company_id}/credits")
def admin_adjust_credits(
    company_id: str,
    body: AdjustCreditsRequest,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    bucket = database.adjust_company_credits(company_id, body.delta)
    database.log_usage(
        "", company_id,
        minutes=abs(body.delta),
        round_type="hr",
        action="add" if body.delta > 0 else "consume",
        detail=body.note or f"Super Admin adjustment: {body.delta}",
        actor_id=str(user.get("_id", user.get("id", ""))),
    )
    log_activity(
        action="credits.adjusted",
        category="credits",
        actor=user,
        target_type="company",
        target_id=company_id,
        target_label=company["name"],
        metadata={"delta": body.delta, "note": body.note},
        severity="warning",
        request=request,
    )
    return {"ok": True, "credits": bucket}


@admin_router.get("/plans/pricing")
def get_plan_pricing(user: dict = Depends(require_super_admin)):
    return database.get_plan_prices()


@admin_router.put("/plans/pricing")
def update_plan_pricing(
    body: UpdatePlanPricingRequest,
    user: dict = Depends(require_super_admin),
    request: Request = None,
):
    prices = database.set_plan_prices(body.prices)
    log_activity(
        action="plans.pricing_updated",
        category="billing",
        actor=user,
        metadata={"prices": body.prices},
        request=request,
    )
    return prices


@admin_router.get("/companies/{company_id}/drives")
def admin_company_drives(company_id: str, user: dict = Depends(require_super_admin)):
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return database.get_drive_overview(company_id)


@admin_router.get("/audit-log")
def get_audit_log(
    company_id: str | None = None,
    actor_id: str | None = None,
    category: str | None = None,
    action: str | None = None,
    severity: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_super_admin),
):
    """Full platform audit trail with filters."""
    filters = {}
    if company_id:
        filters["company_id"] = company_id
    if actor_id:
        filters["actor_id"] = actor_id
    if category:
        filters["category"] = category
    if action:
        filters["action"] = action
    if severity:
        filters["severity"] = severity
    if from_date:
        filters["from_date"] = from_date
    if to_date:
        filters["to_date"] = to_date
    if search:
        filters["search"] = search
    return database.query_audit_log(filters, page, limit)


# ═══════════════════════════════════════════════════════════════════════════
# COMPANY ADMIN ROUTES  (sub-user management — no super admin approval)
# ═══════════════════════════════════════════════════════════════════════════


@company_router.get("/team")
def list_team(user: dict = Depends(require_company_admin)):
    """List all users belonging to the current user's company."""
    company_id = str(user.get("company_id", ""))
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    company = database.get_company_by_id(company_id)
    users = database.list_users_by_company(company_id)
    for u in users:
        u["_id"] = str(u["_id"])
        u.pop("password_hash", None)
        u.pop("active_session_token", None)
        if u.get("company_id"):
            u["company_id"] = str(u["company_id"])
    return {
        "users": users,
        "max_users": company.get("max_users", 5) if company else 5,
        "current_count": len(users),
        "plan": company.get("plan", "starter") if company else "starter",
    }


@company_router.post("/team")
def create_sub_user(
    body: CreateSubUserRequest,
    user: dict = Depends(require_company_admin),
    request: Request = None,
):
    """Company Admin creates a sub-user directly (no super admin approval).
    Enforces plan-based user limits.
    """
    company_id = str(user.get("company_id", ""))
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")

    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Check plan limit
    current_count = database.count_company_users(company_id)
    max_users = company.get("max_users", PLAN_LIMITS["starter"]["max_users"])
    if current_count >= max_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User limit reached ({current_count}/{max_users}). "
                   f"Contact platform admin to upgrade your plan.",
        )

    # Check duplicate email
    if database.get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email already in use")

    sub_user_doc = {
        "email": body.email,
        "password_hash": hash_password(body.password),
        "full_name": body.full_name,
        "role": "sub_user",
        "company_id": company_id,
        "status": "active",
        "permissions": body.permissions,
        "created_by": str(user.get("_id", user.get("id", ""))),
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "login_count": 0,
        "active_session_token": None,
    }
    new_id = database.insert_user(sub_user_doc)

    log_activity(
        action="user.created",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=str(new_id),
        target_label=f"{body.full_name} ({body.email})",
        metadata={"role": "sub_user", "permissions": body.permissions},
        request=request,
    )

    return {
        "ok": True,
        "user_id": str(new_id),
        "email": body.email,
        "message": f"User created. Share credentials with {body.email}",
    }


@company_router.post("/team/{user_id}/suspend")
def suspend_team_member(user_id: str, user: dict = Depends(require_company_admin), request: Request = None):
    """Company Admin can suspend their own sub-users."""
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target.get("company_id", "")) != str(user.get("company_id", "")):
        raise HTTPException(status_code=403, detail="Cannot manage users from another company")
    if target["role"] != "sub_user":
        raise HTTPException(status_code=400, detail="Can only suspend sub-users")

    database.update_user_status(user_id, "suspended")
    log_activity(
        action="user.suspended",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        request=request,
    )
    return {"ok": True}


@company_router.post("/team/{user_id}/activate")
def activate_team_member(user_id: str, user: dict = Depends(require_company_admin), request: Request = None):
    """Company Admin can reactivate their own sub-users."""
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target.get("company_id", "")) != str(user.get("company_id", "")):
        raise HTTPException(status_code=403, detail="Cannot manage users from another company")
    if target["role"] != "sub_user":
        raise HTTPException(status_code=400, detail="Can only activate sub-users")

    database.update_user_status(user_id, "active")
    log_activity(
        action="user.activated",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        request=request,
    )
    return {"ok": True}


@company_router.put("/team/{user_id}")
def update_team_member_permissions(
    user_id: str,
    body: UpdateSubUserPermissionsRequest,
    user: dict = Depends(require_company_admin),
    request: Request = None,
):
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target.get("company_id", "")) != str(user.get("company_id", "")):
        raise HTTPException(status_code=403, detail="Cannot manage users from another company")
    if target["role"] != "sub_user":
        raise HTTPException(status_code=400, detail="Can only update sub-user permissions")

    invalid = [p for p in body.permissions if p not in VALID_PERMISSIONS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid permissions: {', '.join(invalid)}")

    old_perms = target.get("permissions", [])
    database.update_user_permissions(user_id, body.permissions)
    log_activity(
        action="user.permissions_updated",
        category="user_mgmt",
        actor=user,
        target_type="user",
        target_id=user_id,
        target_label=f"{target['full_name']} ({target['email']})",
        metadata={"from": old_perms, "to": body.permissions},
        request=request,
    )
    return {"ok": True, "permissions": body.permissions}


def _company_usage_response(company_id: str, page: int, limit: int, round_type: str | None) -> dict:
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    credits = database.get_company_credits(company_id)
    prices = database.get_plan_prices()
    usage = database.get_usage_log(company_id, page, limit, round_type)
    return {
        "credits": credits,
        "plan_price": prices.get(company.get("plan", "starter")),
        "usage": usage,
    }


@company_router.get("/usage")
def company_usage(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    round_type: str | None = None,
    user: dict = Depends(require_permission("view_usage")),
):
    company_id = str(user.get("company_id", ""))
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    return _company_usage_response(company_id, page, limit, round_type)


@company_router.get("/billing")
def company_billing(user: dict = Depends(require_permission("view_usage"))):
    company_id = str(user.get("company_id", ""))
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    company = database.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    plan = company.get("plan", "starter")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])
    prices = database.get_plan_prices()
    return {
        "plan": plan,
        "plan_price": prices.get(plan),
        "credits": database.get_company_credits(company_id),
        "max_users": company.get("max_users", limits["max_users"]),
        "max_jobs": company.get("max_jobs", limits["max_jobs"]),
        "current_users": database.count_company_users(company_id),
    }


@company_router.get("/audit-log")
def company_audit_log(
    category: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: dict = Depends(require_company_admin),
):
    """Company-scoped audit trail for the Team Access screen.

    A Company Admin sees only their own company's activity: the company_id is
    taken from the authenticated token, never from the query string, so one
    tenant can never read another tenant's logs.
    """
    company_id = str(user.get("company_id", ""))
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")
    filters = {"company_id": company_id}
    if category:
        filters["category"] = category
    if severity:
        filters["severity"] = severity
    if search:
        filters["search"] = search
    return database.query_audit_log(filters, page, limit)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")
