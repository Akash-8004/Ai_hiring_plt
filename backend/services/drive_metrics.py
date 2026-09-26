from backend.core.models import JobDescription, ParsedResume
from backend.services.ai_ranker import AIRankingService
from backend.storage import database

_ranking_service = AIRankingService()


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
) -> dict:
    results = score_candidates_for_drive(candidate_resumes, current_job, company_id, job_id)

    candidate_docs = [
        database.get_candidate_doc(result.candidate.email, company_id, job_id) or {}
        for result in results
    ]

    metrics = derive_funnel_metrics(candidate_docs)
    metrics.update({
        "uploaded": len(candidate_resumes),
        "shortlisted": len([r for r in results if r.status == "Shortlisted"]),
        "rejected": len([r for r in results if r.status == "Rejected"]),
        "averageScore": round(sum(r.score.total_score for r in results) / len(results)) if results else 0,
        "candidate_count": len(candidate_resumes),
    })
    return metrics


def score_candidates_for_drive(
    candidate_resumes: list[ParsedResume],
    current_job: JobDescription,
    company_id: str,
    job_id: str,
):
    from backend.services.ranking import score_candidates
    return score_candidates(candidate_resumes, current_job, _ranking_service, company_id, job_id)
