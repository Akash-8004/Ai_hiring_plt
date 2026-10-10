import os
from unittest import mock
import pytest

from backend.core.models import JobDescription, ParsedResume
from backend.services.ai_ranker import AIRankingService
from backend.services.resume_parser import (
    canonicalize_skill,
    extract_skills_from_text,
    normalize_skill,
    parse_resume_text,
    parse_resume_text_with_ai,
)
from backend.storage import database


def test_extract_unlisted_skills_section_header():
    text = (
        "Name: Jane Doe\n"
        "Email: jane@x.com\n"
        "Skills: Terraform, Kafka, PyTorch, NodeJS, Postgres\n"
        "5 years experience"
    )
    skills = extract_skills_from_text(text)
    normalized = {normalize_skill(s) for s in skills}
    assert "terraform" in normalized
    assert "kafka" in normalized
    assert "pytorch" in normalized
    assert "node.js" in normalized
    assert "postgresql" in normalized

    # Verify canonical display
    assert any("Node.js" in s for s in skills)
    assert any("PostgreSQL" in s for s in skills)


def test_extract_skills_variant_spellings():
    text = "Key Skills: k8s, React.js, restful apis, golang, spring boot, CI/CD"
    skills = extract_skills_from_text(text)
    normalized = {normalize_skill(s) for s in skills}
    assert "kubernetes" in normalized
    assert "react" in normalized
    assert "rest api" in normalized
    assert "go" in normalized
    assert "spring boot" in normalized
    assert "ci/cd" in normalized


def test_extract_skills_multiline_section():
    text = (
        "John Doe\n"
        "john@example.com\n"
        "TECHNICAL SKILLS:\n"
        "Languages: Python, Go, TypeScript\n"
        "Databases: Postgres, Redis, MongoDB\n"
        "DevOps: Docker, Kubernetes, Terraform\n"
        "\n"
        "WORK EXPERIENCE:\n"
        "Senior Software Engineer at Tech Corp\n"
    )
    skills = extract_skills_from_text(text)
    normalized = {normalize_skill(s) for s in skills}
    assert "python" in normalized
    assert "go" in normalized
    assert "typescript" in normalized
    assert "postgresql" in normalized
    assert "redis" in normalized
    assert "mongodb" in normalized
    assert "docker" in normalized
    assert "kubernetes" in normalized
    assert "terraform" in normalized
    assert "senior software engineer" not in normalized


def test_extract_skills_freeform_text_without_section():
    text = (
        "Alice Smith is a backend developer with 4 years experience building systems "
        "using Python, Docker, Kafka, and PostgreSQL in cloud environments."
    )
    skills = extract_skills_from_text(text)
    normalized = {normalize_skill(s) for s in skills}
    assert "python" in normalized
    assert "docker" in normalized
    assert "kafka" in normalized
    assert "postgresql" in normalized


def test_ai_empty_response_fallback_merge():
    text = (
        "Name: Jane Doe\n"
        "Email: jane@x.com\n"
        "Skills: Terraform, Kafka, PyTorch, NodeJS, Postgres\n"
        "5 years experience"
    )
    mock_gemini_resp = {
        "full_name": "Jane Doe",
        "email": "jane@x.com",
        "phone": "555-0100",
        "skills": [],  # AI returns empty list
        "experience_years": 5,
        "education": "BS CS",
        "linkedin": "",
        "github": "",
        "job_title": "Backend Engineer",
        "location": "Remote",
        "summary": "Experienced engineer",
        "other_links": [],
    }
    with mock.patch("backend.services.resume_parser._extract_with_gemini", return_value=mock_gemini_resp), \
         mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_test_key"}):
        res = parse_resume_text_with_ai("resume.txt", text)
        assert res.parsing_provider == "gemini"
        assert len(res.skills) >= 5
        normalized = {normalize_skill(s) for s in res.skills}
        assert "terraform" in normalized
        assert "kafka" in normalized


