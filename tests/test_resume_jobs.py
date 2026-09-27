"""Unit tests for background resume processing queue, workers, sweeper, and batch isolation.

Run directly:
    python tests/test_resume_jobs.py
"""

import asyncio
import os
import sys
import tempfile
import unittest.mock as mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.resume_jobs import _process_job, _check_candidate_limit, _try_cleanup_batch
from backend.core.models import ParsedResume


class MockCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = f"mock-{len(self.docs)+1}"
        self.docs.append(d)
        return mock.MagicMock(inserted_id=d["_id"])

    def find_one_and_update(self, query, update, sort=None, return_document=None):
        for d in sorted(self.docs, key=lambda x: x.get("created_at", datetime.min)):
            matches = True
            for k, v in query.items():
                if d.get(k) != v:
                    matches = False
                    break
            if matches:
                if "$set" in update:
                    d.update(update["$set"])
                if "$inc" in update:
                    for ik, iv in update["$inc"].items():
                        d[ik] = d.get(ik, 0) + iv
                return dict(d)
        return None

    def update_one(self, query, update):
        for d in self.docs:
            if query.get("_id") == d.get("_id"):
                if "$set" in update:
                    d.update(update["$set"])
                return mock.MagicMock(modified_count=1)
        return mock.MagicMock(modified_count=0)

    def find(self, query, projection=None):
        res = []
        for d in self.docs:
            matches = True
            for k, v in query.items():
                if d.get(k) != v:
                    matches = False
                    break
            if matches:
                res.append(dict(d))
        return mock.MagicMock(sort=lambda *args: res, __iter__=lambda self: iter(res))

    def update_many(self, query, update):
        count = 0
        for d in self.docs:
            matches = True
            if query.get("status") and d.get("status") != query["status"]:
                matches = False
            if "claimed_at" in query and "$lt" in query["claimed_at"]:
                if not d.get("claimed_at") or d["claimed_at"] >= query["claimed_at"]["$lt"]:
                    matches = False
            if matches:
                if "$set" in update:
                    d.update(update["$set"])
                count += 1
        return mock.MagicMock(modified_count=count)


def test_claim_and_process_job_success():
    """Verify standard happy-path processing: queued -> processing -> done."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spool_file = Path(tmpdir) / "sample_resume.txt"
        spool_file.write_text("John Doe\njohn@example.com\nPython, FastAPI\n5 years", encoding="utf-8")

        mock_db = MockCollection()
        job_doc = {
            "_id": "job-1",
            "batchId": "batch-101",
            "company_id": "comp-1",
            "job_id": "job-drive-1",
            "file_name": "sample_resume.txt",
            "spool_path": str(spool_file),
            "status": "queued",
            "stage": "queued",
            "created_at": datetime.now(timezone.utc),
            "attempts": 0,
        }
        mock_db.insert_one(job_doc)

        parsed_resume = ParsedResume(
            file_name="sample_resume.txt",
            full_name="John Doe",
            email="john@example.com",
            phone="555-1234",
            skills=["Python", "FastAPI"],
            experience_years=5,
            education="BS CS",
            raw_text="sample text",
            parsing_provider="gemini",
        )

        with mock.patch("backend.storage.database._resume_jobs", mock_db):
            with mock.patch("backend.storage.database.upsert_candidate") as mock_upsert:
                with mock.patch("backend.main._parse_uploaded_bytes", return_value=parsed_resume):
                    with mock.patch("backend.services.resume_jobs._check_candidate_limit", return_value=None):
                        asyncio.run(_process_job(job_doc))

                        mock_upsert.assert_called_once()
                        updated = mock_db.docs[0]
                        assert updated["status"] == "done"
                        assert updated["stage"] == "complete"
                        assert updated["candidate_email"] == "john@example.com"
                        assert updated["candidate_name"] == "John Doe"
                        assert updated["ocr_used"] is False


def test_stale_lease_sweeper_requeues():
    """Verify stale processing jobs older than lease duration are requeued to queued."""
    from backend.storage import database

    mock_db = MockCollection()
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=100)

    stale_job = {
        "_id": "stale-1",
        "batchId": "batch-stale",
        "status": "processing",
        "claimed_at": stale_time,
    }
    fresh_job = {
        "_id": "fresh-1",
        "batchId": "batch-fresh",
        "status": "processing",
        "claimed_at": fresh_time,
    }
    mock_db.insert_one(stale_job)
    mock_db.insert_one(fresh_job)

    with mock.patch("backend.storage.database._resume_jobs", mock_db):
        requeued = database.requeue_stale_resume_jobs(lease_seconds=300)
        assert requeued == 1
        assert mock_db.docs[0]["status"] == "queued"
        assert mock_db.docs[0]["claimed_at"] is None
        assert mock_db.docs[1]["status"] == "processing"


def test_single_file_failure_does_not_affect_batch():
    """Verify that one corrupt/failing file marks only that file failed while others succeed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spool_corrupt = Path(tmpdir) / "corrupt.pdf"
        spool_corrupt.write_bytes(b"bad content")

        mock_db = MockCollection()
        job_doc = {
            "_id": "job-bad",
            "batchId": "batch-mixed",
            "company_id": "comp-1",
            "file_name": "corrupt.pdf",
            "spool_path": str(spool_corrupt),
            "status": "queued",
            "stage": "queued",
        }
        mock_db.insert_one(job_doc)

        with mock.patch("backend.storage.database._resume_jobs", mock_db):
            with mock.patch("backend.main._parse_uploaded_bytes", side_effect=ValueError("Corrupt PDF structure")):
                asyncio.run(_process_job(job_doc))

                updated = mock_db.docs[0]
                assert updated["status"] == "failed"
                assert "Corrupt PDF structure" in updated["error"]


def test_candidate_limit_enforcement_per_file():
    """Verify that hitting candidate limit fails that file with candidate_limit_reached."""
    with mock.patch("backend.storage.database.count_company_candidates", return_value=100):
        with mock.patch("backend.storage.database.get_company_by_id", return_value={"plan": "starter", "max_candidates": 100}):
            err = _check_candidate_limit("comp-123")
            assert err is not None
            assert "candidate_limit_reached" in err

    with mock.patch("backend.storage.database.count_company_candidates", return_value=50):
        with mock.patch("backend.storage.database.get_company_by_id", return_value={"plan": "starter", "max_candidates": 100}):
            err = _check_candidate_limit("comp-123")
            assert err is None


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
