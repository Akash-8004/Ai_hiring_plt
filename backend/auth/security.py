"""JWT token management, password hashing, and FastAPI auth dependencies."""

import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.config import load_env

load_env()

# ── Configuration ───────────────────────────────────────────────────────────

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE-ME-in-production-use-a-256-bit-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

_bearer_scheme = HTTPBearer(auto_error=False)

# ── Simple in-memory rate limiters ──────────────────────────────────────────

_login_attempts: dict[str, list[float]] = {}
LOGIN_RATE_LIMIT = 5         # max attempts
LOGIN_RATE_WINDOW = 60.0     # per 60 seconds

_forgot_attempts: dict[str, list[float]] = {}
FORGOT_RATE_LIMIT = 3        # max requests
FORGOT_RATE_WINDOW = 300.0   # per 5 minutes

_lead_attempts: dict[str, list[float]] = {}
LEAD_RATE_LIMIT = int(os.getenv("LEAD_RATE_LIMIT", "5"))               # max submissions
LEAD_RATE_WINDOW = float(os.getenv("LEAD_RATE_WINDOW_SECONDS", "60"))  # per window


def _check_rate_limit(
    store: dict[str, list[float]],
    key: str,
    limit: int,
    window_seconds: float,
    detail: str,
) -> None:
    """Raise 429 if ``key`` has exceeded the limit within the sliding window."""
    now = time.time()
    attempts = [t for t in store.get(key, []) if now - t < window_seconds]
    remaining = limit - len(attempts)
    if remaining <= 0:
        store[key] = attempts
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(int(window_seconds))},
        )
    attempts.append(now)
    store[key] = attempts


def check_login_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the login rate limit."""
    _check_rate_limit(
        _login_attempts,
        ip,
        LOGIN_RATE_LIMIT,
        LOGIN_RATE_WINDOW,
        "Too many login attempts. Please try again later.",
    )


def check_forgot_password_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the forgot-password rate limit."""
    _check_rate_limit(
        _forgot_attempts,
        ip,
        FORGOT_RATE_LIMIT,
        FORGOT_RATE_WINDOW,
        "Too many password reset requests. Please try again later.",
    )


def check_lead_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the public lead form rate limit."""
    _check_rate_limit(
        _lead_attempts,
        ip,
        LEAD_RATE_LIMIT,
        LEAD_RATE_WINDOW,
        "Too many submissions from this address. Please try again later.",
    )


# ── Password Utilities ──────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT Utilities ───────────────────────────────────────────────────────────

def session_fingerprint(refresh_token: str) -> str:
    """Non-reversible fingerprint binding an access token to a specific session.

    The access token carries this SHA-256 fingerprint of the active refresh
    token as its ``sess`` claim. ``get_current_user`` later compares it against
    the fingerprint of the currently stored ``active_session_token`` so that
    logging out (or logging in elsewhere) instantly invalidates previously
    issued access tokens instead of leaving them usable until expiry.
    """
    return hashlib.sha256((refresh_token or "").encode("utf-8")).hexdigest()


def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["type"] = "access"
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload["jti"] = secrets.token_urlsafe(16)
    payload["type"] = "refresh"
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Password-Reset Token Utilities ──────────────────────────────────────────

def generate_password_reset_token() -> tuple[str, str]:
    """Generate a one-time password-reset token.

    Returns ``(raw_token, token_hash)``. The raw token goes into the emailed
    link; only the SHA-256 hash is persisted, so a database leak cannot be
    replayed into account takeover. Tokens are high-entropy
    (``secrets.token_urlsafe(32)`` ≈ 256 bits), which makes a plain SHA-256
    commitment safe — the preimage resistance argument that applies to
    low-entropy passwords (bcrypt territory) does not apply here.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


# ── Authorization error codes ───────────────────────────────────────────────
# A 403 alone is not machine-actionable: this module also raises 403 for
# account/company suspension, and the rest of the codebase uses 403 for
# business-rule locks (e.g. "Technical round unlocks after the HR deadline
# passes"). Clients that need to react to a *permission* change specifically
# (to revalidate a cached profile) must key off the code, never the status.
PERMISSION_DENIED = "permission_denied"
ACCOUNT_SUSPENDED = "account_suspended"
COMPANY_SUSPENDED = "company_suspended"


