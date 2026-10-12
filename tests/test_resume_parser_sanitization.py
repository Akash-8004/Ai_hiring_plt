"""Regression tests for BUG 25 — resume fields must never contain HTML.

Resume-sourced free-text fields (file_name, full_name, education, job_title,
location, summary) are kept plain-text on write (strip-on-write), matching the
lead-form policy from BUG 28.  Covers the regex parser, the Gemini parser,
the empty-resume placeholder, the DB write choke-point, and legacy dirty rows
on read.
"""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.models import ParsedResume
from backend.core.sanitizer import strip_html
from backend.services.resume_parser import parse_resume_text, parse_resume_text_with_ai
from backend.storage import database


_SNIPPET = (
    "Name: Jane Doe\n"
    "Email: jane@x.com\n"
    "Skills: Terraform, Kafka\n"
    "B.Tech\n"
    "5 years experience\n"
)


def test_regex_parser_sanitizes_file_name():
    res = parse_resume_text("jane<script>alert(1)</script>.pdf", _SNIPPET)
    assert "<" not in res.file_name
    assert ">" not in res.file_name
    assert "alert(1)" in res.file_name  # inner text is preserved, tags removed
    assert res.full_name == "Jane Doe"


def test_gemini_parser_sanitizes_all_free_text_fields():
    html_name = "<script>alert(1)</script>John<script>x</script>"
    gemini_out = {
        "full_name": html_name,
        "email": "jane@x.com",
        "phone": "555-0100",
        "skills": ["Terraform", "Kafka"],
        "experience_years": 5,
        "education": "<b>BS CS</b> from <i>MIT</i>",
        "linkedin": "",
        "github": "",
        "job_title": "<img src=x onerror=alert(1)>Backend Engineer",
        "location": "<svg><script>alert(1)</script></svg>Remote",
        "summary": "Experienced <style>p{}</style> engineer",
        "other_links": [],
    }
    with mock.patch("backend.services.resume_parser._extract_with_gemini", return_value=gemini_out), \
         mock.patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_test_key"}):
        res = parse_resume_text_with_ai("jane.html.pdf", _SNIPPET)

    assert res.parsing_provider == "gemini"
    assert res.full_name == strip_html(html_name)
    assert res.education == "BS CS from MIT"
    assert res.job_title == "Backend Engineer"
    assert res.location == "alert(1)Remote"  # tag text content is preserved
    assert res.summary == "Experienced p{} engineer"
    for value in (res.full_name, res.education, res.job_title, res.location, res.summary, res.file_name):
        assert "<" not in value
        assert ">" not in value


def test_empty_resume_sanitizes_file_name():
    res = parse_resume_text_with_ai("resume<script>alert(1)</script>.txt", "   \n\t  ")
    assert res.parsing_provider == "none"
    assert "<" not in res.file_name
    assert ">" not in res.file_name
    assert "alert(1)" in res.file_name


def test_upsert_candidate_strips_html_on_write():
    resume = ParsedResume(
        file_name="meera<script>x</script>.txt",
        full_name="Meera <b>Iyer</b>",
        email="meera@example.com",
        phone="555-0100",
        skills=["Python"],
        experience_years=2,
        education="Bachelor<script>alert(1)</script>",
        job_title="<i>Engineer</i>",
        location="Remote <script>x</script>",
        summary="Summary with <img onerror=alert(1)> tag",
    )
    with mock.patch("backend.storage.database._candidates.update_one") as mock_update:
        database.upsert_candidate(resume, company_id="comp-1", job_id="job-1")

    mock_update.assert_called_once()
    args, kwargs = mock_update.call_args
    sets = args[1]["$set"]
    assert sets["file_name"] == "meerax.txt"
    assert sets["full_name"] == "Meera Iyer"
    assert sets["education"] == "Bacheloralert(1)"
    assert sets["job_title"] == "Engineer"
    assert sets["location"] == "Remote x"
    assert sets["summary"] == "Summary with tag"
    assert sets["company_id"] == "comp-1"
    assert sets["job_id"] == "job-1"
    assert args[1]["$setOnInsert"]["pipelineStage"] == "uploaded"


def test_load_candidates_sanitizes_legacy_dirty_rows():
    legacy_doc = {
        "file_name": "old<script>alert(1)</script>.pdf",
        "full_name": "Old <b>Candidate</b>",
        "email": "old@example.com",
        "phone": "555-0199",
        "skills": ["Go"],
        "experience_years": 3,
        "education": "MBA <script>x</script>",
        "job_title": "Lead <i>Engineer</i>",
        "location": "NYC <svg/>",
        "summary": "Summary <iframe src=x></iframe> text",
    }
    with mock.patch("backend.storage.database._candidates.find", return_value=[legacy_doc]):
        resumes = database.load_candidates(company_id="comp-1", job_id="job-1")

    assert len(resumes) == 1
    candidate = resumes[0]
    assert candidate.full_name == "Old Candidate"
    assert candidate.education == "MBA x"
    assert candidate.job_title == "Lead Engineer"
    assert candidate.location == "NYC"
    assert candidate.summary == "Summary text"
    assert "<" not in candidate.file_name
    assert candidate.email == "old@example.com"