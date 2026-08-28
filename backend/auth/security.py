"""JWT token management, password hashing, and FastAPI auth dependencies."""

import os
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

# ── Simple in-memory rate limiter for login endpoint ────────────────────────

_login_attempts: dict[str, list[float]] = {}
LOGIN_RATE_LIMIT = 5         # max attempts
LOGIN_RATE_WINDOW = 60.0     # per 60 seconds


def check_login_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded login rate limit."""
    import time
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    # Prune old attempts
    attempts = [t for t in attempts if now - t < LOGIN_RATE_WINDOW]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    attempts.append(now)
    _login_attempts[ip] = attempts


# ── Password Utilities ──────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT Utilities ───────────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["type"] = "access"
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact your administrator.",
        )

    # Check company is active (for non-super-admins)
    if user.get("role") != "super_admin" and user.get("company_id"):
        company = database.get_company_by_id(user["company_id"])
        if not company or company.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company account suspended. Contact platform administrator.",
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _checker


async def require_job_manage(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    perms = user.get("permissions", []) or []
    if role in ("super_admin", "company_admin") or "manage_jobs" in perms or "*" in perms:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to perform this action.",
    )


async def require_drive_delete(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    perms = user.get("permissions", []) or []
    if role in ("super_admin", "company_admin") or "manage_drive_delete" in perms or "*" in perms:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to perform this action.",
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
