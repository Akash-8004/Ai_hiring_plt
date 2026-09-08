from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class JobDescription:
    title: str
    department: str
    location: str
    experience_years: int
    required_skills: list[str]
    nice_to_have_skills: list[str]
    education: str
    description: str
    threshold: int = 80
    hr_interview_duration: int = 7
    technical_interview_duration: int = 5
    custom_questions: list[dict] = field(default_factory=list)
    hr_deadline: str | None = None
    technical_deadline: str | None = None


@dataclass
class ParsedResume:
    file_name: str
    full_name: str
    email: str
    phone: str
    skills: list[str]
    experience_years: int
    education: str
    linkedin: str = ""
    github: str = ""
    raw_text: str = ""
    job_title: str = ""
    location: str = ""
    summary: str = ""
    parsing_provider: str = "regex-fallback"
    other_links: list[dict[str, str]] = field(default_factory=list)
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ResumeScore:
    total_score: int
    recommendation: str
    matched_skills: list[str]
    missing_skills: list[str]
    breakdown: dict[str, int]
    summary: str


@dataclass
class CandidateResult:
    candidate: ParsedResume
    score: ResumeScore
    status: str

    def to_row(self) -> dict[str, Any]:
        return {
            "Name": self.candidate.full_name,
            "Email": self.candidate.email,
            "Phone": self.candidate.phone,
            "Experience": f"{self.candidate.experience_years} yrs",
            "Skills": ", ".join(self.candidate.skills[:8]),
            "Score": self.score.total_score,
            "Status": self.status,
            "Matched": ", ".join(self.score.matched_skills),
            "Missing": ", ".join(self.score.missing_skills),
            "Summary": self.score.summary,
        }
