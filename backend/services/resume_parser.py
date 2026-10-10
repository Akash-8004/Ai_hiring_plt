import logging
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
from backend.services.ocr import OCR_MIME_BY_EXT, ocr_document

logger = logging.getLogger(__name__)


SKILL_ALIASES: dict[str, str] = {
    # Node / JS / TS
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node js": "Node.js",
    "node": "Node.js",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    # Python & Frameworks
    "python": "Python",
    "py": "Python",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    # Frontend
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    "react native": "React Native",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "next js": "Next.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "svelte": "Svelte",
    "redux": "Redux",
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    # Databases
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "sqlite": "SQLite",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "elasticsearch": "Elasticsearch",
    "elastic search": "Elasticsearch",
    "supabase": "Supabase",
    "firebase": "Firebase",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    # DevOps, Cloud & Infra
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Azure",
    "microsoft azure": "Azure",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "ci cd": "CI/CD",
    "jenkins": "Jenkins",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "linux": "Linux",
    "bash": "Bash",
    "shell": "Shell",
    "powershell": "PowerShell",
    "nginx": "Nginx",
    "apache": "Apache",
    "helm": "Helm",
    # Streaming / Messaging
    "kafka": "Kafka",
    "apache kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "celery": "Celery",
    "sqs": "AWS SQS",
    # APIs & Architectures
    "rest": "REST API",
    "rest api": "REST API",
    "rest apis": "REST API",
    "restful": "REST API",
    "restful api": "REST API",
    "restful apis": "REST API",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "microservices": "Microservices",
    "websockets": "WebSockets",
    # AI / ML / Data
    "pytorch": "PyTorch",
    "py torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "scikit-learn": "Scikit-Learn",
    "scikit learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "langchain": "LangChain",
    "llamaindex": "LlamaIndex",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    "nlp": "NLP",
    "deep learning": "Deep Learning",
    "machine learning": "Machine Learning",
    "data science": "Data Science",
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    # Other Languages & Frameworks
    "java": "Java",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "ruby on rails": "Ruby on Rails",
    "rails": "Ruby on Rails",
    "php": "PHP",
    "laravel": "Laravel",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    ".net": ".NET",
    "dotnet": ".NET",
    "asp.net": "ASP.NET",
    "express": "Express.js",
    "expressjs": "Express.js",
    "express.js": "Express.js",
    "nestjs": "NestJS",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "scala": "Scala",
    "r": "R",
    "dart": "Dart",
    "flutter": "Flutter",
    "sql": "SQL",
    "nosql": "NoSQL",
    # Testing & Tooling
    "jest": "Jest",
    "pytest": "PyTest",
    "postman": "Postman",
    "jira": "Jira",
    "selenium": "Selenium",
    "cypress": "Cypress",
    "playwright": "Playwright",
}

KNOWN_SKILLS = set(SKILL_ALIASES.keys()).union({v.lower() for v in SKILL_ALIASES.values()})


def normalize_skill(skill: str) -> str:
    """Normalize skill name to lowercase canonical representation for deterministic matching."""
    cleaned = (skill or "").strip().lower()
    if not cleaned:
        return ""
    if cleaned in SKILL_ALIASES:
        return SKILL_ALIASES[cleaned].lower()
    squashed = re.sub(r"[\s._-]+", "", cleaned)
    for alias_key, canonical in SKILL_ALIASES.items():
        if re.sub(r"[\s._-]+", "", alias_key) == squashed:
            return canonical.lower()
    return cleaned


def canonicalize_skill(skill: str) -> str:
    """Return standard display casing for a skill name."""
    cleaned = (skill or "").strip()
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower in SKILL_ALIASES:
        return SKILL_ALIASES[lower]
    squashed = re.sub(r"[\s._-]+", "", lower)
    for alias_key, canonical in SKILL_ALIASES.items():
        if re.sub(r"[\s._-]+", "", alias_key) == squashed:
            return canonical
    return cleaned.title() if cleaned.isupper() or cleaned.islower() else cleaned