def _forbidden(code: str, message: str) -> HTTPException:
    """Build a 403 carrying a machine-readable code.

    The human-readable ``message`` is kept identical to the previous bare-string
    response so existing UI error text and any string matching stay valid;
    ``apiFetchJson`` unwraps ``{code, message}`` into ``err.code`` / ``err.message``.
    """
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message},
    )


# ── FastAPI Dependencies ────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """Extract and validate the JWT from the Authorization header, then load
    the full user document from MongoDB.  Returns the user dict (without
    password_hash) or raises 401.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Import here to avoid circular imports
    from backend.storage import database
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.get("status") != "active":
        raise _forbidden(
            ACCOUNT_SUSPENDED,
            "Account suspended. Contact your administrator.",
        )

    # Session binding: an access token is only valid while it belongs to the
    # user's currently active session. Logout clears active_session_token, so
    # any access token issued for that session is rejected immediately.
    active_session_token = user.get("active_session_token")
    if not active_session_token or payload.get("sess") != session_fingerprint(active_session_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been terminated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check company is active (for non-super-admins)
    if user.get("role") != "super_admin" and user.get("company_id"):
        company = database.get_company_by_id(user["company_id"])
        if not company or company.get("status") != "active":
            raise _forbidden(
                COMPANY_SUSPENDED,
                "Company account suspended. Contact platform administrator.",
            )

    user.pop("password_hash", None)
    return user


async def require_super_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required",
        )
    return user


async def require_company_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("role") not in ("super_admin", "company_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company Admin access required",
        )
    return user


async def require_authenticated(
    user: dict = Depends(get_current_user),
) -> dict:
    return user


def require_permission(*required: str):
    """Dependency factory enforcing granular sub-user permissions.

    Tenant owners (super_admin / company_admin) and holders of the wildcard
    ``"*"`` permission are always allowed. Every other user must have *all* of
    the listed permission keys on their account, otherwise a 403 is raised.

    Usage:  ``user: dict = Depends(require_permission("manage_resumes"))``
    """
    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        perms = user.get("permissions", []) or []
        if role in ("super_admin", "company_admin") or "*" in perms:
            return user
        missing = [p for p in required if p not in perms]
        if missing:
            raise _forbidden(
                PERMISSION_DENIED,
                "You do not have permission to perform this action.",
            )
        return user

    return _checker


async def require_job_manage(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    perms = user.get("permissions", []) or []
    if role in ("super_admin", "company_admin") or "manage_jobs" in perms or "*" in perms:
        return user
    raise _forbidden(
        PERMISSION_DENIED,
        "You do not have permission to perform this action.",
    )


async def require_drive_delete(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    perms = user.get("permissions", []) or []
    if role in ("super_admin", "company_admin") or "manage_drive_delete" in perms or "manage_jobs" in perms or "*" in perms:
        return user
    raise _forbidden(
        PERMISSION_DENIED,
        "You do not have permission to perform this action.",
    )


# ── Audit Logging ───────────────────────────────────────────────────────────

def log_activity(
    action: str,
    category: str,
    actor: dict,
    target_type: str | None = None,
    target_id: str | None = None,
    target_label: str | None = None,
    metadata: dict | None = None,
    severity: str = "info",
    request: Request | None = None,
) -> None:
    """Write one audit row. Called from endpoints that mutate state."""
    from backend.storage import database

    entry = {
        "actor_id": str(actor.get("_id", actor.get("id", ""))),
        "actor_email": actor.get("email", ""),
        "actor_role": actor.get("role", ""),
        "company_id": actor.get("company_id"),
        "action": action,
        "category": category,
        "severity": severity,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "target_label": target_label,
        "metadata": metadata or {},
        "ip_address": request.client.host if request and request.client else None,
        "user_agent": request.headers.get("user-agent") if request else None,
        "timestamp": datetime.now(timezone.utc),
    }
    database.insert_audit_log(entry)
