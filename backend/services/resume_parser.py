import re
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import BinaryIO

from backend.core.models import ParsedResume
from backend.config import load_env


KNOWN_SKILLS = {
    "python",
    "fastapi",
    "django",
    "flask",
    "react",
    "typescript",
    "javascript",
    "postgresql",
    "mysql",
    "mongodb",
    "docker",
    "kubernetes",
    "aws",
    "redis",
    "celery",
    "rest api",
    "graphql",
    "langchain",
    "openai",
    "html",
    "css",
    "node.js",
    "git",
    "linux",
}


def parse_resume_text(file_name: str, text: str) -> ParsedResume:
    normalized = " ".join(text.split())
    lower_text = normalized.lower()

    name = _extract_name(text, file_name)
    email = _first_match(r"[\w.+-]+@[\w-]+\.[\w.-]+", normalized, "not-found@example.com")
    phone = _first_match(r"(\+?\d[\d\s().-]{8,}\d)", normalized, "Not found")
    experience = _extract_experience(lower_text)
    education = _extract_education(text)
    skills = sorted({skill.title() if skill != "rest api" else "REST API" for skill in KNOWN_SKILLS if skill in lower_text})
    linkedin = _first_match(r"(linkedin\.com/[^\s,]+)", normalized, "")
    github = _first_match(r"(github\.com/[^\s,]+)", normalized, "")
    other_links = _extract_other_links(normalized, linkedin)

    return ParsedResume(
        file_name=file_name,
        full_name=name,
        email=email,
        phone=phone,
        skills=skills,
        experience_years=experience,
        education=education,
        linkedin=linkedin,
        github=github,
        raw_text=text,
        other_links=other_links,
    )


def parse_resume_text_with_ai(file_name: str, text: str) -> ParsedResume:
    load_env()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return parse_resume_text(file_name, text)
    try:
        parsed = _extract_with_gemini(file_name, text, api_key)
        model_links = parsed.get("other_links") if isinstance(parsed.get("other_links"), list) else []
        model_links += ([{"label": "GitHub", "url": _string(parsed.get("github"))}] if _string(parsed.get("github")) else [])
        model_links += _extract_other_links(text, _string(parsed.get("linkedin")))
        return ParsedResume(
            file_name=file_name,
            full_name=_string(parsed.get("full_name"), "Not found"),
            email=_string(parsed.get("email"), "not-found@example.com"),
            phone=_string(parsed.get("phone"), "Not found"),
            skills=_string_list(parsed.get("skills")),
            experience_years=_nonnegative_int(parsed.get("experience_years")),
            education=_string(parsed.get("education"), "Not found"),
            linkedin=_string(parsed.get("linkedin")),
            github=_string(parsed.get("github")),
            raw_text=text,
            job_title=_string(parsed.get("job_title")),
            location=_string(parsed.get("location")),
            summary=_string(parsed.get("summary")),
            parsing_provider="gemini",
            other_links=_link_list(model_links),
        )
    except Exception:
        return parse_resume_text(file_name, text)


def parse_uploaded_resume_with_ai(uploaded_file: BinaryIO) -> ParsedResume:
    file_name = getattr(uploaded_file, "name", "uploaded_resume.txt")
    suffix = Path(file_name).suffix.lower()
    if suffix == ".txt":
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    elif suffix == ".docx":
        text = _read_docx(uploaded_file)
    elif suffix == ".pdf":
        text = _read_pdf(uploaded_file)
    else:
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    return parse_resume_text_with_ai(file_name, text)


def _extract_with_gemini(file_name: str, text: str, api_key: str) -> dict:
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    prompt = (
        "Extract resume information and return only JSON. Include every explicitly "
        "mentioned skill, tool, technology, language, framework, database, cloud "
        "and DevOps item. Put GitHub, X, portfolio, project and any other non-LinkedIn "
        "URLs in other_links with a human-readable label. Use empty values when not found.\n"
        "Schema: {\"full_name\":\"\",\"email\":\"\",\"phone\":\"\","
        "\"skills\":[],\"experience_years\":0,\"education\":\"\","
        "\"linkedin\":\"\",\"github\":\"\",\"job_title\":\"\","
        "\"location\":\"\",\"summary\":\"\",\"other_links\":[]}\n"
        f"File name: {file_name}\nResume:\n{text[:20000]}"
    )
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseJsonSchema": {"type": "object", "properties": {
                "full_name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"},
                "skills": {"type": "array", "items": {"type": "string"}}, "experience_years": {"type": "number"},
                "education": {"type": "string"}, "linkedin": {"type": "string"}, "github": {"type": "string"},
                "job_title": {"type": "string"}, "location": {"type": "string"}, "summary": {"type": "string"},
                "other_links": {"type": "array", "items": {"type": "object", "properties": {
                    "label": {"type": "string"}, "url": {"type": "string"}
                }}},
            }},
        },
    }
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Gemini API error {exc.code}") from exc
    data = json.loads(body)
    return _json_from_model_text(data["candidates"][0]["content"]["parts"][0]["text"])


def _json_from_model_text(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Gemini returned a non-object resume")
    return value


def _string(value: object, fallback: str = "") -> str:
    return str(value).strip() if value is not None and str(value).strip() else fallback


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, round(float(value)))
    except (TypeError, ValueError):
        return 0


