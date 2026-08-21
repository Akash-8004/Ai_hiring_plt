from backend.core.models import JobDescription, ParsedResume
from backend.services.Technical.prompts import build_technical_interviewer_prompt
from backend.services.HR_Round.prompts import build_hr_interviewer_prompt


def get_interviewer_prompt(interview_type: str, job: JobDescription, resume: ParsedResume) -> str:
    """Returns system prompt based on interview type (technical or hr)."""
    if interview_type == "technical":
        return build_technical_interviewer_prompt(job, resume)
    return build_hr_interviewer_prompt(job, resume)
