"""Regression tests for server-side enforcement of the view_pipeline permission.

A sub-user who was only granted "conduct_interviews" must not be able to read
candidate PII (names, emails, phones, resumes), scores, or interview invitation
tokens from ``GET /api/workspace``. Hiding the Pipeline menu item is not enough.

Runs without pytest::

    python tests/test_workspace_pipeline_permission.py
"""

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.main as main  # noqa: E402
from backend.core.models import JobDescription, ParsedResume  # noqa: E402

COMPANY_ID = "507f1f77bcf86cd799439011"
JOB_ID = "j1"

JOB_DICT = {
    "job_id": JOB_ID,
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

CONDUCT_ONLY_USER = {
    "_id": "u-conduct",
    "email": "interviewer@acme.com",
    "role": "sub_user",
    "company_id": COMPANY_ID,
    "permissions": ["conduct_interviews"],
}

PIPELINE_USER = {
    "_id": "u-pipeline",
    "email": "recruiter@acme.com",
    "role": "sub_user",
    "company_id": COMPANY_ID,
    "permissions": ["conduct_interviews", "view_pipeline"],
}

ADMIN_USER = {
    "_id": "u-admin",
    "email": "admin@acme.com",
    "role": "company_admin",
    "company_id": COMPANY_ID,
    "permissions": [],
}

CANDIDATES = [
    {
        "email": f"candidate{i}@example.com",
        "full_name": f"Candidate {i}",
        "phone": f"+1555000000{i}",
        "skills": ["Python"],
        "raw_text": f"Secret resume text for candidate {i}",
        "job_id": JOB_ID,
        "company_id": COMPANY_ID,
        "cached_score": {
            "total_score": 85,
            "matched_skills": ["Python"],
            "missing_skills": [],
            "summary": "Strong fit",
        },
        "pipelineStage": "shortlisted",
        "invitation": {"token": f"TECH-TOKEN-{i}", "type": "technical"},
        "hr_invitation": {"token": f"HR-TOKEN-{i}", "type": "hr"},
    }
    for i in range(3)
]


def _parsed(candidate):
    return ParsedResume(
        file_name=f"{candidate['email']}.pdf",
        full_name=candidate["full_name"],
        email=candidate["email"],
        phone=candidate["phone"],
        skills=candidate["skills"],
        experience_years=3,
        education="B.S. in CS",
        raw_text=candidate["raw_text"],
    )


def _payload_for(user):
    docs = {c["email"]: c for c in CANDIDATES}
    resumes = [_parsed(c) for c in CANDIDATES]
    with mock.patch.object(main.database, "get_job_by_id", return_value=JOB_MODEL), \
         mock.patch.object(main.database, "get_job_doc", return_value=JOB_DICT), \
         mock.patch.object(main.database, "set_active_drive"), \
         mock.patch.object(main.database, "get_active_drive", return_value=JOB_ID), \
         mock.patch.object(main.database, "load_candidates", return_value=resumes), \
         mock.patch.object(main.database, "get_candidate_docs_batch", return_value=docs), \
         mock.patch.object(main.database, "list_jobs", return_value=[JOB_DICT]), \
         mock.patch.object(main.database, "count_candidates_by_job", return_value={JOB_ID: 3}), \
         mock.patch.object(main.database, "list_jd_requests", return_value=[]), \
         mock.patch.object(main.database, "get_company_by_id", return_value={
             "name": "Acme Corp", "plan": "starter", "status": "active",
         }), \
         mock.patch.object(main.database, "get_plan_limits", return_value={"max_candidates": 100}), \
         mock.patch.object(main.database, "count_company_users", return_value=2), \
         mock.patch.object(main.database, "get_company_credits", return_value={}), \
         mock.patch.object(main.database, "get_plan_prices", return_value={}), \
         mock.patch.object(main.database, "set_candidate_scoring") as scoring, \
         mock.patch.object(main.ranking_service, "rank_resume") as rank:
        payload = main._workspace_payload(company_id=COMPANY_ID, user=user, job_id=JOB_ID)
    return payload, scoring, rank


def _assert_no_candidate_data(test_name, payload):
    serialized = json.dumps(payload, default=str).lower()
    for candidate in CANDIDATES:
        for leaked in (
            candidate["email"],
            candidate["phone"],
            candidate["full_name"],
            f"TECH-TOKEN-{CANDIDATES.index(candidate)}",
            f"HR-TOKEN-{CANDIDATES.index(candidate)}",
            candidate["raw_text"],
        ):
            assert leaked.lower() not in serialized, (
                f"{test_name}: leaked {leaked!r} in workspace payload"
            )


def test_conduct_only_user_gets_no_candidates_or_metrics():
    payload, scoring, rank = _payload_for(CONDUCT_ONLY_USER)
    assert payload["candidates"] == []
    assert payload["metrics"] == {}
    assert all(drive["candidate_count"] == 0 for drive in payload["drives"])
    # Withholding data must not trigger expensive scoring on the way out.
    scoring.assert_not_called()
    rank.assert_not_called()


def test_conduct_only_user_payload_contains_no_pii_or_tokens():
    payload, _, _ = _payload_for(CONDUCT_ONLY_USER)
    _assert_no_candidate_data("conduct-only", payload)
    # The workspace scaffolding is still returned so the app can load.
    assert payload["company"]["name"] == "Acme Corp"
    assert payload["job"]["title"] == "Software Engineer"


def test_pipeline_permission_still_returns_candidates():
    payload, _, _ = _payload_for(PIPELINE_USER)
    assert len(payload["candidates"]) == len(CANDIDATES)
    assert payload["metrics"]["uploaded"] == len(CANDIDATES)
    assert payload["candidates"][0]["invitation"]["token"] == "TECH-TOKEN-0"


def test_company_admin_still_returns_candidates():
    payload, _, _ = _payload_for(ADMIN_USER)
    assert len(payload["candidates"]) == len(CANDIDATES)
    assert payload["candidates"][0]["Email"] == CANDIDATES[0]["email"]


def test_missing_user_is_treated_as_no_pipeline_access():
    payload, _, _ = _payload_for(None)
    assert payload["candidates"] == []
    assert payload["metrics"] == {}
    _assert_no_candidate_data("no-user", payload)


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
