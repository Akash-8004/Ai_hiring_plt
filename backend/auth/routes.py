"""Authentication API routes: login, logout, refresh, profile, password change."""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserProfile,
)
from backend.auth.security import (
    check_forgot_password_rate_limit,
    check_login_rate_limit,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_password_reset_token,
    hash_password,
    log_activity,
    require_authenticated,
    session_fingerprint,
    verify_password,
)
from backend.config import frontend_base_url
from backend.services import email_service
from backend.services.email_templates import (
    password_changed_notification_email,
    password_reset_email,
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

    # Create tokens. The access token is bound to the refresh token (session)
    # so that logging out instantly invalidates outstanding access tokens.
    token_data = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "company_id": str(user["company_id"]) if user.get("company_id") else None,
    }
    refresh_token = create_refresh_token(token_data)
    access_token = create_access_token({**token_data, "sess": session_fingerprint(refresh_token)})

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
    # Rotate the refresh token: issue a fresh one, bind the new access token to
    # it, and persist it as the active session token — atomically. The presented
    # token is invalidated, so a stolen refresh token can only be used once.
    new_refresh = create_refresh_token(token_data)
    if not database.rotate_session_token(
        str(user["_id"]),
        body.refresh_token,
        new_refresh,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated — logged in from another location",
        )
    new_access = create_access_token({**token_data, "sess": session_fingerprint(new_refresh)})

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
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
    # If a reset link was still pending (user remembered their password
    # mid-flow), consume it so it cannot be used after this change.
    database.clear_user_password_reset_token(str(full_user["_id"]))

    log_activity(
        action="user.password_changed",
        category="auth",
        actor=user,
        severity="info",
        request=request,
    )

    _send_password_change_notification(
        full_user,
        "You changed your own password",
        failed_silently=True,
    )

    return {"ok": True}


# ── Self-Service Password Reset ──────────────────────────────────────────────

def _company_is_active(user_doc: dict) -> bool:
    """Non-super-admins require an active company (mirrors get_current_user)."""
    if user_doc.get("role") == "super_admin" or not user_doc.get("company_id"):
        return True
    company = database.get_company_by_id(str(user_doc["company_id"]))
    return bool(company and company.get("status") == "active")


def _send_password_change_notification(
    user_doc: dict,
    change_type: str,
    failed_silently: bool = True,
) -> bool:
    """Email the user a security notice that their password changed.

    Best-effort: notification failure never breaks the password-change flow
    itself (the mutation already succeeded). Returns True if the email was
    sent successfully.
    """
    try:
        portal_url = f"{frontend_base_url()}/login"
        subject, html_body, plain_body = password_changed_notification_email(
            user_name=user_doc.get("full_name", "") or user_doc.get("email", ""),
            change_type=change_type,
            portal_url=portal_url,
        )
        result = email_service.send_email(
            user_doc["email"], subject, html_body, plain_body,
        )
        sent = result.get("ok", False)
        email_service.log_email_send(
            to_email=user_doc["email"],
            subject=subject,
            email_type="password_changed_notification",
            status="sent" if sent else "failed",
            error_message=result.get("error"),
            metadata={"change_type": change_type},
            sent_by="system",
        )
        return sent
    except Exception as exc:
        if not failed_silently:
            raise
        return False


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Start the self-service password reset flow.

    Always returns the same generic success response so the endpoint cannot
    be used to enumerate registered email addresses. When the account exists
    and is eligible, a single-use reset link (30-minute expiry) is emailed.
    """
    ip = request.client.host if request.client else "unknown"
    check_forgot_password_rate_limit(ip)

    # Per-email cooldown: one reset email per address per 60 seconds
    # (BUG 21 dedup pattern — prevents email flooding of a known address).
    # company_id=None matches log rows without that metadata key (MongoDB
    # dotted-path null semantics) — password-reset emails are not tenant-scoped.
    recent = database.find_recent_email_log(
        to_email=body.email,
        email_type="password_reset",
        company_id=None,
        seconds=60,
    )

    user = database.get_user_by_email(body.email)
    eligible = (
        user
        and user.get("status") == "active"
        and _company_is_active(user)
        and not recent
    )

    if eligible:
        raw_token, token_hash = generate_password_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        database.set_user_password_reset_token(
            str(user["_id"]), token_hash, expires_at,
        )

        try:
            reset_url = (
                f"{frontend_base_url()}/reset-password?token={raw_token}"
            )
            subject, html_body, plain_body = password_reset_email(
                user_name=user.get("full_name", "") or body.email,
                reset_url=reset_url,
                expires_minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            )
            result = email_service.send_email(
                body.email, subject, html_body, plain_body,
            )
            email_ok = result.get("ok", False)
            email_error = result.get("error")
            email_service.log_email_send(
                to_email=body.email,
                subject=subject,
                email_type="password_reset",
                status="sent" if email_ok else "failed",
                error_message=email_error,
                metadata={"user_id": str(user["_id"]), "auto": True},
                sent_by="system",
            )
            log_activity(
                action="user.password_reset_requested",
                category="auth",
                actor=user,
                severity="warning",
                metadata={"email_sent": email_ok, "email_error": email_error},
                request=request,
            )
        except Exception as exc:
            log_activity(
                action="user.password_reset_requested",
                category="auth",
                actor=user,
                severity="warning",
                metadata={"email_sent": False, "email_error": str(exc)},
                request=request,
            )

    # Identical response regardless of whether the account exists/eligible.
    return {
        "ok": True,
        "message": (
            f"If an account exists for {body.email}, "
            f"a password reset link has been sent."
        ),
    }


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, request: Request):
    """Complete a self-service password reset via a one-time emailed token.

    On success the token is consumed (single-use) and every active session
    for the account is invalidated, so any previously issued JWTs die
    immediately through the session-fingerprint check in ``get_current_user``.
    """
    # Hash the presented raw token and look up by hash — the raw token is
    # never persisted, so a database leak cannot be replayed.
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    user = database.get_user_by_reset_token_hash(token_hash)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )

    expires_at = user.get("password_reset_expires_at")
    # pymongo (non-tz_aware) returns naive UTC datetimes; normalize before
    # comparing against the aware now() to avoid a TypeError.
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or expires_at < datetime.now(timezone.utc):
        database.clear_user_password_reset_token(str(user["_id"]))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    if user.get("status") != "active":
        database.clear_user_password_reset_token(str(user["_id"]))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact your administrator.",
        )

    if not _company_is_active(user):
        database.clear_user_password_reset_token(str(user["_id"]))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company account suspended. Contact platform administrator.",
        )

    user_id = str(user["_id"])
    database.update_user_password(user_id, hash_password(body.new_password))
    # Single-use: consume the token even though the update above succeeded.
    database.clear_user_password_reset_token(user_id)
    # Kill every active session so outstanding JWTs are rejected immediately.
    database.update_user_session(user_id, refresh_token=None)

    log_activity(
        action="user.password_self_reset",
        category="auth",
        actor=user,
        severity="critical",
        metadata={"reset_method": "forgot_password_link"},
        request=request,
    )

    _send_password_change_notification(
        user,
        "You reset your password using the recovery link",
        failed_silently=True,
    )

    return {
        "ok": True,
        "message": "Password reset successfully. Please log in with your new password.",
    }
