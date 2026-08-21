"""
HR Round interview evaluator.

Mirrors the TechnicalInterviewEvaluator pattern but uses the HR-specific
evaluation prompt and scoring dimensions.
"""

import json
import os
import re
import urllib.error
import urllib.request

from backend.config import load_env
from backend.services.HR_Round.prompts import HR_EVALUATION_PROMPT


def _format_transcript(transcript: list[dict]) -> str:
    lines = []
    for message in transcript:
        role = message.get("role", "unknown")
        content = message.get("content") or message.get("message") or ""
        label = role.upper()
        if message.get("type") == "written":
            label += " (WRITTEN)"
        lines.append(f"{label}: {str(content)[:2000]}")
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


class HREvaluator:
    """Gemini-powered HR interview evaluator.

    Sends the HR evaluation prompt + resume + transcript to Gemini and
    returns a structured score dict.  Falls back to a local word-count
    heuristic when no API key is configured.
    """

    def __init__(self) -> None:
        load_env()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.last_error = ""

    def evaluate(self, resume_text: str, transcript: list[dict]) -> dict:
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
        user_words = sum(
            len((str(m.get("content", "")) or "").split())
            for m in transcript
            if m.get("role") in ("user", "candidate")
        )
        detail = min(100, round(user_words / 40 * 100)) if user_words else 30
        decision = "PASS" if detail >= 70 else "FAIL"
        return {
            "communication_score": detail,
            "confidence_score": detail,
            "behavioral_score": detail,
            "motivation_cultural_fit_score": detail,
            "professionalism_score": detail,
            "technical_background_score": detail,
            "final_round_score": detail,
            "decision": decision,
            "feedback": "Local evaluation: transcript length-based estimate. Configure a Gemini API key for full AI evaluation.",
            "strengths": [],
            "areas_for_improvement": [],
            "red_flags": [],
            "recommendation": "Review transcript manually.",
        }
