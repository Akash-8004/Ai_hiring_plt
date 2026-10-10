from typing import Any
from backend.core.models import JobDescription, ParsedResume
from backend.services.ai_ranker import AIRankingService, get_ranking_service
from backend.storage import database

_ranking_service = get_ranking_service()


def _as_dict(value) -> dict:
    """Coerce a stored field to a dict.

    These fields are always written as dicts, but legacy or hand-edited
    documents must not be able to 500 the whole dashboard.
    """
    return value if isinstance(value, dict) else {}


def derive_funnel_metrics(candidate_docs: list[dict]) -> dict:
    """Derive the interview funnel counters from stored per-candidate facts.

    Each counter is computed from an independently persisted fact (an
    invitation token, an interview record, or a decision value) rather than
    from ``pipelineStage``.

    ``pipelineStage`` is a single *mutable* "most recent stage" marker, so it
    cannot express history: advancing it (for example when an admin overrides
    a failed HR round and invites the candidate to the technical round)
    retroactively implies that every earlier gate was passed. Inferring the
    funnel from it therefore counted a bypassed candidate as an HR pass. These
    counters now stay correct regardless of which overrides have been applied.

    Kept as a pure function (plain dicts in, plain dicts out) so it can be
    unit-tested without a live database.
    """
    hr_invited = hr_interviewed = hr_passed = 0
    tech_invited = tech_interviewed = tech_passed = hired = 0
    hr_overridden = tech_overridden = 0

    for doc in candidate_docs:
        if not isinstance(doc, dict):
            continue

        has_hr_invite = bool(_as_dict(doc.get("hr_invitation")).get("token"))
        has_tech_invite = bool(_as_dict(doc.get("invitation")).get("token"))

        hr_interview = _as_dict(doc.get("hr_interview"))
        tech_interview = _as_dict(doc.get("technical_interview"))
        hr_decision = hr_interview.get("decision")
        tech_decision = tech_interview.get("decision")

        if has_hr_invite:
            hr_invited += 1
        if hr_interview.get("status") == "completed":
            hr_interviewed += 1
        # Only a genuine HR PASS counts. A candidate whose technical invitation
        # was issued by an admin override keeps decision == "FAIL" and is not
        # counted here.
        if hr_decision == "PASS":
            hr_passed += 1

        if has_tech_invite:
            tech_invited += 1
        if tech_interview.get("status") == "completed":
            tech_interviewed += 1
        if tech_decision == "PASS":
            tech_passed += 1
            hired += 1

        raw_overrides = doc.get("overrides")
        overrides = raw_overrides if isinstance(raw_overrides, list) else []
        if any(_as_dict(entry).get("round") == "hr" for entry in overrides):
            hr_overridden += 1
        if any(_as_dict(entry).get("round") == "technical" for entry in overrides):
            tech_overridden += 1

    return {
        "hrInvited": hr_invited,
        "hrInterviewed": hr_interviewed,
        "hrPassed": hr_passed,
        "techInvited": tech_invited,
        "techInterviewed": tech_interviewed,
        "techPassed": tech_passed,
        "hired": hired,
        "hrOverridden": hr_overridden,
        "techOverridden": tech_overridden,
    }


def compute_drive_metrics(
    candidate_resumes: list[ParsedResume],
    company_id: str,
    job_id: str,
    current_job: JobDescription,
    candidate_results: list[Any] | None = None,
    candidate_docs: list[dict] | None = None,
) -> dict:
    if candidate_results is None:
        candidate_results = score_candidates_for_drive(candidate_resumes, current_job, company_id, job_id)

    if candidate_docs is None:
        emails = [
            r.candidate.email if hasattr(r, "candidate") else getattr(r, "email", "")
            for r in candidate_results
        ]
        emails = [e for e in emails if e]
        docs_map = database.get_candidate_docs_batch(emails, company_id, job_id)
        candidate_docs = list(docs_map.values())

    metrics = derive_funnel_metrics(candidate_docs)

    total_candidates = len(candidate_resumes)
    shortlisted_count = 0
    rejected_count = 0
    scores: list[int] = []

    threshold = getattr(current_job, "threshold", 80)
    for r in candidate_results:
        score_obj = getattr(r, "score", None)
        score_val = getattr(score_obj, "total_score", getattr(score_obj, "overall", None))
        if score_val is not None:
            scores.append(score_val)
        status = getattr(r, "status", None)
        if status == "Shortlisted" or (status is None and score_val is not None and score_val >= threshold):
            shortlisted_count += 1
        elif status == "Rejected" or (status is None and score_val is not None and score_val < threshold):
            rejected_count += 1

    metrics.update({
        "uploaded": total_candidates,
        "shortlisted": shortlisted_count,
        "rejected": rejected_count,
        "averageScore": round(sum(scores) / len(scores)) if scores else 0,
        "candidate_count": total_candidates,
    })
    return metrics


def score_candidates_for_drive(
    candidate_resumes: list[ParsedResume],
    current_job: JobDescription,
    company_id: str,
    job_id: str,
    docs_by_email: dict[str, dict] | None = None,
    ranking_service: AIRankingService | None = None,
):
    from backend.services.ranking import score_candidates
    svc = ranking_service or _ranking_service
    return score_candidates(
        candidate_resumes,
        current_job,
        svc,
        company_id,
        job_id,
        docs_by_email=docs_by_email,
    )
