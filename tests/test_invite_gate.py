"""Tests for the interview invitation pipeline gate.

Covers the three explicit outcomes of ``invite_candidate``:

* a candidate who PASSED the HR round is invited normally (no reason needed);
* a candidate who FAILED the HR round may still be invited to the technical
  round, but only as a recorded override carrying a reason;
* a candidate who never attempted the HR round is hard-blocked — an override
  cannot invent an attempt.

Also asserts the timeline rules are untouched by an override.

Runs without pytest::

    python tests/test_invite_gate.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.main as main  # noqa: E402

PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

USER = {
    "_id": "u1",
    "email": "admin@acme.com",
    "role": "company_admin",
    "company_id": "c1",
}

JOB = {
    "job_id": "j1",
    "threshold": 80,
    "hr_deadline": PAST,          # HR round closed -> technical unlocked
    "technical_deadline": FUTURE,
}

# For HR-round invites the HR deadline must still be open, otherwise the
# timeline check rejects the invite before the pipeline gate is ever reached.
HR_JOB = dict(JOB, hr_deadline=FUTURE)


def _candidate(**over):
    doc = {
        "email": "priya@example.com",
        "job_id": "j1",
        "full_name": "Priya",
        "cached_score": {"total_score": 13},
        "pipelineStage": "hr_failed",
        "hr_interview": {"status": "completed", "decision": "FAIL", "score": 13},
    }
    doc.update(over)
    return doc


def _call(candidate, interview_type, job=None, **kwargs):
    """Invoke the endpoint directly with the database and side effects stubbed."""
    calls = {"invites": [], "overrides": [], "audit": []}
    job_doc = dict(job if job is not None else JOB)

    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "get_job_doc", return_value=job_doc), \
         mock.patch.object(main.database, "set_candidate_invitation",
                           side_effect=lambda e, i, c=None, j=None: calls["invites"].append(("technical", i))), \
         mock.patch.object(main.database, "set_candidate_hr_invitation",
                           side_effect=lambda e, i, c=None, j=None: calls["invites"].append(("hr", i))), \
         mock.patch.object(main.database, "record_candidate_override",
                           side_effect=lambda e, entry, c=None, j=None: calls["overrides"].append(entry)), \
         mock.patch.object(main.database, "set_candidate_email_sent"), \
         mock.patch.object(main.database, "insert_audit_log"), \
         mock.patch.object(main, "_workspace_payload", return_value={"ok": True}), \
         mock.patch.object(main.email_service, "send_email",
                           return_value={"ok": True, "error": None}), \
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


def _status(exc):
    return getattr(exc, "status_code", None)


def _code(exc):
    detail = getattr(exc, "detail", None)
    return detail.get("code") if isinstance(detail, dict) else None


# ── Hard block: HR never attempted ──────────────────────────────────────────

def test_tech_blocked_when_hr_never_attempted():
    candidate = _candidate(hr_interview=None, pipelineStage="uploaded")
    try:
        _call(candidate, "technical")
    except main.HTTPException as exc:
        assert _status(exc) == 400
        assert "must complete the HR round" in str(exc.detail)
    else:
        raise AssertionError("expected a hard block when HR was never attempted")


def test_hard_block_cannot_be_bypassed_with_a_reason():
    """Supplying a valid reason must not conjure an HR attempt."""
    candidate = _candidate(hr_interview=None, pipelineStage="uploaded")
    try:
        _call(candidate, "technical", override_reason="recruiter_request")
    except main.HTTPException as exc:
        assert _status(exc) == 400
        assert "must complete the HR round" in str(exc.detail)
    else:
        raise AssertionError("an override must not bypass the never-attempted block")


def test_in_progress_hr_is_still_blocked():
    candidate = _candidate(hr_interview={"status": "in_progress", "decision": None})
    try:
        _call(candidate, "technical")
    except main.HTTPException as exc:
        assert _status(exc) == 400
    else:
        raise AssertionError("an in-progress HR round must not unlock technical")


# ── Normal progression: HR PASS needs no reason ─────────────────────────────

def test_tech_invite_after_hr_pass_needs_no_reason():
    candidate = _candidate(
        hr_interview={"status": "completed", "decision": "PASS", "score": 88},
        pipelineStage="hr_passed",
    )
    _, calls = _call(candidate, "technical")
    assert calls["overrides"] == [], "a clean pass must not be recorded as an override"
    assert calls["invites"] and calls["invites"][0][0] == "technical"


def test_hr_invite_for_shortlisted_candidate_needs_no_reason():
    candidate = _candidate(
        cached_score={"total_score": 90},
        hr_interview=None,
        pipelineStage="uploaded",
    )
    _, calls = _call(candidate, "hr", job=HR_JOB)
    assert calls["overrides"] == []
    assert calls["invites"] and calls["invites"][0][0] == "hr"


# ── Override: HR FAIL into the technical round ──────────────────────────────

def test_tech_invite_after_hr_fail_requires_a_reason():
    candidate = _candidate()
    try:
        _call(candidate, "technical")
    except main.HTTPException as exc:
        assert _status(exc) == 400
        assert _code(exc) == "override_reason_required", f"got code={_code(exc)!r}"
    else:
        raise AssertionError("a bypass without a reason must be rejected")


def test_tech_invite_after_hr_fail_with_reason_is_recorded():
    candidate = _candidate()
    _, calls = _call(
        candidate, "technical",
        override_reason="recruiter_request",
        override_note="Manager knows her from a previous role.",
    )
    assert len(calls["overrides"]) == 1, "the override must be persisted"
    entry = calls["overrides"][0]
    assert entry["round"] == "technical"
    assert entry["reason"] == "recruiter_request"
    assert entry["by_email"] == "admin@acme.com"
    assert entry["context"]["hr_decision"] == "FAIL"
    assert entry["context"]["resume_score"] == 13
    assert entry["note"].startswith("Manager knows")
    assert calls["invites"], "the invitation itself must still be issued"


def test_unknown_reason_code_is_rejected():
    candidate = _candidate()
    try:
        _call(candidate, "technical", override_reason="because_i_said_so")
    except main.HTTPException as exc:
        assert _status(exc) == 400
        assert _code(exc) == "invalid_override_reason"
    else:
        raise AssertionError("an unrecognised reason code must be rejected")


def test_override_never_counts_as_an_hr_pass():
    """The stored record keeps decision == FAIL, so metrics stay honest."""
    candidate = _candidate()
    _call(candidate, "technical", override_reason="referral")
    # The endpoint must not mutate the HR result itself.
    assert candidate["hr_interview"]["decision"] == "FAIL"


# ── Override: resume-rejected into the HR round ─────────────────────────────

def test_hr_invite_for_rejected_candidate_requires_a_reason():
    candidate = _candidate(cached_score={"total_score": 13}, hr_interview=None, pipelineStage="uploaded")
    try:
        _call(candidate, "hr", job=HR_JOB)
    except main.HTTPException as exc:
        assert _status(exc) == 400
        assert _code(exc) == "override_reason_required"
    else:
        raise AssertionError("a rejected resume needs a reason to be invited anyway")


def test_hr_invite_for_rejected_candidate_with_reason():
    candidate = _candidate(cached_score={"total_score": 13}, hr_interview=None, pipelineStage="uploaded")
    _, calls = _call(candidate, "hr", job=HR_JOB, override_reason="strong_resume")
    assert len(calls["overrides"]) == 1
    assert calls["overrides"][0]["round"] == "hr"
    assert calls["overrides"][0]["context"]["resume_status"] == "Rejected"
    assert calls["invites"] and calls["invites"][0][0] == "hr"


def test_missing_cached_score_is_treated_as_not_shortlisted():
    """Absent score must demand a reason rather than silently waving it by."""
    candidate = _candidate(cached_score=None, hr_interview=None, pipelineStage="uploaded")
    try:
        _call(candidate, "hr", job=HR_JOB)
    except main.HTTPException as exc:
        assert _code(exc) == "override_reason_required"
    else:
        raise AssertionError("a candidate with no cached score must not auto-pass the gate")


# ── Timeline rules are never bypassed by an override ────────────────────────

def test_technical_still_locked_while_hr_deadline_active():
    job = dict(JOB, hr_deadline=FUTURE)
    candidate = _candidate(hr_interview={"status": "completed", "decision": "FAIL", "score": 13})
    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "get_job_doc", return_value=job):
        try:
            main.invite_candidate(
                email=candidate["email"], interview_type="technical", send_email=False,
                user=USER, request=None, override_reason="role_priority",
            )
        except main.HTTPException as exc:
            assert _status(exc) == 403
            assert "unlocks after the HR deadline" in str(exc.detail)
        else:
            raise AssertionError("an override must not skip the round timeline")


def test_invite_blocked_after_deadline_passed():
    job = dict(JOB, technical_deadline=PAST)
    candidate = _candidate(hr_interview={"status": "completed", "decision": "PASS", "score": 90})
    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "get_job_doc", return_value=job):
        try:
            main.invite_candidate(
                email=candidate["email"], interview_type="technical", send_email=False,
                user=USER, request=None,
            )
        except main.HTTPException as exc:
            assert _status(exc) == 400
            assert "deadline has passed" in str(exc.detail)
        else:
            raise AssertionError("an expired deadline must block the invite")


def test_invite_blocked_when_round_deadline_unset():
    job = dict(JOB, technical_deadline=None)
    candidate = _candidate(hr_interview={"status": "completed", "decision": "PASS", "score": 90})
    with mock.patch.object(main, "_resolve_effective_job_id", return_value="j1"), \
         mock.patch.object(main.database, "get_candidate_doc", return_value=candidate), \
         mock.patch.object(main.database, "get_job_doc", return_value=job):
        try:
            main.invite_candidate(
                email=candidate["email"], interview_type="technical", send_email=False,
                user=USER, request=None,
            )
        except main.HTTPException as exc:
            assert "Set a technical deadline" in str(exc.detail)
        else:
            raise AssertionError("a missing deadline must block the invite")


def test_invalid_interview_type_rejected():
    candidate = _candidate()
    try:
        _call(candidate, "panel")
    except main.HTTPException as exc:
        assert _status(exc) == 400
    else:
        raise AssertionError("unknown interview types must be rejected")


def test_candidate_is_scoped_to_the_active_drive():
    """The same email in two drives must not resolve to the wrong one.

    Candidate documents are keyed by (email, company, job). The pipeline lists
    candidates for the ACTIVE drive, so the invite must resolve the candidate
    and its deadlines within that same drive. Looking the candidate up by email
    alone returned an arbitrary document — typically the older drive — and the
    invite was then validated against that drive's expired deadline, producing
    "The hr deadline has passed" for a candidate who had never been near one.
    """
    seen = {}

    def fake_get_candidate_doc(email, company_id=None, job_id=None):
        seen["job_id"] = job_id
        if job_id != "active-drive":
            return None
        # Shortlisted, so a plain "Invite" needs no override reason.
        return _candidate(job_id="active-drive", cached_score={"total_score": 90},
                          hr_interview=None, pipelineStage="uploaded")

    active_job = {"job_id": "active-drive", "threshold": 80,
                  "hr_deadline": FUTURE, "technical_deadline": FUTURE}
    old_job = {"job_id": "old-drive", "threshold": 80,
               "hr_deadline": PAST, "technical_deadline": PAST}

    with mock.patch.object(main.database, "get_candidate_doc",
                           side_effect=fake_get_candidate_doc), \
         mock.patch.object(main, "_resolve_effective_job_id", return_value="active-drive"), \
         mock.patch.object(main.database, "get_job_doc",
                           side_effect=lambda c, j: active_job if j == "active-drive" else old_job), \
         mock.patch.object(main.database, "set_candidate_hr_invitation"), \
         mock.patch.object(main.database, "insert_audit_log"), \
         mock.patch.object(main, "_workspace_payload", return_value={"ok": True}), \
         mock.patch.object(main.email_service, "log_email_send"):
        main.invite_candidate(
            email="priya@example.com", interview_type="hr", send_email=False,
            user=USER, request=None,
        )

    assert seen["job_id"] == "active-drive", (
        "the candidate lookup must be scoped to the active drive, not email-only"
    )


def test_candidate_missing_from_active_drive_is_rejected():
    """A candidate present only in another drive must not be invited silently."""
    with mock.patch.object(main.database, "get_candidate_doc", return_value=None), \
         mock.patch.object(main, "_resolve_effective_job_id", return_value="active-drive"):
        try:
            main.invite_candidate(
                email="ghost@example.com", interview_type="hr", send_email=False,
                user=USER, request=None,
            )
        except main.HTTPException as exc:
            assert _status(exc) == 404
            assert "current job drive" in str(exc.detail)
        else:
            raise AssertionError("must not fall back to a candidate from another drive")


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
