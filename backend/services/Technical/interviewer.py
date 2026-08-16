from backend.core.models import JobDescription, ParsedResume
from backend.services.interview_agent import InterviewAgent
from backend.services.Technical.prompts import build_technical_interviewer_prompt

interview_agent = InterviewAgent()


def get_interviewer_prompt(interview_type: str, job: JobDescription, resume: ParsedResume) -> str:
    """Returns system prompt based on interview type (technical or hr)."""
    if interview_type == "technical":
        return build_technical_interviewer_prompt(job, resume)
    return interview_agent.build_interviewer_prompt(job, resume)
