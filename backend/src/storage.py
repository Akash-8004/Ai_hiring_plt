from backend.src.ai_ranker import AIRankingService
from backend.src.models import CandidateResult, JobDescription, ParsedResume


def score_candidates(
    resumes: list[ParsedResume],
    job: JobDescription,
    ranking_service: AIRankingService,
) -> list[CandidateResult]:
    results: list[CandidateResult] = []
    seen_emails: set[str] = set()

    for resume in resumes:
        if resume.email.lower() in seen_emails:
            continue
        seen_emails.add(resume.email.lower())

        score = ranking_service.rank_resume(resume, job)
        status = "Shortlisted" if score.total_score >= job.threshold else "Rejected"
        results.append(CandidateResult(candidate=resume, score=score, status=status))

    return sorted(results, key=lambda item: item.score.total_score, reverse=True)
