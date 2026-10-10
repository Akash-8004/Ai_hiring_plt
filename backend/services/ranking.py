from backend.core.models import CandidateResult, JobDescription, ParsedResume, ResumeScore
from backend.services.ai_ranker import AIRankingService
from backend.storage import database


def score_candidates(
    resumes: list[ParsedResume],
    job: JobDescription,
    ranking_service: AIRankingService,
    company_id: str | None = None,
    job_id: str | None = None,
    docs_by_email: dict[str, dict] | None = None,
) -> list[CandidateResult]:
    results: list[CandidateResult] = []
    seen_emails: set[str] = set()

    # Pre-fetch candidate docs in one batch query if not provided
    if company_id and docs_by_email is None and resumes:
        docs_by_email = database.get_candidate_docs_batch(
            [r.email for r in resumes], company_id, job_id
        )

    for resume in resumes:
        if resume.email.lower() in seen_emails:
            continue
        seen_emails.add(resume.email.lower())

        score = None

        # Try to use cached score if available
        if company_id:
            doc = docs_by_email.get(resume.email) if docs_by_email else database.get_candidate_doc(resume.email, company_id, job_id)
            if doc:
                cached = doc.get("cached_score") or doc.get("scoring")
                if cached:
                    try:
                        total = cached.get("total_score") if "total_score" in cached else cached.get("score")
                        if total is not None and "breakdown" in cached:
                            score = ResumeScore(
                                total_score=total,
                                recommendation=cached.get("recommendation", "Review / Reject"),
                                matched_skills=cached.get("matched_skills", []),
                                missing_skills=cached.get("missing_skills", []),
                                breakdown=cached.get("breakdown", {}),
                                summary=cached.get("summary", cached.get("explanation", "")),
                            )
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
