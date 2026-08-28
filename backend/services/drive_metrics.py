from backend.core.models import JobDescription, ParsedResume
from backend.services.ai_ranker import AIRankingService
from backend.storage import database

_ranking_service = AIRankingService()


def compute_drive_metrics(
    candidate_resumes: list[ParsedResume],
    company_id: str,
    job_id: str,
    current_job: JobDescription,
) -> dict:
    results = score_candidates_for_drive(candidate_resumes, current_job, company_id, job_id)
    hr_invited = 0
    hr_interviewed = 0
    hr_passed = 0
    tech_invited = 0
    tech_interviewed = 0
    tech_passed = 0
    hired = 0

    for result in results:
        doc = database.get_candidate_doc(
            result.candidate.email, company_id, job_id
        ) or {}
        stage = doc.get("pipelineStage", "uploaded")
        if stage in {"hr_invited", "hr_passed", "hr_failed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_invited += 1
        if stage in {"hr_passed", "hr_failed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_interviewed += 1
        if stage in {"hr_passed", "invited", "tech_passed", "tech_failed", "hired"}:
            hr_passed += 1
        if stage in {"invited", "tech_passed", "tech_failed", "hired"}:
            tech_invited += 1
        if stage in {"tech_passed", "tech_failed", "hired"}:
            tech_interviewed += 1
        if stage in {"tech_passed", "hired"}:
            tech_passed += 1
        if stage == "hired":
            hired += 1

    shortlisted = len([r for r in results if r.status == "Shortlisted"])
    rejected = len([r for r in results if r.status == "Rejected"])
    average = round(sum(r.score.total_score for r in results) / len(results)) if results else 0

    return {
        "uploaded": len(candidate_resumes),
        "shortlisted": shortlisted,
        "rejected": rejected,
        "averageScore": average,
        "hrInvited": hr_invited,
        "hrInterviewed": hr_interviewed,
        "hrPassed": hr_passed,
        "techInvited": tech_invited,
        "techInterviewed": tech_interviewed,
        "techPassed": tech_passed,
        "hired": hired,
        "candidate_count": len(candidate_resumes),
    }


def score_candidates_for_drive(
    candidate_resumes: list[ParsedResume],
    current_job: JobDescription,
    company_id: str,
    job_id: str,
):
    from backend.services.ranking import score_candidates
    return score_candidates(candidate_resumes, current_job, _ranking_service, company_id, job_id)
