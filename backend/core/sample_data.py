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
)


SAMPLE_RESUMES = [
    """
    Name: Priya Sharma
    Email: priya.sharma@example.com
    Phone: +91 9876543210
    Experience: 4 years
    Education: B.Tech Computer Science
    Skills: Python, FastAPI, PostgreSQL, Docker, REST API, Redis, AWS
    LinkedIn: linkedin.com/in/priyasharma
    GitHub: github.com/priya-builds
    Built SaaS APIs, optimized database queries, and deployed services with Docker.
    """,
    """
    Name: Rahul Mehta
    Email: rahul.mehta@example.com
    Phone: +91 9123456780
    Experience: 2 years
    Education: BCA
    Skills: JavaScript, React, Node.js, MongoDB, HTML, CSS
    LinkedIn: linkedin.com/in/rahulmehta
    GitHub: github.com/rahul-ui
    Worked mainly on frontend dashboards and basic API integration.
    """,
    """
    Name: Ananya Iyer
    Email: ananya.iyer@example.com
    Phone: +91 9988776655
    Experience: 5 years
    Education: MCA
    Skills: Python, Django, FastAPI, PostgreSQL, Celery, Docker, REST API, Linux
    LinkedIn: linkedin.com/in/ananyaiyer
    GitHub: github.com/ananya-services
    Designed backend services, message queues, and candidate workflow automation.
    """,
]
