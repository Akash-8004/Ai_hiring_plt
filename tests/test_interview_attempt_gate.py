"""Tests for the single-attempt interview gate (issue 19).

A candidate who closes the tab mid-interview must NOT be able to re-open the
link, preview the questions and retry. The attempt is consumed server-side when
the live relay connects, and a recruiter can re-open it explicitly.

Covers:

* ``_ensure_attempt_available`` — blocks a spent attempt and a completed round,
  allows a fresh one and resolves the correct round from the token;
* the public ``/api/interview/session/{token}`` payload — reports ``locked`` and
  never leaks the coding questions;
* ``POST /api/candidates/{email}/interview/reset`` — re-opens a started round,
  refuses a completed one and refuses a never-started one.

Runs without pytest::

    python tests/test_interview_attempt_gate.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.main as main  # noqa: E402

FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

USER = {
    "_id": "u1",
    "email": "admin@acme.com",
    "role": "company_admin",
    "company_id": "c1",
}


def _status(exc):
    return getattr(exc, "status_code", None)


def _code(exc):
    detail = getattr(exc, "detail", None)
    return detail.get("code") if isinstance(detail, dict) else None


def _tech_candidate(**over):
    doc = {
        "email": "priya@example.com",
        "job_id": "j1",
        "full_name": "Priya Sharma",
        "invitation": {
            "token": "TECH-TOKEN",
            "type": "technical",
            "expires_at": FUTURE,
        },
    }
    doc.update(over)
    return doc


def _resume():
    return SimpleNamespace(email="priya@example.com", full_name="Priya Sharma")


def _job():
    return SimpleNamespace(
        title="Backend Engineer",
        custom_questions=[
            {"id": "q1", "question": "Reverse a linked list", "topic": "DSA"},
        ],
    )


# ── Guard: _ensure_attempt_available ────────────────────────────────────────

def test_fresh_interview_is_allowed():
    interview_type = main._ensure_attempt_available("TECH-TOKEN", _tech_candidate())
    assert interview_type == "technical"


def test_hr_token_resolves_to_hr_round():
    doc = {
        "invitation": {"token": "TECH-TOKEN", "type": "technical"},
        "hr_invitation": {"token": "HR-TOKEN", "type": "hr"},
    }
    assert main._ensure_attempt_available("HR-TOKEN", doc) == "hr"


def test_consumed_attempt_is_blocked():
    doc = _tech_candidate(
        technical_interview={"status": "in_progress", "attempts_used": 1}
    )
    try:
        main._ensure_attempt_available("TECH-TOKEN", doc)
    except main.HTTPException as exc:
        assert _status(exc) == 409
        assert _code(exc) == "attempt_consumed"
    else:
        raise AssertionError("a spent attempt must be blocked")


def test_abandoned_attempt_is_still_blocked():
    """Closing the tab leaves status in_progress + attempts_used=1."""
    doc = _tech_candidate(
        technical_interview={
            "status": "in_progress",
            "attempts_used": 1,
            "abandoned_at": FUTURE,
        }
    )
    try:
        main._ensure_attempt_available("TECH-TOKEN", doc)
    except main.HTTPException as exc:
        assert _code(exc) == "attempt_consumed"
    else:
        raise AssertionError("an abandoned attempt must stay locked")


def test_completed_interview_is_blocked():
    doc = _tech_candidate(technical_interview={"status": "completed"})
    try:
        main._ensure_attempt_available("TECH-TOKEN", doc)
    except main.HTTPException as exc:
        assert _status(exc) == 409
        assert _code(exc) == "interview_completed"
    else:
        raise AssertionError("a completed interview must be blocked")


# ── Public session payload ──────────────────────────────────────────────────

def _call_session(candidate, token="TECH-TOKEN"):
    with mock.patch.object(main, "_candidate_ref_for_token", return_value=("priya@example.com", "c1")), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "load_candidates", return_value=[_resume()]), \
         mock.patch.object(main.database, "get_job_by_id", return_value=_job()), \
         mock.patch.object(main.database, "load_job", return_value=_job()), \
         mock.patch.object(main.database, "get_company_by_id", return_value={"name": "Acme", "settings": {}}):
        return main.interview_session(token)


def test_session_fresh_is_open_and_hides_questions():
    payload = _call_session(_tech_candidate())
    assert payload["completed"] is False
    assert payload["locked"] is False
    assert payload["customQuestions"] == [], "questions must not leak before start"
    assert payload["hasCodingQuestions"] is True


def test_session_started_is_locked():
    candidate = _tech_candidate(
        technical_interview={"status": "in_progress", "attempts_used": 1}
    )
    payload = _call_session(candidate)
    assert payload["locked"] is True
    assert payload["completed"] is False
    assert payload["customQuestions"] == []


def test_session_completed_shows_result_not_locked():
    candidate = _tech_candidate(
        technical_interview={
            "status": "completed",
            "decision": "PASS",
            "score": 88,
            "attempts_used": 1,
        }
    )
    payload = _call_session(candidate)
    assert payload["completed"] is True
    assert payload["locked"] is False
    assert payload["decision"] == "PASS"
    assert payload["score"] == 88


# ── Recruiter reset endpoint ────────────────────────────────────────────────

def _call_reset(candidate, interview_type="technical"):
    calls = {"reset": [], "audit": []}

    def fake_reset(email, itype, company_id=None, job_id=None):
        calls["reset"].append((email, itype, company_id, job_id))

    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "reset_candidate_interview", side_effect=fake_reset), \
         mock.patch.object(main, "_active_drive_id", return_value="j1"), \
         mock.patch.object(main, "_workspace_payload", return_value={"ok": True}), \
         mock.patch.object(main, "log_activity", side_effect=lambda **kw: calls["audit"].append(kw)):
        result = main.reopen_candidate_interview(
            email=candidate["email"],
            interview_type=interview_type,
            user=USER,
            request=None,
        )
    return result, calls


def test_reset_reopens_a_started_interview():
    candidate = _tech_candidate(
        technical_interview={"status": "in_progress", "attempts_used": 1}
    )
    result, calls = _call_reset(candidate)
    assert result == {"ok": True}
    assert calls["reset"] == [("priya@example.com", "technical", "c1", "j1")]
    assert calls["audit"] and calls["audit"][0]["action"] == "candidate.interview_reopened"


def test_reset_refuses_a_completed_interview():
    candidate = _tech_candidate(
        technical_interview={"status": "completed", "decision": "PASS", "score": 90}
    )
    try:
        _call_reset(candidate)
    except main.HTTPException as exc:
        assert _status(exc) == 409
    else:
        raise AssertionError("a completed interview must not be resettable")


def test_reset_refuses_a_never_started_interview():
    candidate = _tech_candidate()
    try:
        _call_reset(candidate)
    except main.HTTPException as exc:
        assert _status(exc) == 400
    else:
        raise AssertionError("a never-started interview has nothing to reset")


def test_reset_rejects_unknown_interview_type():
    candidate = _tech_candidate(
        technical_interview={"status": "in_progress", "attempts_used": 1}
    )
    try:
        _call_reset(candidate, interview_type="panel")
    except main.HTTPException as exc:
        assert _status(exc) == 400
    else:
        raise AssertionError("unknown interview types must be rejected")


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
