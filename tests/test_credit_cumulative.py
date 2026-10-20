"""Tests for cumulative, monthly interview credit consumption.

Credit rule: 1 credit = 600 seconds (10 minutes) of ACTUAL interview time.
Durations accumulate across all candidates of a company within a billing
period; leftover seconds carry forward to the next completed interview.
"""

from backend.storage import database

CID = "64b000000000000000000001"


def test_single_short_interview_consumes_nothing():
    credits, remainder = database.compute_cumulative_credits(0, 5 * 60)
    assert credits == 0
    assert remainder == 300


def test_five_plus_nine_plus_twelve_minutes():
    # 5 + 9 + 12 = 26 minutes -> 2 credits, 6 minutes carried forward.
    remainder = 0
    total_credits = 0
    for minutes in (5, 9, 12):
        credits, remainder = database.compute_cumulative_credits(remainder, minutes * 60)
        total_credits += credits
    assert total_credits == 2
    assert remainder == 6 * 60


def test_carry_forward_across_boundary():
    # 26 min consumed 2 credits and carried 6 min. Next 4 min -> 1 credit, 0 left.
    credits, remainder = database.compute_cumulative_credits(6 * 60, 4 * 60)
    assert credits == 1
    assert remainder == 0


def test_six_plus_four_minutes_is_one_credit():
    credits, remainder = database.compute_cumulative_credits(0, 6 * 60)
    assert (credits, remainder) == (0, 360)
    credits, remainder = database.compute_cumulative_credits(remainder, 4 * 60)
    assert (credits, remainder) == (1, 0)


def test_exact_block_consumes_credit_with_no_remainder():
    credits, remainder = database.compute_cumulative_credits(0, 10 * 60)
    assert (credits, remainder) == (1, 0)


def test_long_interview_consumes_multiple_credits():
    # 45 minutes -> 4 credits, 5 minutes carried forward.
    credits, remainder = database.compute_cumulative_credits(0, 45 * 60)
    assert credits == 4
    assert remainder == 5 * 60


def test_negative_durations_are_clamped():
    assert database.compute_cumulative_credits(0, -30) == (0, 0)
    assert database.compute_cumulative_credits(-100, 30) == (0, 30)


def test_fresh_bucket_has_zero_remainder():
    bucket = database._fresh_credits_bucket(100, "2026-10")
    assert bucket["remainder_seconds"] == 0


def test_monthly_reset_clears_remainder(monkeypatch):
    """A period change resets credits and wipes the carried-forward seconds."""
    old = {
        "_id": CID,
        "plan": "starter",
        "credits": {
            "period": "2000-01",
            "allowance": 500,
            "used": 3,
            "remaining": 497,
            "overage": 0,
            "adjustments": 0,
            "remainder_seconds": 123,
        },
    }
    written = {}

    class _Col:
        def update_one(self, flt, update, **kwargs):
            written["credits"] = update["$set"]["credits"]

    monkeypatch.setattr(database, "get_company_by_id", lambda cid: old)
    monkeypatch.setattr(database, "insert_audit_log", lambda entry: None)
    monkeypatch.setattr(database, "_companies", _Col())

    result = database.reset_company_credits_if_due(CID)
    assert result["remainder_seconds"] == 0
    assert result["period"] != "2000-01"
    assert written["credits"]["remainder_seconds"] == 0


def test_same_period_backfills_missing_remainder(monkeypatch):
    company = {
        "_id": CID,
        "plan": "starter",
        "credits": {
            "period": database._month_period(),
            "allowance": 500,
            "used": 10,
            "remaining": 490,
            "overage": 0,
            "adjustments": 0,
        },
    }
    monkeypatch.setattr(database, "get_company_by_id", lambda cid: company)
    result = database.reset_company_credits_if_due(CID)
    assert result["remainder_seconds"] == 0


def test_record_interview_usage_is_idempotent(monkeypatch):
    """Replaying the same event_id must not consume credits twice."""
    event_id = f"{CID}:j1:a@x.com:hr:2026-01-01T00:00:00+00:00"
    processed = {
        "event_id": event_id,
        "status": "processed",
        "credits_consumed": 2,
        "previous_remainder_seconds": 0,
        "new_remainder_seconds": 360,
        "duration_seconds": 1200,
    }

    class _Col:
        def find_one(self, flt):
            if flt.get("event_id") == event_id:
                return processed
            return None

        def insert_one(self, doc):
            raise AssertionError("must not attempt to insert a duplicate event")

    monkeypatch.setattr(database, "_interview_usage", _Col())
    result = database.record_interview_usage(
        company_id=CID,
        candidate_email="a@x.com",
        interview_type="hr",
        event_id=event_id,
        duration_seconds=1200,
    )
    assert result["idempotent"] is True
    assert result["credits_consumed"] == 2
    assert result["new_remainder_seconds"] == 360