_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:technical\s+skills?|key\s+skills?|core\s+skills?|core\s+competencies|"
    r"technologies(?:\s+(?:and|&)\s+tools)?|tools(?:\s+(?:and|&)\s+technologies)?|"
    r"skills(?:\s+(?:and|&)\s+(?:expertise|abilities|competencies|tools))?|"
    r"tech\s+stack|skills)\s*[:\-–—]?\s*(.*)$",
    re.IGNORECASE,
)

_SECTION_STOP_RE = re.compile(
    r"^\s*(?:experience|work\s+experience|professional\s+experience|employment|"
    r"work\s+history|education|academic|projects|personal\s+projects|certifications?|"
    r"licenses?|publications?|awards?|summary|profile|about\s+me|objective|"
    r"interests|languages|references)\s*[:\-–—]?\s*$",
    re.IGNORECASE,
)

_SUB_CATEGORY_PREFIX_RE = re.compile(
    r"^\s*(?:languages?|programming\s+languages?|frameworks?|libraries|databases?|"
    r"devops|cloud|tools?|platforms?|operating\s+systems?|methodologies?)\s*[:\-–—]\s*",
    re.IGNORECASE,
)

_SKILL_DELIMITERS_RE = re.compile(r"[,;|•·\t]|\s+[/–—]\s+")

_NOISE_TOKENS = {
    "and", "etc", "or", "years", "year", "yrs", "experience", "various", "including",
    "basic", "advanced", "intermediate", "proficient", "strong", "good", "hands-on",
    "knowledge", "skills", "tools", "competencies", "technologies",
}


def _clean_skill_token(raw_token: str) -> list[str]:
    """Clean a skill token, handling parentheses (e.g. 'AWS (EC2, S3)') and noise prefixes."""
    token = raw_token.strip(" \t\r\n.,;:|•·-*_")
    if not token or len(token) > 45:
        return []
    token = re.sub(
        r"^(?:proficient\s+in|hands-on\s+with|experience\s+with|knowledge\s+of|strong\s+in|familiar\s+with)\s+",
        "",
        token,
        flags=re.IGNORECASE,
    ).strip()
    if not token:
        return []
    paren_match = re.match(r"^([^(]+)\(([^)]+)\)$", token)
    if paren_match:
        main_part = paren_match.group(1).strip()
        sub_part = paren_match.group(2).strip()
        results = []
        if main_part and main_part.lower() not in _NOISE_TOKENS:
            results.append(canonicalize_skill(main_part))
        for sub in _SKILL_DELIMITERS_RE.split(sub_part):
            sub_clean = sub.strip()
            if sub_clean and sub_clean.lower() not in _NOISE_TOKENS and not sub_clean.isdigit():
                results.append(canonicalize_skill(sub_clean))
        return results

    if token.lower() in _NOISE_TOKENS or token.isdigit():
        return []
    return [canonicalize_skill(token)]


def extract_skills_from_text(text: str) -> list[str]:
    """Extract skills using section-aware parsing combined with comprehensive lexicon matching."""
    if not text or not text.strip():
        return []

    extracted: list[str] = []
    seen_normalized: set[str] = set()

    def add_skill(skill_name: str) -> None:
        norm = normalize_skill(skill_name)
        if norm and norm not in seen_normalized and norm not in _NOISE_TOKENS:
            seen_normalized.add(norm)
            extracted.append(skill_name)

    lines = text.splitlines()
    in_skills_section = False
    section_lines_read = 0

    # 1. Section-aware extraction
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_skills_section and section_lines_read > 0:
                in_skills_section = False
            continue

        header_match = _SECTION_HEADER_RE.match(stripped)
        if header_match:
            in_skills_section = True
            section_lines_read = 0
            inline_content = header_match.group(1).strip()
            if inline_content:
                for chunk in _SKILL_DELIMITERS_RE.split(inline_content):
                    for tok in _clean_skill_token(chunk):
                        add_skill(tok)
            continue

        if in_skills_section:
            if _SECTION_STOP_RE.match(stripped):
                in_skills_section = False
                continue

            section_lines_read += 1
            if section_lines_read > 25:
                in_skills_section = False
                continue

            content = _SUB_CATEGORY_PREFIX_RE.sub("", stripped)
            content = re.sub(r"^[-*•·>]\s*", "", content)
            for chunk in _SKILL_DELIMITERS_RE.split(content):
                for tok in _clean_skill_token(chunk):
                    add_skill(tok)

    # 2. Comprehensive lexicon scan across the entire text (with boundary protection)
    lower_text = text.lower()
    for alias, canonical in SKILL_ALIASES.items():
        norm = canonical.lower()
        if norm in seen_normalized:
            continue
        if len(alias) <= 2:
            if alias in {"c++", "c#", ".net"}:
                pattern = r"(?<![a-zA-Z0-9])" + re.escape(alias) + r"(?![a-zA-Z0-9])"
                if re.search(pattern, lower_text):
                    add_skill(canonical)
            continue

        pattern = r"(?<![a-zA-Z0-9])" + re.escape(alias) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, lower_text):
            add_skill(canonical)

    return extracted


