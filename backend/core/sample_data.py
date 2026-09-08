from backend.core.models import JobDescription


DEFAULT_JOB = JobDescription(
    title="Backend Engineer",
    department="Engineering",
    location="Remote / India",
    experience_years=3,
    required_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "REST API"],
    nice_to_have_skills=["AWS", "Redis", "Celery", "React"],
    education="B.Tech / MCA / equivalent practical experience",
    description=(
        "We need a backend engineer to build APIs, database models, async workers, "
        "and integrations for a SaaS hiring platform. The candidate should be strong "
        "in Python, FastAPI, PostgreSQL, Docker, REST APIs, and production debugging."
    ),
    threshold=80,
    hr_interview_duration=7,
    technical_interview_duration=5,
)
