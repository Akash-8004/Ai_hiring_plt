import json
import os
import re
import urllib.error
import urllib.request

from backend.config import load_env
from backend.core.models import JobDescription, ParsedResume

HR_EVALUATION_PROMPT = """
You are an expert HR interviewer evaluator with 10+ years of experience in talent assessment.

EVALUATE the interview transcript and return ONLY valid JSON.

SCORING CRITERIA (0-100 each):

1. communication_score (25%): clarity, articulation, structure, confidence, active listening, professional language.
2. behavioral_score (25%): STAR format, specific examples, self-awareness, teamwork, conflict resolution, growth mindset, accountability.
3. cultural_fit_score (20%): alignment with company values, attitude and enthusiasm, work style, motivation, adaptability.
4. professionalism_score (15%): preparedness, questions asked, respect and courtesy, handling difficult questions, overall demeanor.
5. resume_alignment_score (15%): validation of resume claims, consistency, depth of experience verification, honesty.

CALCULATION:
final_round_score = (communication * 0.25) + (behavioral * 0.25) + (cultural_fit * 0.20) + (professionalism * 0.15) + (resume_alignment * 0.15)

DECISION LOGIC:
- PASS: final_round_score >= 70 AND no critical red flags
- FAIL: final_round_score < 70 OR critical red flags present

Critical red flags: frequent job hopping without reason, negative attitude, dishonesty, poor communication, unrealistic expectations, cultural misalignment.

OUTPUT JSON:
{
  "communication_score": <0-100>,
  "behavioral_score": <0-100>,
  "cultural_fit_score": <0-100>,
  "professionalism_score": <0-100>,
  "resume_alignment_score": <0-100>,
  "final_round_score": <calculated decimal>,
  "decision": "PASS" or "FAIL",
  "feedback": "<natural paragraph text>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "areas_for_improvement": ["<area 1>", "<area 2>"],
  "red_flags": ["<flag>" or "None"],
  "recommendation": "<brief overall recommendation>"
}
"""


class InterviewAgent:
    """Gemini-powered AI interviewer prompts and transcript evaluation."""

    def __init__(self) -> None:
        load_env()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.last_error = ""

    def build_interviewer_prompt(self, job: JobDescription, resume: ParsedResume) -> str:
        return f"""
You are an HR interviewer conducting a voice mock interview on behalf of {job.title} hiring at the company.

TARGET ROLE: {job.title}
DEPARTMENT: {job.department}
LOCATION: {job.location}
MINIMUM EXPERIENCE: {job.experience_years} years
REQUIRED SKILLS: {", ".join(job.required_skills)}
NICE TO HAVE: {", ".join(job.nice_to_have_skills)}
JOB DESCRIPTION: {job.description}

CANDIDATE:
Name: {resume.full_name}
Experience: {resume.experience_years} years
Education: {resume.education}
Detected skills: {", ".join(resume.skills)}

RESUME TEXT:
{resume.raw_text[:6000]}

INTERVIEW STRUCTURE (10-15 minutes total):
1. WARM OPENING: Greet the candidate warmly by name, introduce yourself as from the HR team, ask them to introduce themselves.
2. BACKGROUND & MOTIVATION: Ask them to walk through their career journey, what attracted them to this role, and what they look for next.
3. BEHAVIORAL ASSESSMENT: Use STAR probing - significant workplace challenge, difficult team member, tight deadline. Dig deeper with follow-ups.
4. CULTURAL FIT: Preferred work style, ideal work environment, work-life balance.
5. PRACTICAL MATTERS: Notice period, joining timeline, relocation willingness.
6. CLOSING: Ask if they have questions, then thank them and tell them the interview is complete.

TONE & STYLE:
- Conversational, warm, empathetic, professional but not robotic.
- Active listening - acknowledge answers and encourage elaboration.
- One question at a time. Follow up naturally based on their answers.
- When you are finished with the interview, say "Thank you for joining" and end the session.
""".strip()

    def evaluate_interview(self, resume_text: str, transcript: list[dict]) -> dict:
        prompt = (
            HR_EVALUATION_PROMPT
            + "\n\nRESUME:\n"
            + (resume_text or "")[:6000]
            + "\n\nINTERVIEW TRANSCRIPT:\n"
            + _format_transcript(transcript)
        )
        if self.api_key:
            try:
                self.last_error = ""
                return self._call_gemini(prompt)
            except Exception as exc:
                self.last_error = str(exc)
        return self._evaluate_locally(transcript)

    def _call_gemini(self, prompt: str) -> dict:
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
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Gemini API error {exc.code}") from exc

        data = json.loads(raw_response)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _json_from_model_text(text)

    def _evaluate_locally(self, transcript: list[dict]) -> dict:
        user_words = sum(len((str(m.get("content", "")) or "").split()) for m in transcript if m.get("role") == "user")
        detail = min(100, round(user_words / 40 * 100)) if user_words else 30
        decision = "PASS" if detail >= 70 else "FAIL"
        return {
            "communication_score": detail,
            "behavioral_score": detail,
            "cultural_fit_score": detail,
            "professionalism_score": detail,
            "resume_alignment_score": detail,
            "final_round_score": detail,
            "decision": decision,
            "feedback": "Local evaluation: transcript length-based estimate. Configure a Gemini API key for full AI evaluation.",
            "strengths": [],
            "areas_for_improvement": [],
            "red_flags": "None",
            "recommendation": "Review transcript manually.",
        }


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for message in transcript:
        role = message.get("role", "unknown")
        content = message.get("content") or message.get("message") or ""
        lines.append(f"{role.upper()}: {str(content)[:2000]}")
    return "\n".join(lines) if lines else "(empty transcript)"


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
