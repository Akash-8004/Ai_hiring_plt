import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from backend.src.models import JobDescription, ParsedResume, ResumeScore


class AIRankingService:
    """Resume ranking service with Gemini-first screening and local fallback."""

    def __init__(self) -> None:
        _load_dotenv()
        self.provider = os.getenv("AI_PROVIDER", "local").strip().lower()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.last_provider_used = "local"
        self.last_error = ""

    def rank_resume(self, resume: ParsedResume, job: JobDescription) -> ResumeScore:
        if self.provider == "gemini" and self.api_key:
            try:
                self.last_provider_used = "gemini"
                self.last_error = ""
                return self._rank_with_gemini(resume, job)
            except Exception as exc:
                score = self._rank_locally(resume, job)
                self.last_provider_used = "local-fallback"
                self.last_error = _friendly_error(exc)
                return score

        self.last_provider_used = "local"
        self.last_error = "" if self.provider == "local" else "Gemini API key is not configured."
        return self._rank_locally(resume, job)

    def _rank_locally(self, resume: ParsedResume, job: JobDescription) -> ResumeScore:
        required = {_normalize_skill(skill) for skill in job.required_skills if skill.strip()}
        resume_skills = {_normalize_skill(skill) for skill in resume.skills if skill.strip()}

        matched = sorted(required.intersection(resume_skills))
        missing = sorted(required.difference(resume_skills))

        skill_score = round((len(matched) / max(len(required), 1)) * 100)
        keyword_score = self._keyword_overlap(resume.raw_text, job.description)
        experience_score = min(100, round((resume.experience_years / max(job.experience_years, 1)) * 100))
        education_score = self._education_score(resume.education, job.education)
        semantic_score = round((skill_score * 0.65) + (keyword_score * 0.35))

        total = round(
            (skill_score * 0.35)
            + (experience_score * 0.2)
            + (education_score * 0.1)
            + (keyword_score * 0.15)
            + (semantic_score * 0.2)
        )

        recommendation = "Shortlist" if total >= job.threshold else "Review / Reject"
        summary = self._summary(resume, job, total, matched, missing)

        return ResumeScore(
            total_score=total,
            recommendation=recommendation,
            matched_skills=[_display_skill(skill) for skill in matched],
            missing_skills=[_display_skill(skill) for skill in missing],
            breakdown={
                "Skill Match": skill_score,
                "Experience Match": experience_score,
                "Education Match": education_score,
                "Keyword Match": keyword_score,
                "Semantic Match": semantic_score,
            },
            summary=summary,
        )

    def _rank_with_gemini(self, resume: ParsedResume, job: JobDescription) -> ResumeScore:
        prompt = _gemini_screening_prompt(resume, job)
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini API error {exc.code}: {details}") from exc

        data = json.loads(raw_response)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _json_from_model_text(text)
        breakdown = {
            "Skill Match": _bounded_int(parsed.get("breakdown", {}).get("Skill Match", 0)),
            "Experience Match": _bounded_int(parsed.get("breakdown", {}).get("Experience Match", 0)),
            "Education Match": _bounded_int(parsed.get("breakdown", {}).get("Education Match", 0)),
            "Keyword Match": _bounded_int(parsed.get("breakdown", {}).get("Keyword Match", 0)),
            "Semantic Match": _bounded_int(parsed.get("breakdown", {}).get("Semantic Match", 0)),
        }
        total_score = _bounded_int(parsed.get("total_score", 0))
        recommendation = str(parsed.get("recommendation", "")).strip()
        if recommendation not in {"Shortlist", "Review / Reject"}:
            recommendation = "Shortlist" if total_score >= job.threshold else "Review / Reject"

        return ResumeScore(
            total_score=total_score,
            recommendation=recommendation,
            matched_skills=_clean_string_list(parsed.get("matched_skills", [])),
            missing_skills=_clean_string_list(parsed.get("missing_skills", [])),
            breakdown=breakdown,
            summary=str(parsed.get("summary", "")).strip()[:420],
        )

    def _keyword_overlap(self, resume_text: str, job_text: str) -> int:
        job_terms = _important_terms(job_text)
        resume_terms = _important_terms(resume_text)
        if not job_terms:
            return 0
        return round((len(job_terms.intersection(resume_terms)) / len(job_terms)) * 100)

    def _education_score(self, resume_education: str, job_education: str) -> int:
        if resume_education.lower() == "not found":
            return 45
        resume_terms = _important_terms(resume_education)
        job_terms = _important_terms(job_education)
        if not job_terms:
            return 75
        return 100 if resume_terms.intersection(job_terms) else 70

    def _summary(
        self,
        resume: ParsedResume,
        job: JobDescription,
        total: int,
        matched: list[str],
        missing: list[str],
    ) -> str:
        if total >= job.threshold:
            return (
                f"{resume.full_name} is a strong fit for {job.title}, matching "
                f"{len(matched)} required skills with {resume.experience_years} years of experience."
            )
        return (
            f"{resume.full_name} needs review before shortlisting; gaps include "
            f"{', '.join(_display_skill(skill) for skill in missing[:3]) or 'core JD alignment'}."
        )


def _load_dotenv() -> None:
    for parent_idx in (1, 2):
        env_path = Path(__file__).resolve().parents[parent_idx] / ".env"
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _gemini_screening_prompt(resume: ParsedResume, job: JobDescription) -> str:
    return f"""
You are an enterprise hiring platform resume screening engine.

Score this candidate only against the job description and job-related evidence.
Ignore protected or irrelevant personal characteristics. Do not infer sensitive traits.

Return only valid JSON using this exact schema:
{{
  "total_score": 0,
  "recommendation": "Shortlist",
  "matched_skills": [],
  "missing_skills": [],
  "breakdown": {{
    "Skill Match": 0,
    "Experience Match": 0,
    "Education Match": 0,
    "Keyword Match": 0,
    "Semantic Match": 0
  }},
  "summary": "One concise HR-facing explanation."
}}

Rules:
- total_score must be 0 to 100.
- recommendation must be "Shortlist" when total_score is at least {job.threshold}; otherwise "Review / Reject".
- matched_skills and missing_skills should focus on required JD skills.
- summary must be concise and evidence-based.

Job:
Title: {job.title}
Department: {job.department}
Location: {job.location}
Minimum experience: {job.experience_years} years
Required skills: {", ".join(job.required_skills)}
Nice to have skills: {", ".join(job.nice_to_have_skills)}
Education: {job.education}
Description: {job.description}

Parsed candidate:
Name: {resume.full_name}
Experience: {resume.experience_years} years
Education: {resume.education}
Detected skills: {", ".join(resume.skills)}

Resume text:
{resume.raw_text[:7000]}
""".strip()


def _json_from_model_text(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _bounded_int(value: object) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(100, parsed))


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:20]


def _friendly_error(exc: Exception) -> str:
    message = str(exc)
    if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
        return "Gemini quota or rate limit is currently exhausted; local fallback is active."
    if "403" in message or "API key" in message:
        return "Gemini API key was rejected; local fallback is active."
    return "Gemini request failed; local fallback is active."


def _important_terms(text: str) -> set[str]:
    stop_words = {
        "and",
        "the",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "need",
        "will",
        "have",
        "into",
        "your",
        "you",
        "our",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9.+#-]{2,}", text.lower())
        if token not in stop_words
    }


def _normalize_skill(skill: str) -> str:
    return skill.strip().lower().replace("rest APIs".lower(), "rest api")


def _display_skill(skill: str) -> str:
    return "REST API" if skill == "rest api" else skill.title()