def _link_list(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    links = []
    seen = set()
    for item in value:
        if isinstance(item, dict):
            url = _string(item.get("url"))
            label = _string(item.get("label"), "Other link")
        else:
            url = _string(item)
            label = _link_label(url)
        if url and _is_plausible_link(url) and url not in seen:
            links.append({"label": label, "url": url})
            seen.add(url)
    return links


def _extract_other_links(text: str, linkedin: str) -> list[dict[str, str]]:
    found = re.findall(
        r"(?:https?://|www\.)[^\s,<>]+|(?<![@\w])(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,}(?:/[^\s,<>]*)?",
        text,
        re.IGNORECASE,
    )
    links = []
    for raw_url in found:
        url = raw_url.rstrip(".)]}")
        if linkedin and url.lower().rstrip("/") == linkedin.lower().rstrip("/"):
            continue
        has_scheme = bool(re.match(r"(?:https?://|www\.)", url, re.IGNORECASE))
        normalized = url if re.match(r"https?://", url, re.IGNORECASE) else f"https://{url}"
        parsed = urlparse(normalized)
        if not has_scheme and parsed.path in ("", "/") and parsed.netloc.lower().removeprefix("www.") not in _KNOWN_LINK_HOSTS:
            continue
        links.append({"label": _link_label(normalized), "url": normalized})
    return _link_list(links)


def extract_other_links(text: str, linkedin: str = "") -> list[dict[str, str]]:
    return _extract_other_links(text or "", linkedin or "")


def clean_other_links(value: object) -> list[dict[str, str]]:
    return _link_list(value)


def _link_label(url: str) -> str:
    host = urlparse(url if re.match(r"https?://", url, re.IGNORECASE) else f"https://{url}").netloc.lower().removeprefix("www.")
    names = {"github.com": "GitHub", "x.com": "X", "twitter.com": "X", "gitlab.com": "GitLab", "behance.net": "Behance", "dribbble.com": "Dribbble"}
    if host in names:
        return names[host]
    return host.split(".")[0].replace("-", " ").title() or "Other link"


_KNOWN_LINK_HOSTS = {
    "github.com", "gitlab.com", "linkedin.com", "x.com", "twitter.com",
    "leetcode.com", "stackoverflow.com", "medium.com", "dev.to", "behance.net",
    "dribbble.com", "kaggle.com", "portfolio.dev",
}

_NON_LINK_TECH_HOSTS = {
    "react.js", "node.js", "express.js", "asp.net", "b.tech", "make.com",
}


def _is_plausible_link(url: str) -> bool:
    parsed = urlparse(url if re.match(r"https?://", url, re.IGNORECASE) else f"https://{url}")
    host = parsed.netloc.lower().removeprefix("www.")
    return host not in _NON_LINK_TECH_HOSTS and bool(host and "." in host)


def parse_uploaded_resume(uploaded_file: BinaryIO) -> ParsedResume:
    file_name = getattr(uploaded_file, "name", "uploaded_resume.txt")
    suffix = Path(file_name).suffix.lower()

    if suffix == ".txt":
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    elif suffix == ".docx":
        text = _read_docx(uploaded_file)
    elif suffix == ".pdf":
        text = _read_pdf(uploaded_file)
    else:
        text = uploaded_file.read().decode("utf-8", errors="ignore")

    return parse_resume_text(file_name, text)


def _read_docx(uploaded_file: BinaryIO) -> str:
    try:
        from docx import Document

        document = Document(uploaded_file)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception:
        return "DOCX parsing placeholder. Install python-docx for real document extraction."


def _read_pdf(uploaded_file: BinaryIO) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(uploaded_file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return "PDF parsing placeholder. Install pypdf or pdfplumber for real PDF extraction."


def _extract_name(text: str, file_name: str) -> str:
    for line in text.splitlines():
        match = re.search(r"^\s*(?:name|full name)\s*:\s*([A-Za-z][A-Za-z\s.'-]{2,60})\s*$", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    match = re.search(
        r"(?:name|full name)\s*:\s*([A-Za-z][A-Za-z\s.'-]{2,60}?)(?=\s+(?:email|phone|experience|education)\s*:|$)",
        " ".join(text.split()),
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return Path(file_name).stem.replace("_", " ").replace("-", " ").title()


def _extract_experience(text: str) -> int:
    match = re.search(r"(\d+)\s*(?:\+?\s*)?(?:years|year|yrs|yr)", text)
    return int(match.group(1)) if match else 0


def _extract_education(text: str) -> str:
    for line in text.splitlines():
        match = re.search(r"^\s*(?:education|degree)\s*:\s*(.{2,80})\s*$", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    match = re.search(
        r"(?:education|degree)\s*:\s*(.{2,80}?)(?=\s+(?:skills|linkedin|github|experience|phone|email)\s*:|$)",
        " ".join(text.split()),
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    for keyword in ["B.Tech", "M.Tech", "MCA", "BCA", "MBA", "Bachelor", "Master"]:
        if keyword.lower() in text.lower():
            return keyword
    return "Not found"


def _first_match(pattern: str, text: str, fallback: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return fallback
    return (match.group(1) if match.groups() else match.group(0)).strip()
