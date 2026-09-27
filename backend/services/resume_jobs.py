import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import load_env
from backend.storage import database

logger = logging.getLogger(__name__)

_tasks: list[asyncio.Task] = []
_shutdown = False
_kick_event: asyncio.Event | None = None


def kick_workers() -> None:
    if _kick_event is not None:
        _kick_event.set()


async def start_workers(app) -> None:
    global _shutdown, _kick_event
    _shutdown = False
    load_env()
    concurrency = int(os.getenv("OCR_CONCURRENCY", "3"))
    _kick_event = asyncio.Event()

    requeued = database.requeue_stale_resume_jobs(
        int(os.getenv("RESUME_JOB_LEASE_SECONDS", "300"))
    )
    if requeued:
        logger.info("Requeued %d stale resume jobs on startup", requeued)

    sem = asyncio.Semaphore(concurrency)

    async def worker_loop():
        while not _shutdown:
            try:
                _kick_event.clear()
                job = database.claim_resume_job()
                if not job:
                    try:
                        await asyncio.wait_for(_kick_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    continue
                async with sem:
                    await _process_job(job)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in resume worker loop")
                await asyncio.sleep(2)

    for i in range(concurrency):
        task = asyncio.create_task(worker_loop(), name=f"resume-worker-{i}")
        _tasks.append(task)

    sweeper = asyncio.create_task(_sweeper_loop(), name="resume-sweeper")
    _tasks.append(sweeper)
    logger.info("Started %d resume workers + sweeper", concurrency)


async def stop_workers() -> None:
    global _shutdown
    _shutdown = True
    for task in _tasks:
        task.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    logger.info("Resume workers stopped")


async def _sweeper_loop() -> None:
    load_env()
    lease_seconds = int(os.getenv("RESUME_JOB_LEASE_SECONDS", "300"))
    while not _shutdown:
        try:
            await asyncio.sleep(60)
            requeued = database.requeue_stale_resume_jobs(lease_seconds)
            if requeued:
                logger.info("Sweeper requeued %d stale resume jobs", requeued)
                kick_workers()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in resume job sweeper")


async def _process_job(job: dict) -> None:
    job_id = job["_id"]
    file_name = job["file_name"]
    spool_path = job.get("spool_path", "")
    company_id = job.get("company_id")
    drive_job_id = job.get("job_id")

    try:
        database.update_resume_job(job_id, {"stage": "extracting"})

        spool = Path(spool_path)
        if not spool.is_file():
            raise FileNotFoundError(f"Spool file missing: {spool_path}")

        contents = await asyncio.to_thread(spool.read_bytes)

        database.update_resume_job(job_id, {"stage": "parsing"})

        from backend.main import _parse_uploaded_bytes
        resume = await asyncio.to_thread(_parse_uploaded_bytes, file_name, contents)

        ocr_used = "-ocr" in (resume.parsing_provider or "")
        database.update_resume_job(job_id, {
            "stage": "upserting",
            "ocr_used": ocr_used,
            "candidate_email": resume.email,
            "candidate_name": resume.full_name,
        })

        limit_err = _check_candidate_limit(company_id)
        if limit_err:
            raise RuntimeError(limit_err)

        database.upsert_candidate(resume, company_id=company_id, job_id=drive_job_id)

        ttl_hours = int(os.getenv("RESUME_JOB_TTL_HOURS", "24"))
        database.update_resume_job(job_id, {
            "status": "done",
            "stage": "complete",
            "finished_at": datetime.now(timezone.utc),
            "expireAt": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        })
        logger.info("Processed resume job %s -> %s (%s)", job_id, resume.email, file_name)

    except Exception as exc:
        logger.exception("Resume job %s failed: %s", job_id, file_name)
        ttl_hours = int(os.getenv("RESUME_JOB_TTL_HOURS", "24"))
        database.update_resume_job(job_id, {
            "status": "failed",
            "error": str(exc)[:500],
            "finished_at": datetime.now(timezone.utc),
            "expireAt": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        })

    _try_cleanup_batch(job.get("batchId"))


def _check_candidate_limit(company_id: str | None) -> str | None:
    if not company_id:
        return None
    count = database.count_company_candidates(company_id)
    company = database.get_company_by_id(company_id) or {}
    plan = company.get("plan", "starter")
    max_candidates = company.get("max_candidates")
    if max_candidates is None:
        max_candidates = database.get_plan_limits(plan).get("max_candidates", 100)
    if count >= max_candidates:
        return f"candidate_limit_reached ({count}/{max_candidates})"
    return None


def _try_cleanup_batch(batch_id: str | None) -> None:
    if not batch_id:
        return
    jobs = database.get_resume_jobs_by_batch(batch_id)
    if not jobs:
        return
    if all(j["status"] in ("done", "failed") for j in jobs):
        spool_dir = Path(__file__).resolve().parent.parent.parent / "temp_files" / "resumes" / batch_id
        if spool_dir.is_dir():
            try:
                shutil.rmtree(spool_dir)
                logger.info("Cleaned up spool directory for batch %s", batch_id)
            except Exception:
                logger.warning("Failed to clean up spool dir %s", spool_dir)
