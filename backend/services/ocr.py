import base64
import json
import logging
import os
import urllib.error
import urllib.request

from backend.config import load_env

logger = logging.getLogger(__name__)

OCR_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def ocr_document(file_name: str, contents: bytes) -> str:
    load_env()
    if not os.getenv("OCR_ENABLED", "true").strip().lower() in ("1", "true", "yes"):
        logger.info("OCR disabled via OCR_ENABLED, skipping %s", file_name)
        return ""

    ext = os.path.splitext(file_name)[1].lower()
    mime = OCR_MIME_BY_EXT.get(ext)
    if not mime:
        logger.warning("No OCR mime type for extension '%s'", ext)
        return ""

    max_mb = int(os.getenv("OCR_MAX_FILE_MB", "10"))
    if len(contents) > max_mb * 1024 * 1024:
        logger.warning("File %s exceeds OCR_MAX_FILE_MB (%d MB), skipping OCR", file_name, max_mb)
        return ""

    if mime == "application/pdf":
        max_pages = int(os.getenv("OCR_MAX_PAGES", "10"))
        try:
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(contents))
            if len(reader.pages) > max_pages:
                logger.warning("File %s has %d pages (max %d), skipping OCR", file_name, len(reader.pages), max_pages)
                return ""
        except Exception:
            pass

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No GEMINI_API_KEY set, cannot OCR %s", file_name)
        return ""

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    timeout = int(os.getenv("OCR_TIMEOUT_SECONDS", "60"))
    media_resolution = os.getenv("OCR_MEDIA_RESOLUTION", "MEDIA_RESOLUTION_MEDIUM").strip()

    b64 = base64.standard_b64encode(contents).decode("ascii")

    prompt = (
        "Transcribe all text from this document verbatim. "
        "Preserve reading order and line breaks. "
        "Return plain text only — no summarising, no commentary, no markdown fences."
    )

    generation_config = {
        "temperature": 0,
        "responseMimeType": "text/plain",
    }
    if media_resolution:
        generation_config["mediaResolution"] = media_resolution

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64}},
                {"text": prompt},
            ],
        }],
        "generationConfig": generation_config,
    }

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        logger.exception("Gemini OCR API error %d for %s: %s", exc.code, file_name, err_body)
        return ""
    except Exception:
        logger.exception("Gemini OCR request failed for %s", file_name)
        return ""

    try:
        data = json.loads(body)
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        logger.info("OCR extracted %d characters from %s", len(text), file_name)
        return text
    except Exception:
        logger.exception("Failed to parse OCR response for %s", file_name)
        return ""