# Minimum number of non-whitespace characters to consider extracted text
# meaningful. Scanned/image-only PDFs and corrupt DOCX files typically
# produce empty or near-empty text that cannot be parsed.
_MIN_TEXT_LENGTH = 30


def _is_text_empty(text: str) -> bool:
    """Return True when extracted text is blank or trivially short."""
    stripped = (text or "").strip()
    # Also catch the old DOCX placeholder that should no longer appear
    if stripped.startswith("DOCX parsing placeholder") or stripped.startswith("PDF parsing placeholder"):
        return True
    # Count only non-whitespace characters
    return sum(1 for ch in stripped if not ch.isspace()) < _MIN_TEXT_LENGTH


def _empty_resume(file_name: str, text: str) -> ParsedResume:
    """Return a placeholder ParsedResume flagged as having no extractable text."""
    name = Path(file_name).stem.replace("_", " ").replace("-", " ").title()
    return ParsedResume(
        file_name=file_name,
        full_name=name,
        email="not-found@example.com",
        phone="Not found",
        skills=[],
        experience_years=0,
        education="Not found",
        raw_text="[NO_TEXT_EXTRACTED] The uploaded file contained no readable text. "
                 "This usually means the PDF is a scanned image without an embedded "
                 "text layer, or the DOCX file is corrupted. Please re-upload a "
                 "text-based PDF, DOCX, or TXT file.",
        parsing_provider="none",
    )


def parse_resume_text(file_name: str, text: str) -> ParsedResume:
    if _is_text_empty(text):
        return _empty_resume(file_name, text)
    normalized = " ".join(text.split())
    lower_text = normalized.lower()

    name = _extract_name(text, file_name)
    email = _first_match(r"[\w.+-]+@[\w-]+\.[\w.-]+", normalized, "not-found@example.com")
    phone = _first_match(r"(\+?\d[\d\s().-]{8,}\d)", normalized, "Not found")
    experience = _extract_experience(lower_text)
    education = _extract_education(text)
    skills = extract_skills_from_text(text)
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
        parsing_provider="regex-fallback",
    )


