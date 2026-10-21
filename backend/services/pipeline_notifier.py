"""Notify company staff when a candidate passes the final (technical) round.

Called from ``backend.main._run_interview_evaluation`` right after a round
result is persisted.  Rounds run HR first, Technical second — so the
Technical round is always the LAST round.  A candidate is "to be hired" as
soon as the technical round decision is ``PASS``, even when the HR round
was bypassed by an admin override (overrides only skip the gate; they never
write a decision, so HR may simply be absent).

Recipients: the company admin AND every staff member of the company,
regardless of which permissions they hold.

Best-effort only: every step is wrapped so an SMTP/DB failure can never
break the interview evaluation flow.
"""

import logging

from backend.config import frontend_base_url
from backend.services import email_service
from backend.services.email_templates import candidate_hired_email
from backend.storage import database

logger = logging.getLogger(__name__)

EMAIL_TYPE = "candidate_hired"


def _passed(decision) -> bool:
    return str(decision or "").strip().upper() == "PASS"


def candidate_passed_final_round(candidate: dict) -> bool:
    """True when the candidate's technical (final) round is PASS.

    HR status is irrelevant — it may be PASS, FAIL, or absent entirely
    (bypassed by an admin pipeline override).
    """
    return _passed((candidate.get("technical_interview") or {}).get("decision"))


def _resolve_recipients(company_id: str) -> list[dict]:
    """Company admin + every staff member, deduped by email."""
    seen: set[str] = set()
    recipients: list[dict] = []
    for user in database.list_users_by_company(company_id):
        email = str(user.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append({
            "email": email,
            "name": user.get("name", ""),
            "role": user.get("role", ""),
        })
    return recipients


def _hr_round_label(hr: dict) -> str:
    """Human label for the HR round — it may not exist (bypassed/never run)."""
    if not hr:
        return "Bypassed / Not taken"
    decision = str(hr.get("decision") or "").strip().upper()
    return decision or "Not taken"


def notify_candidate_hired(
    candidate_email: str,
    company_id: str | None,
    job_id: str | None = None,
) -> dict:
    """Send the candidate-hired notification. Only meaningful after a
    technical-round PASS; safe to call after any round.

    The one-time claim (``database.claim_candidate_hired_notification``)
    guarantees a single notification per candidate even if evaluation is
    re-run or the round is later reset and re-passed within the same doc.
    """
    try:
        if not company_id:
            return {"ok": False, "skipped": "no company_id"}

        candidate = database.get_candidate_doc(candidate_email, company_id, job_id) or {}
        if not candidate_passed_final_round(candidate):
            return {"ok": False, "skipped": "final (technical) round not passed"}

        # Atomic one-time claim — first caller wins, everyone else skips.
        if not database.claim_candidate_hired_notification(
            candidate_email, company_id, job_id
        ):
            return {"ok": False, "skipped": "already notified"}

        recipients = _resolve_recipients(str(company_id))
        if not recipients:
            logger.info("Candidate-hired: no recipients for company %s", company_id)
            return {"ok": False, "skipped": "no recipients"}

        company = database.get_company_by_id(str(company_id)) or {}
        company_name = company.get("name", "your company")

        job_title = ""
        if job_id:
            job_doc = database.get_job_doc(str(company_id), job_id) or {}
            job_title = str(job_doc.get("title") or "")
        if not job_title:
            job_title = str(candidate.get("job_title") or "")

        hr = candidate.get("hr_interview") or {}
        tech = candidate.get("technical_interview") or {}

        candidate_name = str(
            candidate.get("full_name") or candidate.get("name") or candidate_email
        )
        dashboard_url = f"{frontend_base_url().rstrip('/')}/app/dashboard"

        subject, html_body, plain_body = candidate_hired_email(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            company_name=company_name,
            job_title=job_title,
            hr_label=_hr_round_label(hr),
            hr_score=hr.get("score", "N/A") if hr else "N/A",
            tech_decision=str(tech.get("decision", "")),
            tech_score=tech.get("score", "N/A"),
            dashboard_url=dashboard_url,
        )

        sent, failed = 0, 0
        for recipient in recipients:
            result = email_service.send_email(
                recipient["email"], subject, html_body, plain_body
            )
            ok = bool(result.get("ok"))
            sent += 1 if ok else 0
            failed += 0 if ok else 1
            email_service.log_email_send(
                to_email=recipient["email"],
                subject=subject,
                email_type=EMAIL_TYPE,
                status="sent" if ok else "failed",
                error_message=result.get("error"),
                metadata={
                    "company_id": str(company_id),
                    "job_id": job_id,
                    "candidate_email": candidate_email,
                    "recipient_role": recipient.get("role", ""),
                    "company_name": company_name,
                    "job_title": job_title,
                },
            )

        logger.info(
            "Candidate-hired notification for %s: %d sent, %d failed, %d recipients",
            candidate_email, sent, failed, len(recipients),
        )
        return {"ok": True, "sent": sent, "failed": failed, "recipients": len(recipients)}

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "Failed to notify candidate-hired for %s: %s", candidate_email, exc
        )
        return {"ok": False, "error": str(exc)}