def test_record_interview_usage_rolls_back_when_insufficient(monkeypatch):
    """When credits are insufficient the seconds are preserved, not lost."""
    company = {
        "_id": CID,
        "plan": "starter",
        "credits": {
            "period": database._month_period(),
            "allowance": 5,
            "used": 5,
            "remaining": 0,
            "overage": 0,
            "adjustments": 0,
            "remainder_seconds": 0,
        },
    }

    class _Companies:
        def find_one_and_update(self, flt, pipeline, **kwargs):
            return None

    class _InterviewUsage:
        def __init__(self):
            self.inserted = []

        def find_one(self, flt):
            return None

        def insert_one(self, doc):
            self.inserted.append(doc)

        def find_one_and_update(self, flt, update, **kwargs):
            return {"event_id": flt.get("event_id"), "status": "processing"}

        def update_one(self, flt, update):
            self.updated = update

    monkeypatch.setattr(database, "get_company_by_id", lambda cid: company)
    monkeypatch.setattr(database, "reset_company_credits_if_due", lambda cid: company["credits"])
    monkeypatch.setattr(database, "_companies", _Companies())
    monkeypatch.setattr(database, "_interview_usage", _InterviewUsage())
    monkeypatch.setattr(database, "log_usage", lambda *a, **k: None)

    result = database.record_interview_usage(
        company_id=CID,
        candidate_email="a@x.com",
        interview_type="hr",
        event_id="evt-insufficient",
        duration_seconds=1200,
    )
    assert result["credits_consumed"] == 0


def test_atomic_pipeline_consumes_only_full_blocks(monkeypatch):
    """The atomic update debits floor(seconds/600) and keeps the remainder."""
    captured = {}

    class _Companies:
        def find_one_and_update(self, flt, pipeline, **kwargs):
            captured["pipeline"] = pipeline
            return {
                "credits": {
                    "last_event_id": "evt1",
                    "last_consumed_credits": 2,
                    "last_previous_remainder_seconds": 0,
                    "last_new_remainder_seconds": 360,
                }
            }

    company = {
        "_id": CID,
        "plan": "starter",
        "credits": {
            "period": database._month_period(),
            "allowance": 500,
            "used": 0,
            "remaining": 500,
            "overage": 0,
            "adjustments": 0,
            "remainder_seconds": 0,
        },
    }

    class _InterviewUsage:
        def find_one(self, flt):
            return None

        def insert_one(self, doc):
            return None

        def find_one_and_update(self, flt, update, **kwargs):
            return {"event_id": flt.get("event_id"), "status": "processing"}

        def update_one(self, flt, update):
            return None

    monkeypatch.setattr(database, "get_company_by_id", lambda cid: company)
    monkeypatch.setattr(database, "reset_company_credits_if_due", lambda cid: company["credits"])
    monkeypatch.setattr(database, "_companies", _Companies())
    monkeypatch.setattr(database, "_interview_usage", _InterviewUsage())
    monkeypatch.setattr(database, "log_usage", lambda *a, **k: None)

    result = database.record_interview_usage(
        company_id=CID,
        candidate_email="a@x.com",
        interview_type="hr",
        event_id="evt1",
        duration_seconds=26 * 60,
    )
    assert result["credits_consumed"] == 2
    assert result["new_remainder_seconds"] == 360
    assert captured["pipeline"]


def test_concurrent_delivery_does_not_double_charge(monkeypatch):
    """A second concurrent delivery of the same event is a no-op."""
    event_id = "evt-concurrent"
    state = {
        "event_id": event_id,
        "status": "processing",
        "credits_consumed": 1,
        "previous_remainder_seconds": 0,
        "new_remainder_seconds": 120,
        "duration_seconds": 480,
    }

    calls = {"find": 0}

    class _InterviewUsage:
        def find_one(self, flt):
            # First look: not yet visible to this worker. Later: the row that
            # the concurrent worker already claimed.
            calls["find"] += 1
            return None if calls["find"] == 1 else state

        def insert_one(self, doc):
            # Unique index rejects the duplicate event.
            raise Exception("duplicate key")

        def find_one_and_update(self, flt, update, **kwargs):
            # Claim never succeeds: the first worker owns the event.
            return None

        def update_one(self, flt, update):
            raise AssertionError("must not process an already-claimed event")

    monkeypatch.setattr(database, "_interview_usage", _InterviewUsage())
    monkeypatch.setattr(database, "get_company_by_id", lambda cid: {"_id": CID, "plan": "starter", "credits": {}})
    result = database.record_interview_usage(
        company_id=CID,
        candidate_email="a@x.com",
        interview_type="hr",
        event_id=event_id,
        duration_seconds=480,
    )
    assert result["idempotent"] is True
    assert result["credits_consumed"] == 1


def test_get_interview_usage_filters_processed(monkeypatch):
    captured = {}

    class _Col:
        def count_documents(self, query):
            captured["query"] = query
            return 0

        def find(self, query):
            captured["find"] = query
            return self

        def sort(self, *a, **k):
            return self

        def skip(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return []

    monkeypatch.setattr(database, "_interview_usage", _Col())
    out = database.get_interview_usage(CID, page=1, limit=10)
    assert out["total"] == 0
    assert captured["query"]["status"] == "processed"