def parse_resume_text_with_ai(file_name: str, text: str) -> ParsedResume:
    if _is_text_empty(text):
        return _empty_resume(file_name, text)
    load_env()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning(
            "parse_resume_text_with_ai: GEMINI_API_KEY is not configured; using regex-fallback for %s",
            file_name,
        )
        res = parse_resume_text(file_name, text)
        res.parsing_provider = "regex-fallback"
        return res
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        parsed = _extract_with_gemini(file_name, text, api_key)
        model_links = parsed.get("other_links") if isinstance(parsed.get("other_links"), list) else []
        model_links += ([{"label": "GitHub", "url": _string(parsed.get("github"))}] if _string(parsed.get("github")) else [])
        model_links += _extract_other_links(text, _string(parsed.get("linkedin")))

        extracted_skills = _string_list(parsed.get("skills"))
        local_skills = extract_skills_from_text(text)
        if not extracted_skills:
            logger.warning(
                "parse_resume_text_with_ai: Gemini returned empty skills for %s; using local fallback skills (%d found)",
                file_name,
                len(local_skills),
            )
            extracted_skills = local_skills
        else:
            # Union with local skills so no explicitly mentioned skills are missed
            seen = {normalize_skill(s) for s in extracted_skills}
            for ls in local_skills:
                if normalize_skill(ls) not in seen:
                    extracted_skills.append(ls)
                    seen.add(normalize_skill(ls))

        logger.info(
            "parse_resume_text_with_ai: file=%s, model=%s, key_present=True, skills_count=%d, provider=gemini",
            file_name,
            model,
            len(extracted_skills),
        )

        return ParsedResume(
            file_name=file_name,
            full_name=_string(parsed.get("full_name"), "Not found"),
            email=_string(parsed.get("email"), "not-found@example.com"),
            phone=_string(parsed.get("phone"), "Not found"),
            skills=extracted_skills,
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
    except Exception as exc:
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        logger.exception(
            "parse_resume_text_with_ai: Gemini extraction failed for %s (model=%s): %s; falling back to regex parser",
            file_name,
            model,
            exc,
        )
        res = parse_resume_text(file_name, text)
        res.parsing_provider = "gemini-failed"
        logger.info(
            "parse_resume_text_with_ai: file=%s, model=%s, key_present=True, skills_count=%d, provider=gemini-failed",
            file_name,
            model,
            len(res.skills),
        )
        return res


def parse_uploaded_resume_with_ai(uploaded_file: BinaryIO, raw_bytes: bytes | None = None) -> ParsedResume:
    file_name = getattr(uploaded_file, "name", "uploaded_resume.txt")
    suffix = Path(file_name).suffix.lower()
    ocr_used = False
    if suffix in OCR_MIME_BY_EXT and suffix not in (".pdf",):
        contents = raw_bytes or uploaded_file.read()
        text = ocr_document(file_name, contents)
        ocr_used = bool(text and not _is_text_empty(text))
        if not ocr_used:
            text = ""
    elif suffix == ".txt":
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    elif suffix == ".docx":
        text = _read_docx(uploaded_file)
    elif suffix == ".pdf":
        text = _read_pdf(uploaded_file)
        if _is_text_empty(text):
            contents = raw_bytes or uploaded_file.read()
            ocr_text = ocr_document(file_name, contents)
            if ocr_text and not _is_text_empty(ocr_text):
                text = ocr_text
                ocr_used = True
    else:
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    if _is_text_empty(text):
        return _empty_resume(file_name, text)
    resume = parse_resume_text_with_ai(file_name, text)
    if ocr_used and resume.parsing_provider not in {"none", "regex-fallback", "gemini-failed"} and not resume.parsing_provider.endswith("-ocr"):
        resume.parsing_provider = f"{resume.parsing_provider}-ocr"
    return resume


def _extract_with_gemini(file_name: str, text: str, api_key: str) -> dict:
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
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
        parts = []
        for elem in document.element.body.iter():
            if elem.tag.endswith("}p") or elem.tag.endswith("}tr"):
                parts.append("\n")
            elif elem.tag.endswith("}tab"):
                parts.append(" ")
            elif elem.tag.endswith("}t"):
                if elem.text:
                    parts.append(elem.text)
        body_text = "".join(parts)
        for section in document.sections:
            for area in (section.header, section.footer):
                if area:
                    for paragraph in area.paragraphs:
                        if paragraph.text and paragraph.text.strip():
                            body_text += "\n" + paragraph.text
                    for table in getattr(area, "tables", []):
                        for row in table.rows:
                            for cell in row.cells:
                                if cell.text and cell.text.strip():
                                    body_text += "\n" + cell.text
        return body_text
    except Exception:
        logger.exception("Failed to read DOCX: %s", getattr(uploaded_file, "name", "unknown"))
        return ""


def _read_pdf(uploaded_file: BinaryIO) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(uploaded_file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.exception("Failed to read PDF: %s", getattr(uploaded_file, "name", "unknown"))
        return ""


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
