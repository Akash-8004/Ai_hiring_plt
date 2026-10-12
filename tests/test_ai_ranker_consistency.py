"""Regression tests for BUG 27 — headline score must never contradict its own breakdown.

Covers:
- Gemini path: an internally-inconsistent model output (headline 85 + low
  sub-scores) is reconciled to the rubric-weighted total.
- Local path: the total always equals the weighted breakdown.
- Persisted/cached reads: stale totals are reconciled before display.
"""

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.models import JobDescription, ParsedResume
from backend.services.ai_ranker import (
    AIRankingService,
    reconcile_total_score,
    weighted_total_from_breakdown,
)
from backend.services.ranking import score_candidates


class _FakeResp:
    def __init__(self, content: bytes):
        self.content = content

    def read(self) -> bytes:
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_service() -> AIRankingService:
    svc = AIRankingService()
    svc.provider = "gemini"
    svc.api_key = "fake-key"
    return svc


def _make_job() -> JobDescription:
    return JobDescription(
        title="DevOps Engineer",
        department="Engineering",
        location="Remote",
        experience_years=3,
        required_skills=["Terraform", "Kafka"],
        nice_to_have_skills=[],
        education="Bachelor",
        description="Looking for a DevOps engineer with Terraform and Kafka.",
        threshold=80,
    )


def _make_resume() -> ParsedResume:
    return ParsedResume(
        file_name="meera.txt",
        full_name="Meera Iyer",
        email="meera@example.com",
        phone="555-0100",
        skills=["Python"],
        experience_years=2,
        education="Bachelor",
        raw_text="Meera Iyer. Software engineer building pipelines.",
        parsing_provider="gemini",
    )


def _patch_gemini(model_payload: dict):
    raw = json.dumps({
        "candidates": [{"content": {"parts": [{"text": json.dumps(model_payload)}]}}]
    }).encode()
    return mock.patch("urllib.request.urlopen", return_value=_FakeResp(raw))


def test_gemini_inconsistent_total_reconciled():
    """BUG 27 repro: model says 85 while its breakdown only sums to ~17."""
    job = _make_job()
    resume = _make_resume()
    model = {
        "total_score": 85,
        "recommendation": "Shortlist",
        "matched_skills": ["Terraform"],
        "missing_skills": ["Kafka"],
        "breakdown": {
            "Skill Match": 15,
            "Experience Match": 20,
            "Education Match": 15,
            "Keyword Match": 15,
            "Semantic Match": 20,
        },
        "summary": "Decent profile.",
    }
    with _patch_gemini(model):
        score = _make_service()._rank_with_gemini(resume, job)

    assert score.total_score == 17
    assert score.breakdown["Skill Match"] == 15
    assert score.total_score == weighted_total_from_breakdown(score.breakdown)
    assert score.recommendation == "Review / Reject"


def test_gemini_consistent_total_unchanged():
    """A model total that already matches the weighted breakdown stays as-is."""
    job = _make_job()
    resume = _make_resume()
    breakdown = {
        "Skill Match": 100,
        "Experience Match": 67,
        "Education Match": 75,
        "Keyword Match": 80,
        "Semantic Match": 93,
    }
    weighted = weighted_total_from_breakdown(breakdown)
    model = {
        "total_score": weighted,
        "recommendation": "Shortlist" if weighted >= job.threshold else "Review / Reject",
        "matched_skills": ["Terraform"],
        "missing_skills": ["Kafka"],
        "breakdown": breakdown,
        "summary": "Strong match.",
    }
    with _patch_gemini(model):
        score = _make_service()._rank_with_gemini(resume, job)

    assert score.total_score == weighted
    assert score.recommendation == model["recommendation"]


def test_local_total_always_equals_weighted_breakdown():
    job = _make_job()
    resume = _make_resume()
    svc = AIRankingService()
    score = svc._rank_locally(resume, job)
    assert score.total_score == weighted_total_from_breakdown(score.breakdown)


def test_reconcile_preserves_total_when_no_breakdown():
    assert reconcile_total_score(85, {}) == 85
    assert reconcile_total_score(85, None) == 85
    # A single weighted component contributes its weighted share, not the value
    assert reconcile_total_score(None, {"Skill Match": 15}) == 5
    partial = {"Skill Match": 100, "Experience Match": 100}
    assert reconcile_total_score(None, partial) == 55
    # Unknown/incomplete breakdown keys cannot be weighted -> total kept
    assert reconcile_total_score(85, {"Match": 100, "Foo": 50}) == 85
    # Full breakdown follows the rubric exactly
    full = {
        "Skill Match": 100,
        "Experience Match": 67,
        "Education Match": 75,
        "Keyword Match": 80,
        "Semantic Match": 93,
    }
    assert reconcile_total_score(0, full) == weighted_total_from_breakdown(full)


def test_cached_inconsistent_score_reconciled_before_scoring():
    """Stale cached totals (excluding breakdown) are reconciled on read."""
    resumes = [_make_resume()]
    job = _make_job()
    cols = weighted_total_from_breakdown({
        "Skill Match": 40,
        "Experience Match": 40,
        "Education Match": 50,
        "Keyword Match": 40,
        "Semantic Match": 40,
    })
    docs_by_email = {
        resumes[0].email: {
            "cached_score": {
                "total_score": 92,  # stale inflated headline
                "recommendation": "Shortlist",
                "matched_skills": ["Terraform"],
                "missing_skills": ["Kafka"],
                "breakdown": {
                    "Skill Match": 40,
                    "Experience Match": 40,
                    "Education Match": 50,
                    "Keyword Match": 40,
                    "Semantic Match": 40,
                },
                "summary": "Existing profile.",
            }
        }
    }
    ranking_service = _make_service()
    results = score_candidates(
        resumes,
        job,
        ranking_service,
        company_id="company-1",
        job_id="job-1",
        docs_by_email=docs_by_email,
    )
    assert len(results) == 1
    assert results[0].score.total_score == cols
    assert results[0].score.matched_skills == ["Terraform"]