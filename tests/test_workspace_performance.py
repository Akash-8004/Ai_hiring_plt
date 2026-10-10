"""Tests for Bug #10: GET /api/workspace performance optimizations.

Verifies:
1. _workspace_payload fetches candidate docs in batch (no N+1 get_candidate_doc calls).
2. compute_drive_metrics reuses passed candidate_results and candidate_docs without duplicate scoring.
3. _workspace_payload uses fast local ranking fallback when > 5 candidates are unscored to prevent timeout.
4. Payload structure maintains all expected keys for frontend consumers.
"""

import sys
from pathlib import Path
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.main as main
from backend.services.drive_metrics import compute_drive_metrics
from backend.services.ai_ranker import get_local_ranking_service
from backend.core.models import JobDescription, ParsedResume, ResumeScore, CandidateResult

COMPANY_ID = "507f1f77bcf86cd799439011"

USER = {
    "_id": "u1",
    "email": "admin@acme.com",
    "role": "company_admin",
    "company_id": COMPANY_ID,
}

JOB_DICT = {
    "job_id": "j1",
    "title": "Software Engineer",
    "department": "Engineering",
    "location": "Remote",
    "experience_years": 3,
    "description": "Python backend engineer needed.",
    "threshold": 75,
    "skills": ["Python", "Docker"],
    "required_skills": ["Python"],
    "nice_to_have_skills": [],
    "education": "B.S. in CS",
}

JOB_MODEL = JobDescription(
    title="Software Engineer",
    department="Engineering",
    location="Remote",
    experience_years=3,
    required_skills=["Python"],
    nice_to_have_skills=[],
    education="B.S. in CS",
    description="Python backend engineer needed.",
    threshold=75,
)


def _make_candidate(i, has_score=True):
    email = f"dev{i}@example.com"
    cand = {
        "email": email,
        "full_name": f"Candidate {i}",
        "job_id": "j1",
        "company_id": COMPANY_ID,
        "skills": ["Python"],
        "raw_text": f"Candidate {i} resume with Python experience.",
        "pipelineStage": "applied",
        "hr_interview": None,
        "technical_interview": None,
    }
    if has_score:
        cand["cached_score"] = {
            "total_score": 85,
            "overall_score": 85,
            "skill_match": 90,
            "skills": ["Python"],
            "decision": "STRONG PASS",
        }
    return cand


def _to_parsed_resume(c):
    return ParsedResume(
        file_name=f"{c['email']}.pdf",
        full_name=c["full_name"],
        email=c["email"],
        phone="1234567890",
        skills=c["skills"],
        experience_years=3,
        education="B.S. in CS",
        raw_text=c["raw_text"],
    )


def test_compute_drive_metrics_reuses_precomputed():
    """Verify compute_drive_metrics does zero scoring or DB queries when precomputed data is passed."""
    cands = [_make_candidate(i) for i in range(5)]
    parsed_resumes = [_to_parsed_resume(c) for c in cands]
    results = [
        CandidateResult(
            candidate=pr,
            score=ResumeScore(
                total_score=85,
                recommendation="Strong Pass",
                matched_skills=["Python"],
                missing_skills=[],
                breakdown={},
                summary="Good fit",
            ),
            status="Shortlisted",
        )
        for pr in parsed_resumes
    ]

    with mock.patch("backend.services.drive_metrics.score_candidates_for_drive") as mock_score, \
         mock.patch("backend.services.drive_metrics.database.get_candidate_doc") as mock_get_doc:
        
        metrics = compute_drive_metrics(
            candidate_resumes=parsed_resumes,
            company_id=COMPANY_ID,
            job_id="j1",
            current_job=JOB_MODEL,
            candidate_results=results,
            candidate_docs=cands,
        )

        mock_score.assert_not_called()
        mock_get_doc.assert_not_called()
        assert metrics["uploaded"] == 5
        assert metrics["shortlisted"] == 5
        assert metrics["averageScore"] == 85


def test_workspace_payload_batch_loading_and_no_duplicate_scoring():
    """Verify _workspace_payload fetches docs in batch and does not re-score already scored candidates."""
    cands = [_make_candidate(i, has_score=True) for i in range(10)]
    parsed = [_to_parsed_resume(c) for c in cands]
    docs_by_email = {c["email"]: c for c in cands}

    with mock.patch("backend.main.database.get_company_by_id", return_value={"name": "Acme Corp"}), \
         mock.patch("backend.main.database.list_jobs", return_value=[JOB_DICT]), \
         mock.patch("backend.main.database.set_active_drive"), \
         mock.patch("backend.main.database.load_candidates", return_value=parsed), \
         mock.patch("backend.main.database.get_candidate_docs_batch", return_value=docs_by_email) as mock_batch, \
         mock.patch("backend.main.database.get_candidate_doc") as mock_single_doc, \
         mock.patch("backend.main.database.count_candidates_by_job", return_value={"j1": 10}), \
         mock.patch("backend.main.database.list_jd_requests", return_value=[]), \
         mock.patch("backend.main.AIRankingService.rank_resume") as mock_rank:

        payload = main._workspace_payload(company_id=COMPANY_ID, user=USER, job_id="j1")

        # 1. Batch load was called
        mock_batch.assert_called_once_with([c["email"] for c in cands], COMPANY_ID, "j1")
        # 2. Individual get_candidate_doc was NOT called per candidate
        mock_single_doc.assert_not_called()
        # 3. No scoring was triggered since all 10 candidates have cached_score
        mock_rank.assert_not_called()

        # 4. Payload structure is complete
        assert "candidates" in payload
        assert "metrics" in payload
        assert "drives" in payload
        assert "deadlines" in payload
        assert "company" in payload
        assert len(payload["candidates"]) == 10
        assert payload["metrics"]["uploaded"] == 10


def test_workspace_payload_fast_local_ranking_for_unscored_batch():
    """Verify that when > 5 unscored candidates are present, local ranker is used to prevent timeout."""
    cands = [_make_candidate(i, has_score=False) for i in range(8)]
    parsed = [_to_parsed_resume(c) for c in cands]
    docs_by_email = {c["email"]: c for c in cands}

    local_ranker = get_local_ranking_service()

    with mock.patch("backend.main.database.get_company_by_id", return_value={"name": "Acme Corp"}), \
         mock.patch("backend.main.database.list_jobs", return_value=[JOB_DICT]), \
         mock.patch("backend.main.database.set_active_drive"), \
         mock.patch("backend.main.database.load_candidates", return_value=parsed), \
         mock.patch("backend.main.database.get_candidate_docs_batch", return_value=docs_by_email), \
         mock.patch("backend.main.database.count_candidates_by_job", return_value={"j1": 8}), \
         mock.patch("backend.main.database.list_jd_requests", return_value=[]), \
         mock.patch("backend.main.database.set_candidate_score") as mock_save_score, \
         mock.patch.object(local_ranker, "rank_resume", wraps=local_ranker.rank_resume) as mock_local_rank:

        payload = main._workspace_payload(company_id=COMPANY_ID, user=USER, job_id="j1")

        # Fast local ranker was called instead of gemini ranker
        assert mock_local_rank.call_count == 8
        assert mock_save_score.call_count == 8
        assert len(payload["candidates"]) == 8
