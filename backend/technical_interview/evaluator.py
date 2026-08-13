"""
Technical interview evaluator — uses Gemini API to score a completed
technical interview transcript.  Follows the same pattern as the existing
InterviewAgent but with technical-specific scoring.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from backend.technical_interview.prompts import TECHNICAL_EVALUATION_PROMPT


class TechnicalInterviewEvaluator:
    """Evaluate a technical interview transcript using Gemini."""

    def __init__(self) -> None:
        _load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.last_error = ""

    def evaluate(self, resume_text: str, transcript: list[dict]) -> dict:
        """Score the technical interview and return structured results."""
        prompt = (
            TECHNICAL_EVALUATION_PROMPT
            + "\n\nRESUME:\n"
            + (resume_text or "")[:6000]
            + "\n\nINTERVIEW TRANSCRIPT:\n"
            + _format_transcript(transcript)
        )
        if self.api_key:
            try:
                self.last_error = ""
                result = self._call_gemini(prompt)
                # Retry once if JSON parsing failed
                if result is None:
                    result = self._call_gemini(prompt)
                if result is not None:
                    return result
            except Exception as exc:
                self.last_error = str(exc)
        return self._evaluate_locally(transcript)

    def _call_gemini(self, prompt: str) -> dict | None:
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
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Gemini API error {exc.code}") from exc

        data = json.loads(raw_response)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _json_from_model_text(text)

    @staticmethod
    def _evaluate_locally(transcript: list[dict]) -> dict:
        """Fallback when Gemini is unavailable — rough word-count estimate."""
        user_words = sum(
            len((str(m.get("content", "")) or "").split())
            for m in transcript
            if m.get("role") in ("user", "candidate")
        )
        detail = min(100, round(user_words / 40 * 100)) if user_words else 30
        decision = "PASS" if detail >= 65 else "FAIL"
        return {
            "problem_solving_score": detail,
            "technical_depth_score": detail,
            "code_quality_score": detail,
            "communication_score": detail,
            "debugging_optimization_score": detail,
            "final_round_score": detail,
            "decision": decision,
            "feedback": "Local evaluation: transcript length-based estimate. Configure a Gemini API key for full AI evaluation.",
            "technical_strengths": [],
            "technical_gaps": [],
            "code_quality_notes": "N/A",
            "recommendation": "Review transcript manually.",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for message in transcript:
        role = message.get("role", "unknown")
        content = message.get("content") or message.get("message") or ""
        lines.append(f"{role.upper()}: {str(content)[:2000]}")
    return "\n".join(lines) if lines else "(empty transcript)"


def _json_from_model_text(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting the first JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None
