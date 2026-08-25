"""Authentication API routes: login, logout, refresh, profile, password change."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.models import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserProfile,
)
from backend.auth.security import (
    check_login_rate_limit,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    log_activity,
    require_authenticated,
    verify_password,
)
from backend.storage import database

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request):
    """Unified login for all roles. Returns JWT tokens + user profile."""
    ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(ip)

    user = database.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        # Log failed attempt
        log_activity(
            action="user.login_failed",
            category="auth",
            actor={"email": body.email, "role": "unknown"},
            severity="warning",
            metadata={"reason": "invalid_credentials"},
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact your administrator.",
        )

    # Check company status for non-super-admins
    company_name = None
    if user["role"] != "super_admin" and user.get("company_id"):
        company = database.get_company_by_id(user["company_id"])
        if not company or company.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account suspended. Contact platform administrator.",
            )
        company_name = company.get("name")

    # Create tokens
    token_data = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "company_id": str(user["company_id"]) if user.get("company_id") else None,
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Check if there was a previous session (for audit log)
    had_previous_session = bool(user.get("active_session_token"))

    # Single active session: overwrite the previous refresh token
    database.update_user_session(
        str(user["_id"]),
        refresh_token=refresh_token,
        last_login=datetime.now(timezone.utc),
    )

    if had_previous_session:
        log_activity(
            action="user.session_invalidated",
            category="auth",
            actor=user,
            severity="info",
            metadata={"reason": "new_login"},
            request=request,
        )

    log_activity(
        action="user.login",
        category="auth",
        actor=user,
        severity="info",
        request=request,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserProfile(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            company_id=str(user["company_id"]) if user.get("company_id") else None,
            company_name=company_name,
            status=user["status"],
            permissions=user.get("permissions", []),
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest):
    """Issue a new access token using a valid refresh token."""
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Verify this refresh token is the active one (single session enforcement)
    if user.get("active_session_token") != body.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated — logged in from another location",
        )

    if user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )

    company_name = None
    if user["role"] != "super_admin" and user.get("company_id"):
        company = database.get_company_by_id(user["company_id"])
        if company:
            company_name = company.get("name")

    token_data = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "company_id": str(user["company_id"]) if user.get("company_id") else None,
    }
    new_access = create_access_token(token_data)

    return TokenResponse(
        access_token=new_access,
        refresh_token=body.refresh_token,  # reuse same refresh token
        user=UserProfile(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            company_id=str(user["company_id"]) if user.get("company_id") else None,
            company_name=company_name,
            status=user["status"],
            permissions=user.get("permissions", []),
        ),
    )


@router.post("/logout")
def logout(user: dict = Depends(require_authenticated), request: Request = None):
    """Clear the active session token."""
    database.update_user_session(str(user["_id"]), refresh_token=None)
    log_activity(
        action="user.logout",
        category="auth",
        actor=user,
        severity="info",
        request=request,
    )
    return {"ok": True}


@router.get("/me")
def get_me(user: dict = Depends(require_authenticated)):
    """Return the current user's profile."""
    company_name = None
    if user.get("company_id"):
        company = database.get_company_by_id(user["company_id"])
        if company:
            company_name = company.get("name")

    return UserProfile(
        id=str(user.get("_id", user.get("id", ""))),
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        company_id=str(user["company_id"]) if user.get("company_id") else None,
        company_name=company_name,
        status=user["status"],
        permissions=user.get("permissions", []),
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(require_authenticated),
    request: Request = None,
):
    """Change the logged-in user's password."""
    full_user = database.get_user_by_id(str(user.get("_id", user.get("id", ""))))
    if not full_user or not verify_password(body.current_password, full_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    database.update_user_password(
        str(full_user["_id"]),
        hash_password(body.new_password),
    )

    log_activity(
        action="user.password_changed",
        category="auth",
        actor=user,
        severity="info",
        request=request,
    )
    return {"ok": True}