def test_ai_exception_fallback_and_provider_marker():
    text = (
        "Name: Jane Doe\n"
        "Email: jane@x.com\n"
        "Skills: Terraform, Kafka, PyTorch, NodeJS, Postgres\n"
        "5 years experience"
    )
    with mock.patch("backend.services.resume_parser._extract_with_gemini", side_effect=RuntimeError("Quota 429")), \
         mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy_test_key"}):
        res = parse_resume_text_with_ai("resume.txt", text)
        assert res.parsing_provider == "gemini-failed"
        assert len(res.skills) >= 5
        normalized = {normalize_skill(s) for s in res.skills}
        assert "terraform" in normalized
        assert "node.js" in normalized


def test_missing_api_key_regex_fallback():
    text = (
        "Name: Jane Doe\n"
        "Email: jane@x.com\n"
        "Skills: Terraform, Kafka\n"
    )
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
        res = parse_resume_text_with_ai("resume.txt", text)
        assert res.parsing_provider == "regex-fallback"
        assert "Terraform" in res.skills
        assert "Kafka" in res.skills


def test_empty_whitespace_text_not_regressed():
    res = parse_resume_text_with_ai("blank.pdf", "   \n\t  ")
    assert res.parsing_provider == "none"
    assert res.skills == []
    assert res.raw_text.startswith("[NO_TEXT_EXTRACTED]")


def test_scoring_with_extracted_skills_no_collapse():
    job = JobDescription(
        title="DevOps Engineer",
        department="Engineering",
        location="Remote",
        experience_years=3,
        required_skills=["Terraform", "Kafka", "Postgres", "NodeJS"],
        nice_to_have_skills=[],
        education="Bachelor",
        description="Looking for DevOps engineer proficient in Terraform, Kafka, Postgres, and NodeJS.",
        threshold=70,
    )
    parsed = parse_resume_text(
        "jane.txt",
        "Name: Jane Doe\nEmail: jane@x.com\nSkills: Terraform, Kafka, PyTorch, NodeJS, Postgres\n4 years experience\nEducation: Bachelor"
    )
    ranker = AIRankingService()
    # Rank locally
    score = ranker._rank_locally(parsed, job)
    assert score.breakdown["Skill Match"] == 100
    assert score.total_score >= 70
    assert score.recommendation == "Shortlist"


def test_scoring_safety_net_derives_skills_when_empty():
    job = JobDescription(
        title="Backend Engineer",
        department="Engineering",
        location="Remote",
        experience_years=3,
        required_skills=["Python", "PostgreSQL", "Docker"],
        nice_to_have_skills=[],
        education="Bachelor",
        description="Backend developer with Python, PostgreSQL, and Docker.",
        threshold=70,
    )
    # Resume with empty skills list, but non-trivial raw_text containing skills
    resume = ParsedResume(
        file_name="empty_skills.txt",
        full_name="Bob Developer",
        email="bob@example.com",
        phone="555-1234",
        skills=[],  # empty skills
        experience_years=4,
        education="Bachelor",
        raw_text="Experienced engineer working with Python, PostgreSQL, and Docker daily for 4 years.",
        parsing_provider="gemini",
    )
    ranker = AIRankingService()
    score = ranker.rank_resume(resume, job)
    # Safety net should derive skills from raw_text and achieve high match
    assert "Python" in resume.skills or "python" in [s.lower() for s in resume.skills]
    assert score.breakdown["Skill Match"] == 100
    assert score.recommendation == "Shortlist"


def test_score_cache_consistency():
    # Verify clear_candidate_scores unsets both cached_score and scoring
    with mock.patch("backend.storage.database._candidates.update_many") as mock_update_many:
        mock_update_many.return_value = mock.MagicMock(modified_count=3)
        cleared = database.clear_candidate_scores("comp_123", "job_456")
        assert cleared == 3
        mock_update_many.assert_called_once()
        args, kwargs = mock_update_many.call_args
        assert args[1] == {"$unset": {"cached_score": "", "scoring": ""}}
