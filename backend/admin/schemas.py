"""Pydantic models for admin-specific API requests and responses."""

from pydantic import BaseModel


class CompanyStatsResponse(BaseModel):
    total_companies: int
    active_companies: int
    suspended_companies: int
    total_users: int
    total_candidates: int
    total_interviews: int


class AuditLogQuery(BaseModel):
    company_id: str | None = None
    actor_id: str | None = None
    category: str | None = None
    action: str | None = None
    severity: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    search: str | None = None
    page: int = 1
    limit: int = 50
    sort: str = "desc"
