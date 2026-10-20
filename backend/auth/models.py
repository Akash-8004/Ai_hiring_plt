"""Pydantic models for authentication requests and responses."""

from pydantic import BaseModel, Field, field_validator
import re


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{6,19}$")

MAX_CREDIT_ADJUSTMENT = 50000
CREDIT_CAP_MULTIPLIER = 2
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

# BUG 14: manage_users removed under default policy since no route enforces it
VALID_PERMISSIONS = frozenset({
    "manage_jobs", "manage_drive_delete", "manage_resumes", "conduct_interviews",
    "view_pipeline", "view_usage",
})


def _validate_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Invalid email address")
    return value


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""
    if not PHONE_RE.match(value):
        raise ValueError("Enter a valid phone number")
    return value


def _validate_password(value: str) -> str:
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
        raise ValueError("Password must contain at least one special character")
    return value


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
        return _validate_password(v)


class ForgotPasswordRequest(BaseModel):
    """Public request to start the self-service password reset flow."""
    email: str

    @field_validator("email")
    @classmethod
    def validate_forgot_email(cls, v: str) -> str:
        return _validate_email(v)


class ResetPasswordRequest(BaseModel):
    """Self-service password reset using a one-time emailed token."""
    token: str = Field(min_length=16)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


class ResetUserPasswordRequest(BaseModel):
    """Super Admin resets any user's password without knowing the current one."""
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UpdateUserProfileRequest(BaseModel):
    """Super Admin edits a team member's name, email, or role."""
    full_name: str | None = None
    email: str | None = None
    role: str | None = Field(default=None, pattern="^(company_admin|sub_user)$")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_email(v)


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
    auto_send_email: bool = True

    @field_validator("admin_email", "contact_email")
    @classmethod
    def validate_company_emails(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, v: str) -> str:
        return _validate_phone(v) or ""

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        return _validate_password(v)


class CreateSubUserRequest(BaseModel):
    """Company Admin creates a sub-user within their company (plan limit enforced)."""
    email: str
    full_name: str
    password: str = Field(min_length=8)
    permissions: list[str] = Field(
        default_factory=lambda: ["conduct_interviews", "view_pipeline"]
    )
    auto_send_email: bool = True

    @field_validator("email")
    @classmethod
    def validate_subuser_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("password")
    @classmethod
    def validate_subuser_password(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, perms: list[str]) -> list[str]:
        if not perms:
            raise ValueError("Select at least one permission")
        invalid = [p for p in perms if p not in VALID_PERMISSIONS]
        if invalid:
            raise ValueError(f"Invalid permissions: {', '.join(invalid)}")
        return perms


class UpdateCompanyRequest(BaseModel):
    plan: str | None = Field(default=None, pattern="^(starter|growth|enterprise)$")
    max_users: int | None = Field(default=None, ge=1, le=500)
    max_candidates: int | None = Field(default=None, ge=1, le=100000)
    industry: str | None = None
    contact_phone: str | None = None
    price_adjustments: dict[str, float | None] | None = None
    credits_adjustment: int | None = Field(default=None, ge=-MAX_CREDIT_ADJUSTMENT, le=MAX_CREDIT_ADJUSTMENT)

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, v: str | None) -> str | None:
        return _validate_phone(v)


class UpdateSubUserPermissionsRequest(BaseModel):
    permissions: list[str]

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, perms: list[str]) -> list[str]:
        if not perms:
            raise ValueError("Select at least one permission")
        invalid = [p for p in perms if p not in VALID_PERMISSIONS]
        if invalid:
            raise ValueError(f"Invalid permissions: {', '.join(invalid)}")
        return perms


class AdjustCreditsRequest(BaseModel):
    delta: int = Field(ge=-MAX_CREDIT_ADJUSTMENT, le=MAX_CREDIT_ADJUSTMENT)
    note: str = ""


class SendCredentialsRequest(BaseModel):
    """Payload for sending company admin credentials via email."""
    admin_email: str
    admin_password: str


class SendTeamCredentialsRequest(BaseModel):
    """Payload for (re)sending a team member's credentials via email.

    The password is never stored server-side (only its bcrypt hash), so the
    caller must supply the plaintext — same constraint as
    ``SendCredentialsRequest``.
    """
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_team_email(cls, v: str) -> str:
        return _validate_email(v)


class PlanTierUpdate(BaseModel):
    price: float | None = None
    max_users: int | None = Field(default=None, ge=1, le=500)
    max_candidates: int | None = Field(default=None, ge=1, le=100000)


class UpdatePlanPricingRequest(BaseModel):
    plans: dict[str, PlanTierUpdate]


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
    max_candidates: int
    current_users: int = 0
    created_at: str
    credits: dict | None = None
    plan_price: float | None = None


# ── Plan Limits ─────────────────────────────────────────────────────────────

PLAN_LIMITS = {
    "starter": {"max_users": 5, "max_candidates": 100, "max_credits": 500},
    "growth": {"max_users": 15, "max_candidates": 500, "max_credits": 2000},
    "enterprise": {"max_users": 50, "max_candidates": 5000, "max_credits": 10000},
}

PLAN_PRICES = {"starter": 199, "growth": 499, "enterprise": None}
