"""Regression tests for the drive funnel metrics.

Focus: the funnel counters must be derived from stored interview *facts*, never
from the mutable ``pipelineStage`` field.

The bug this guards against: ``pipelineStage`` is a single "most recent stage"
marker, so inviting a candidate who FAILED the HR round (an admin override)
overwrote the stage to ``invited``. The old counters inferred the funnel from
that string, so advancing the stage retroactively implied the HR round had been
passed — a bypassed candidate was counted in "HR Passed".

Runs without pytest so the suite works in this repo as-is::

    python tests/test_drive_metrics.py

It is also collected normally by pytest if it is ever added.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.drive_metrics import derive_funnel_metrics  # noqa: E402


def _doc(**over):
    """Build a minimal candidate doc with sensible empty defaults."""
    base = {
        "email": "c@example.com",
        "pipelineStage": "uploaded",
        "hr_invitation": None,
        "invitation": None,
        "hr_interview": None,
        "technical_interview": None,
        "overrides": [],
    }
    base.update(over)
    return base


def _invitation(token="t"):
    return {"token": token, "link": f"https://x/{token}"}


def _interview(decision, score=50, status="completed"):
    return {"status": status, "decision": decision, "score": score}


# ── Normal progression ──────────────────────────────────────────────────────

def test_full_happy_path():
    docs = [
        _doc(
            pipelineStage="hired",
            hr_invitation=_invitation("h"),
            invitation=_invitation("t"),
            hr_interview=_interview("PASS", 80),
            technical_interview=_interview("PASS", 90),
        )
    ]
    m = derive_funnel_metrics(docs)
    assert m["hrInvited"] == 1
    assert m["hrInterviewed"] == 1
    assert m["hrPassed"] == 1
    assert m["techInvited"] == 1
    assert m["techInterviewed"] == 1
    assert m["techPassed"] == 1
    assert m["hired"] == 1


def test_uploaded_only():
    m = derive_funnel_metrics([_doc(), _doc(email="d@example.com")])
    assert m["hrInvited"] == 0
    assert m["hrInterviewed"] == 0
    assert m["hrPassed"] == 0
    assert m["techInvited"] == 0
    assert m["techPassed"] == 0
    assert m["hired"] == 0


def test_empty_candidate_list():
    m = derive_funnel_metrics([])
    assert m["hrInvited"] == 0 and m["hrPassed"] == 0 and m["hired"] == 0


# ── The reported bug: HR FAILED, then overridden into the technical round ───

def test_hr_fail_then_tech_override_does_not_count_as_hr_pass():
    """The exact reported regression: Priya failed HR, was invited to tech.

    Her stage becomes 'invited', but 'HR Passed' must stay 0.
    """
    docs = [
        _doc(
            pipelineStage="invited",
            hr_invitation=_invitation("h"),
            invitation=_invitation("t"),
            hr_interview=_interview("FAIL", 13),
            overrides=[{"round": "technical", "reason": "recruiter_request"}],
        )
    ]
    m = derive_funnel_metrics(docs)
    assert m["hrPassed"] == 0, "a bypassed candidate must not count as an HR pass"
    assert m["hrInvited"] == 1
    assert m["hrInterviewed"] == 1
    assert m["techInvited"] == 1
    assert m["techPassed"] == 0


def test_tech_override_never_satisfies_hr_when_hr_never_happened():
    """Someone pushed straight to tech without sitting HR.

    None of the HR counters may be incremented.
    """
    docs = [
        _doc(
            pipelineStage="invited",
            invitation=_invitation("t"),
            overrides=[{"round": "technical", "reason": "role_priority"}],
        )
    ]
    m = derive_funnel_metrics(docs)
    assert m["hrInvited"] == 0
    assert m["hrInterviewed"] == 0
    assert m["hrPassed"] == 0
    assert m["techInvited"] == 1


def test_hr_invitation_without_token_is_not_counted():
    docs = [_doc(hr_invitation={"link": "https://x"}, pipelineStage="hr_invited")]
    m = derive_funnel_metrics(docs)
    assert m["hrInvited"] == 0


# ── The core invariant: metrics are independent of pipelineStage ────────────

def test_metrics_ignore_pipeline_stage_entirely():
    """Identical facts must produce identical metrics for any pipelineStage.

    This is the property the old stage-inferred implementation violated.
    """
    facts = dict(
        hr_invitation=_invitation("h"),
        invitation=_invitation("t"),
        hr_interview=_interview("FAIL", 13),
        overrides=[{"round": "technical", "reason": "referral"}],
    )
    baseline = derive_funnel_metrics([_doc(pipelineStage="uploaded", **facts)])
    for stage in ("hr_invited", "hr_passed", "hr_failed", "invited", "tech_failed", "hired", "anything_else"):
        assert derive_funnel_metrics([_doc(pipelineStage=stage, **facts)]) == baseline, (
            f"pipelineStage={stage!r} changed the metrics"
        )


def test_hired_stage_does_not_hide_a_passed_candidate():
    """Re-inviting must not erase the hire; the decision is the source of truth."""
    passed = _doc(
        pipelineStage="invited",
        hr_invitation=_invitation("h"),
        hr_interview=_interview("PASS", 80),
        technical_interview=_interview("PASS", 88),
    )
    m = derive_funnel_metrics([passed])
    assert m["hired"] == 1
    assert m["techPassed"] == 1


# ── Interview in progress must not count as a decision ──────────────────────

def test_in_progress_interview_is_not_a_pass_or_fail():
    docs = [
        _doc(
            pipelineStage="hr_invited",
            hr_invitation=_invitation("h"),
            hr_interview={"status": "in_progress", "decision": None},
        )
    ]
    m = derive_funnel_metrics(docs)
    assert m["hrInterviewed"] == 0, "only completed interviews count as interviewed"
    assert m["hrPassed"] == 0


# ── Override visibility ─────────────────────────────────────────────────────

def test_override_counted_once_per_round_per_candidate():
    docs = [
        _doc(
            overrides=[
                {"round": "technical", "reason": "referral"},
                {"round": "technical", "reason": "role_priority"},
                {"round": "hr", "reason": "referral"},
            ]
        )
    ]
    m = derive_funnel_metrics(docs)
    assert m["techOverridden"] == 1, "repeated overrides must not inflate the count"
    assert m["hrOverridden"] == 1


def test_overrides_do_not_change_pass_counters():
    plain = derive_funnel_metrics([_doc(hr_interview=_interview("FAIL", 20))])
    with_override = derive_funnel_metrics(
        [_doc(hr_interview=_interview("FAIL", 20), overrides=[{"round": "technical"}])]
    )
    assert plain["hrPassed"] == with_override["hrPassed"] == 0
    assert plain["hrInterviewed"] == with_override["hrInterviewed"] == 1


def test_malformed_docs_do_not_crash():
    docs = [
        {},
        _doc(overrides=None),
        _doc(hr_invitation="not-a-dict", hr_interview=None),
        _doc(overrides=[{}, {"round": "hr"}, {"round": "unknown"}]),
    ]
    m = derive_funnel_metrics(docs)
    assert m["hrInvited"] == 0
    assert m["hrOverridden"] == 1


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
