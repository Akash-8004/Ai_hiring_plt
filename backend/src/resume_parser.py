import re
from pathlib import Path
from typing import BinaryIO

from backend.src.models import ParsedResume


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
    )


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
