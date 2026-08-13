import json
import os
import urllib.request
from typing import Any

from backend.src.interview_agent import InterviewAgent
from backend.src.models import JobDescription, ParsedResume
from backend.technical_interview.prompts import build_technical_interviewer_prompt

interview_agent = InterviewAgent()


def get_interviewer_prompt(interview_type: str, job: JobDescription, resume: ParsedResume) -> str:
    """Returns system prompt based on interview type (technical or hr)."""
    if interview_type == "technical":
        return build_technical_interviewer_prompt(job, resume)
    return interview_agent.build_interviewer_prompt(job, resume)


def generate_interviewer_turn(system_prompt: str, transcript: list[dict[str, str]], user_message: str = "") -> str:
    """Generates next turn response from the interviewer (Gemini API or local fallback)."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    prompt_parts = [system_prompt, "\n--- INTERVIEW CONVERSATION TRANSCRIPT ---"]
    for msg in transcript:
        role = "CANDIDATE" if msg.get("role") in ("candidate", "user") else "INTERVIEWER"
        prompt_parts.append(f"{role}: {msg.get('content', '')}")

    if user_message:
        prompt_parts.append(f"CANDIDATE: {user_message}")
        prompt_parts.append("INTERVIEWER: (Respond naturally as Rohan/interviewer. Ask follow-up or next technical question. Keep response under 3 sentences for natural speech.)")
    else:
        prompt_parts.append("INTERVIEWER: (Greet the candidate warmly by name, introduce yourself as Rohan from engineering, and ask them to introduce themselves. Keep response under 3 sentences.)")

    full_prompt = "\n\n".join(prompt_parts)

    if not key:
        if not user_message:
            return "Hi there! I'm Rohan from the engineering team. Welcome to your technical interview! Could you briefly introduce yourself and share your strongest technical experience?"
        return "Thank you for sharing that! Could you walk me through the hardest technical problem you encountered in that project and how you solved it?"

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req_payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 250,
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(req_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        print("Gemini chat endpoint error:", exc)
        if not user_message:
            return "Hi! I'm Rohan from the engineering team. Welcome to your technical interview! Please introduce yourself and your background."
        return "That sounds like a great experience. Can you tell me about the architecture and trade-offs you considered?"
