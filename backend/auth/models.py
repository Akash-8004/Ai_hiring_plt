"""Pydantic models for authentication requests and responses."""

from pydantic import BaseModel, Field, field_validator
import re


# ── Request Models ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateCompanyRequest(BaseModel):
    """Super Admin creates a new company + its admin user."""
    company_name: str = Field(min_length=2, max_length=100)
    industry: str = ""
    contact_email: str
    contact_phone: str = ""
    plan: str = Field(default="starter", pattern="^(starter|growth|enterprise)$")
    admin_email: str
    admin_name: str
    admin_password: str = Field(min_length=8)


class CreateSubUserRequest(BaseModel):
    """Company Admin creates a sub-user within their company (plan limit enforced)."""
    email: str
    full_name: str
    password: str = Field(min_length=8)
    permissions: list[str] = Field(
        default_factory=lambda: ["conduct_interviews", "view_pipeline"]
    )


class UpdateCompanyRequest(BaseModel):
    plan: str | None = Field(default=None, pattern="^(starter|growth|enterprise)$")
    max_users: int | None = Field(default=None, ge=1, le=500)
    max_jobs: int | None = Field(default=None, ge=1, le=1000)
    industry: str | None = None
    contact_phone: str | None = None


# ── Response Models ─────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    company_id: str | None = None
    company_name: str | None = None
    status: str
    permissions: list[str] = []


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserProfile


class CompanyProfile(BaseModel):
    id: str
    name: str
    slug: str
    industry: str
    contact_email: str
    contact_phone: str
    plan: str
    status: str
    max_users: int
    max_jobs: int
    current_users: int = 0
    created_at: str


# ── Plan Limits ─────────────────────────────────────────────────────────────

PLAN_LIMITS = {
    "starter": {"max_users": 5, "max_jobs": 3},
    "growth": {"max_users": 15, "max_jobs": 10},
    "enterprise": {"max_users": 50, "max_jobs": 50},
}
