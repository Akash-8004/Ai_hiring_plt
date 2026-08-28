from backend.core.models import CandidateResult, JobDescription, ParsedResume, ResumeScore
from backend.services.ai_ranker import AIRankingService
from backend.storage import database


def score_candidates(
    resumes: list[ParsedResume],
    job: JobDescription,
    ranking_service: AIRankingService,
    company_id: str | None = None,
    job_id: str | None = None,
) -> list[CandidateResult]:
    results: list[CandidateResult] = []
    seen_emails: set[str] = set()

    for resume in resumes:
        if resume.email.lower() in seen_emails:
            continue
        seen_emails.add(resume.email.lower())

        score = None

        # Try to use cached score if available
        if company_id:
            doc = database.get_candidate_doc(resume.email, company_id, job_id)
            if doc and doc.get("cached_score"):
                try:
                    score = ResumeScore(**doc["cached_score"])
                except (TypeError, KeyError):
                    score = None

        if score is None:
            score = ranking_service.rank_resume(resume, job)
            # Cache the new score in MongoDB
            if company_id:
                database.set_candidate_score(
                    resume.email,
                    {
                        "total_score": score.total_score,
                        "recommendation": score.recommendation,
                        "matched_skills": score.matched_skills,
                        "missing_skills": score.missing_skills,
                        "breakdown": score.breakdown,
                        "summary": score.summary,
                    },
                    company_id,
                    job_id,
                )

        status = "Shortlisted" if score.total_score >= job.threshold else "Rejected"
        results.append(CandidateResult(candidate=resume, score=score, status=status))

    return sorted(results, key=lambda item: item.score.total_score, reverse=True)
