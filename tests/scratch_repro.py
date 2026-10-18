"""Exhaustive reproduction of every 'Still Invite' scenario."""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backend.main as main

PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
FUTURE_3D = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
USER = {"_id": "u1", "email": "admin@acme.com", "role": "company_admin", "company_id": "c1"}


def _call(candidate, interview_type, job, **kwargs):
    calls = {"invites": [], "overrides": [], "amends": []}
    job_doc = dict(job)
    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "get_job_doc", return_value=job_doc), \
         mock.patch.object(main.database, "set_candidate_invitation",
                           side_effect=lambda e, i, c=None, j=None: calls["invites"].append(("technical", i))), \
         mock.patch.object(main.database, "set_candidate_hr_invitation",
                           side_effect=lambda e, i, c=None, j=None: calls["invites"].append(("hr", i))), \
         mock.patch.object(main.database, "set_candidate_invitation_expiry",
                           side_effect=lambda e, t, exp, src="per_candidate", c=None, j=None: calls["amends"].append((t, exp, src))), \
         mock.patch.object(main.database, "record_candidate_override",
                           side_effect=lambda e, entry, c=None, j=None: calls["overrides"].append(entry)), \
         mock.patch.object(main.database, "set_candidate_email_sent"), \
         mock.patch.object(main.database, "insert_audit_log"), \
         mock.patch.object(main, "_workspace_payload", return_value={"ok": True}), \
         mock.patch.object(main.email_service, "send_email", return_value={"ok": True, "error": None}), \
         mock.patch.object(main.email_service, "log_email_send"):
        result = main.invite_candidate(
            email=candidate["email"],
            interview_type=interview_type,
            send_email=False,
            user=USER,
            request=None,
            **kwargs,
        )
    return result, calls


def test(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")


# ── Scenario 2: Drive deadline ACTIVE, Still-Invite (override only, no deadline) ─

def scenario_2_new_candidate():
    """Drive active + rejected + override reason -> new invitation with drive deadline."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": FUTURE, "technical_deadline": FUTURE}
    # No deadline param -> backend falls back to drive deadline
    _, calls = _call(candidate, "hr", job, override_reason="strong_resume")
    assert calls["invites"], "invitation must be created"
    inv = calls["invites"][0][1]
    assert inv["expires_at"] == FUTURE, f"expires_at must be drive deadline, got {inv['expires_at']}"
    assert inv["deadline_source"] == "drive", f"source must be 'drive', got {inv['deadline_source']}"

test("Scenario 2: New candidate, drive active, no per-candidate deadline", scenario_2_new_candidate)


# ── Scenario 3A: Drive deadline PASSED, new candidate, per-candidate deadline ─

def scenario_3a_new_candidate():
    """Drive passed + rejected + override + per-candidate deadline -> new invitation with per-candidate."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": PAST, "technical_deadline": FUTURE}
    _, calls = _call(candidate, "hr", job, override_reason="strong_resume", deadline=FUTURE_3D)
    assert calls["invites"], "invitation must be created"
    inv = calls["invites"][0][1]
    assert inv["expires_at"] == FUTURE_3D, f"expires_at must be per-candidate, got {inv['expires_at']}"
    assert inv["deadline_source"] == "per_candidate"

test("Scenario 3A: New candidate, drive passed, per-candidate deadline", scenario_3a_new_candidate)


# ── Scenario 3B: Drive passed, NO per-candidate deadline -> should be BLOCKED ─

def scenario_3b_no_deadline():
    """Drive passed + rejected + no per-candidate deadline -> 400."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": PAST, "technical_deadline": FUTURE}
    try:
        _call(candidate, "hr", job, override_reason="strong_resume")
        raise AssertionError("Expected 400 when drive deadline passed and no per-candidate deadline")
    except main.HTTPException as exc:
        assert exc.status_code == 400, f"Expected 400, got {exc.status_code}"

test("Scenario 3B: Drive passed, no per-candidate deadline -> 400", scenario_3b_no_deadline)


# ── Scenario 3C: Existing invitation + drive passed + per-candidate deadline -> AMEND or 400? ─

def scenario_3c_existing_token_expired():
    """Existing invitation (expired) + per-candidate deadline -> should 400 'already expired'."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
        "hr_invitation": {"token": "old-token", "link": "http://x/?interview=old-token", "expires_at": PAST, "deadline_source": "drive"},
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": PAST, "technical_deadline": FUTURE}
    try:
        _call(candidate, "hr", job, override_reason="strong_resume", deadline=FUTURE_3D)
        raise AssertionError("Expected 400 for expired invitation")
    except main.HTTPException as exc:
        assert exc.status_code == 400
        assert "already expired" in str(exc.detail)
        print(f"          -> Got expected 400: {exc.detail}")

test("Scenario 3C: Existing expired token + per-candidate deadline -> 400", scenario_3c_existing_token_expired)


# ── Scenario 3D: Existing invitation + drive ACTIVE + per-candidate deadline -> AMEND ─

def scenario_3d_existing_token_active_amend():
    """Existing invitation (active) + different per-candidate deadline -> amend."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
        "hr_invitation": {"token": "existing-token", "link": "http://x/?interview=existing-token", "expires_at": FUTURE, "deadline_source": "drive"},
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": PAST, "technical_deadline": FUTURE}
    _, calls = _call(candidate, "hr", job, override_reason="strong_resume", deadline=FUTURE_3D)
    assert calls["amends"], "set_candidate_invitation_expiry must be called"
    assert calls["amends"][0][1] == FUTURE_3D
    assert calls["amends"][0][2] == "per_candidate"
    assert not calls["invites"], "should NOT create a new invitation"

test("Scenario 3D: Existing active token + new per-candidate deadline -> amend", scenario_3d_existing_token_active_amend)


# ── Scenario 3E: Existing invitation + drive ACTIVE + NO per-candidate deadline -> keep existing ─

def scenario_3e_existing_token_no_deadline():
    """Existing invitation (active) + no per-candidate deadline -> keeps drive deadline."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "uploaded", "hr_interview": None,
        "hr_invitation": {"token": "existing-token", "link": "http://x/?interview=existing-token", "expires_at": FUTURE, "deadline_source": "drive"},
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": FUTURE, "technical_deadline": FUTURE}
    _, calls = _call(candidate, "hr", job, override_reason="strong_resume")
    assert not calls["amends"], "expiry should NOT be amended"
    assert not calls["invites"], "should NOT create a new invitation"

test("Scenario 3E: Existing active token, no per-candidate deadline → no change", scenario_3e_existing_token_no_deadline)


# ── Scenario 4: Technical round, HR failed, drive passed, per-candidate ─

def scenario_4_tech_after_hr_fail():
    """Tech Still-Invite after HR FAIL, tech drive passed, per-candidate deadline."""
    candidate = {
        "email": "rejected@example.com", "job_id": "j1", "full_name": "Rejected",
        "cached_score": {"total_score": 13}, "pipelineStage": "hr_failed",
        "hr_interview": {"status": "completed", "decision": "FAIL", "score": 13},
    }
    job = {"job_id": "j1", "threshold": 80, "hr_deadline": PAST, "technical_deadline": PAST}
    _, calls = _call(candidate, "technical", job, override_reason="recruiter_request", deadline=FUTURE_3D)
    assert calls["invites"], "technical invitation must be created"
    inv = calls["invites"][0][1]
    assert inv["expires_at"] == FUTURE_3D
    assert inv["deadline_source"] == "per_candidate"

test("Scenario 4: Tech Still-Invite, HR FAIL, tech passed, per-candidate", scenario_4_tech_after_hr_fail)
