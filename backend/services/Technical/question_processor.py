"""
Custom technical question processor.

Extracts raw text from an uploaded question bank (PDF / DOCX / TXT) or manual
HR input, then uses the project's Gemini provider to restructure it into a
clean, structured question list. Falls back to simple line splitting when
Gemini is unavailable.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import BinaryIO

from backend.config import load_env
from backend.services.resume_parser import _read_docx, _read_pdf

QUESTION_RESTRUCTURE_PROMPT = """
You are an expert technical interviewer preparing a structured coding question bank.

The hiring team has supplied raw technical/coding questions (possibly messy,
with mixed numbering, bullets, headings, or answers). Restructure them into a
clean, de-duplicated list of individual questions.

Rules:
- Extract every distinct question. If an item contains both a question and a
  model answer, keep the answer in the "expected_points" array.
- Fix typos and grammar so the question reads clearly.
- Assign a short "topic" (e.g. algorithms, SQL, system design, python, REST API).
- Assign "difficulty": "easy", "medium", or "hard".
- expected_points: 2-4 concise bullet points an interviewer should listen for.
- Return ONLY valid JSON, an array of objects:
[
  {
    "question": "...",
    "topic": "...",
    "difficulty": "easy" | "medium" | "hard",
    "expected_points": ["...", "..."]
  }
]
- If the input contains no usable questions, return an empty array.
""".strip()


class QuestionProcessor:
    """Gemini-powered question restructure with a local fallback."""

    def __init__(self) -> None:
        load_env()
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.last_provider_used = "local"
        self.last_error = ""

    def process_text(self, raw_text: str) -> list[dict]:
        text = (raw_text or "").strip()
        if not text:
            return []
        if self.api_key:
            try:
                self.last_error = ""
                result = self._process_with_gemini(text)
                if result:
                    self.last_provider_used = "gemini"
                    return result
            except Exception as exc:
                self.last_error = _friendly_error(exc)
        self.last_provider_used = "local"
        return _process_locally(text)

    def process_file(self, uploaded_file: BinaryIO) -> list[dict]:
        file_name = getattr(uploaded_file, "name", "questions.txt")
        suffix = os.path.splitext(file_name)[1].lower()
        if suffix == ".docx":
            text = _read_docx(uploaded_file)
        elif suffix == ".pdf":
            text = _read_pdf(uploaded_file)
        else:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
        return self.process_text(text)

    def _process_with_gemini(self, raw_text: str) -> list[dict]:
        prompt = (
            QUESTION_RESTRUCTURE_PROMPT
            + "\n\nRAW QUESTIONS FROM HIRING TEAM:\n"
            + raw_text[:12000]
        )
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
        parsed = _json_from_model_text(text)
        if not isinstance(parsed, list):
            parsed = parsed.get("questions", []) if isinstance(parsed, dict) else []
        return [_normalize_question(item) for item in parsed if _normalize_question(item)]


def _process_locally(raw_text: str) -> list[dict]:
    """Fallback: split on numbering/bullets and wrap each line as a question."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    pattern = re.compile(r"^(?:\d+[.)]|\d+\s*[-:])|(?:^[-*•])")
    questions: list[dict] = []
    for line in lines:
        cleaned = re.sub(r"^(?:\d+[.)]\s*|\d+\s*[-:]\s*|[-*•]\s*)", "", line).strip()
        if len(cleaned) < 10:
            continue
        questions.append(_normalize_question({"question": cleaned, "topic": "General"}))
    return questions


def _normalize_question(item: dict) -> dict | None:
    question = str(item.get("question", "")).strip()
    if not question:
        return None
    difficulty = str(item.get("difficulty", "medium")).strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    expected_points = item.get("expected_points") or []
    if not isinstance(expected_points, list):
        expected_points = []
    return {
        "question": question,
        "topic": str(item.get("topic", "General")).strip() or "General",
        "difficulty": difficulty,
        "expected_points": [str(p).strip() for p in expected_points if str(p).strip()][:6],
    }


def _json_from_model_text(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return []


def _friendly_error(exc: Exception) -> str:
    message = str(exc)
    if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
        return "Gemini quota is exhausted; local formatting used."
    if "403" in message or "API key" in message:
        return "Gemini API key was rejected; local formatting used."
    return "Gemini request failed; local formatting used."
