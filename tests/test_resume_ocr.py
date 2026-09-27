"""Tests for Gemini Vision OCR resume extraction and fallback behavior.

Run directly:
    python tests/test_resume_ocr.py
"""

import io
import json
import os
import sys
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.ocr import ocr_document, OCR_MIME_BY_EXT
from backend.services.resume_parser import (
    parse_uploaded_resume_with_ai,
    _is_text_empty,
    _empty_resume,
)
from backend.main import _validate_magic_bytes, ALLOWED_RESUME_EXTENSIONS

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCANNED_PDF_PATH = FIXTURES_DIR / "scanned_resume.pdf"


def _make_text_pdf() -> bytes:
    # Generates a minimal PDF with actual text stream
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 73 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"72 712 Td\n"
        b"(John Doe Senior Software Engineer john.doe@example.com Python FastAPI Docker) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000367 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"444\n"
        b"%%EOF\n"
    )


def test_text_pdf_never_calls_ocr():
    """Cost guard: A PDF with embedded text layer MUST NOT trigger OCR."""
    pdf_bytes = _make_text_pdf()
    stream = io.BytesIO(pdf_bytes)
    stream.name = "john_doe_resume.pdf"

    with mock.patch("backend.services.resume_parser.ocr_document") as mock_ocr:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with mock.patch("urllib.request.urlopen") as mock_url:
                mock_resp = mock.MagicMock()
                mock_resp.read.return_value = json.dumps({
                    "candidates": [{
                        "content": {
                            "parts": [{
                                "text": json.dumps({
                                    "full_name": "John Doe",
                                    "email": "john.doe@example.com",
                                    "phone": "555-123-4567",
                                    "skills": ["Python", "FastAPI", "Docker"],
                                    "experience_years": 5,
                                    "education": "B.S. in Computer Science",
                                    "linkedin": "https://linkedin.com/in/johndoe",
                                    "github": "https://github.com/johndoe",
                                })
                            }]
                        }
                    }]
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                parsed = parse_uploaded_resume_with_ai(stream, raw_bytes=pdf_bytes)

                mock_ocr.assert_not_called()
                assert parsed.full_name == "John Doe"
                assert parsed.email == "john.doe@example.com"
                assert parsed.parsing_provider == "gemini"
                assert not parsed.raw_text.startswith("[NO_TEXT_EXTRACTED]")


def test_scanned_pdf_recovers_text_with_ocr():
    """Scanned PDF with empty text layer calls OCR and recovers full text."""
    scanned_bytes = SCANNED_PDF_PATH.read_bytes()
    stream = io.BytesIO(scanned_bytes)
    stream.name = "scanned_candidate.pdf"

    ocr_transcript = (
        "Alice Smith\n"
        "Email: alice.smith@example.com\n"
        "Phone: +1 (555) 987-6543\n"
        "Skills: React, TypeScript, Node.js, Python, MongoDB\n"
        "Experience: 4 years as Frontend Engineer at TechCorp\n"
        "Education: Bachelor of Science in Software Engineering\n"
    )

    with mock.patch("backend.services.resume_parser.ocr_document", return_value=ocr_transcript) as mock_ocr:
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with mock.patch("urllib.request.urlopen") as mock_url:
                mock_resp = mock.MagicMock()
                mock_resp.read.return_value = json.dumps({
                    "candidates": [{
                        "content": {
                            "parts": [{
                                "text": json.dumps({
                                    "full_name": "Alice Smith",
                                    "email": "alice.smith@example.com",
                                    "phone": "+1 (555) 987-6543",
                                    "skills": ["React", "TypeScript", "Node.js", "Python", "MongoDB"],
                                    "experience_years": 4,
                                    "education": "Bachelor of Science in Software Engineering",
                                })
                            }]
                        }
                    }]
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                parsed = parse_uploaded_resume_with_ai(stream, raw_bytes=scanned_bytes)

                mock_ocr.assert_called_once()
                assert parsed.full_name == "Alice Smith"
                assert parsed.email == "alice.smith@example.com"
                assert parsed.parsing_provider == "gemini-ocr"
                assert parsed.raw_text == ocr_transcript
                assert not _is_text_empty(parsed.raw_text)


def test_ocr_disabled_env_yields_sentinel():
    """When OCR_ENABLED=false, scanned PDF degrades to sentinel."""
    scanned_bytes = SCANNED_PDF_PATH.read_bytes()
    stream = io.BytesIO(scanned_bytes)
    stream.name = "scanned_candidate.pdf"

    with mock.patch.dict(os.environ, {"OCR_ENABLED": "false", "GEMINI_API_KEY": "fake-key"}):
        parsed = parse_uploaded_resume_with_ai(stream, raw_bytes=scanned_bytes)
        assert parsed.parsing_provider == "none"
        assert parsed.raw_text.startswith("[NO_TEXT_EXTRACTED]")


def test_ocr_exception_swallowed_and_degrades_gracefully():
    """OCR network/API errors must never raise — degrade to sentinel."""
    scanned_bytes = SCANNED_PDF_PATH.read_bytes()
    stream = io.BytesIO(scanned_bytes)
    stream.name = "scanned_candidate.pdf"

    with mock.patch("backend.services.ocr.urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            parsed = parse_uploaded_resume_with_ai(stream, raw_bytes=scanned_bytes)
            assert parsed.parsing_provider == "none"
            assert parsed.raw_text.startswith("[NO_TEXT_EXTRACTED]")


def test_image_png_goes_straight_to_ocr():
    """PNG/JPG inputs go straight to OCR without attempting pypdf."""
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 20
    stream = io.BytesIO(png_bytes)
    stream.name = "resume_photo.png"

    ocr_transcript = "Name: Bob Johnson\nEmail: bob@example.com\nSkills: Python, Django, AWS\nExperience: 3 years"

    with mock.patch("backend.services.resume_parser.ocr_document", return_value=ocr_transcript) as mock_ocr:
        with mock.patch("backend.services.resume_parser._read_pdf") as mock_read_pdf:
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                parsed = parse_uploaded_resume_with_ai(stream, raw_bytes=png_bytes)
                mock_read_pdf.assert_not_called()
                mock_ocr.assert_called_once()
                assert parsed.full_name == "Bob Johnson"
                assert parsed.email == "bob@example.com"


def test_ocr_document_payload_shape():
    """Verify inline_data mime_type, base64 payload and media_resolution."""
    sample_pdf = SCANNED_PDF_PATH.read_bytes()

    with mock.patch.dict(os.environ, {
        "GEMINI_API_KEY": "test-key-123",
        "GEMINI_MODEL": "gemini-3.5-flash-lite",
        "OCR_MEDIA_RESOLUTION": "MEDIA_RESOLUTION_MEDIUM",
    }):
        with mock.patch("urllib.request.urlopen") as mock_url:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps({
                "candidates": [{
                    "content": {
                        "parts": [
                            {"text": "Line 1\n"},
                            {"text": "Line 2"},
                        ]
                    }
                }]
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            text = ocr_document("doc.pdf", sample_pdf)
            assert text == "Line 1\nLine 2"

            # Check request payload structure
            call_args = mock_url.call_args[0][0]
            assert call_args.get_header("X-goog-api-key") == "test-key-123"
            req_data = json.loads(call_args.data.decode("utf-8"))
            part = req_data["contents"][0]["parts"][0]
            assert "inlineData" in part
            assert part["inlineData"]["mimeType"] == "application/pdf"
            assert req_data["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_MEDIUM"


def test_magic_byte_validation():
    """Verify magic-byte validation rejects disguised files."""
    assert _validate_magic_bytes("real.pdf", b"%PDF-1.4...", ".pdf") is None
    assert _validate_magic_bytes("real.png", b"\x89PNG\r\n...", ".png") is None
    assert _validate_magic_bytes("real.jpg", b"\xff\xd8\xff\xe0...", ".jpg") is None
    assert _validate_magic_bytes("real.docx", b"PK\x03\x04...", ".docx") is None

    # ZIP disguised as PDF
    err = _validate_magic_bytes("fake.pdf", b"PK\x03\x04...", ".pdf")
    assert err is not None
    assert "ZIP/DOCX" in err

    # Garbage in PDF
    err2 = _validate_magic_bytes("corrupt.pdf", b"Random garbage text", ".pdf")
    assert err2 is not None


def _main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
            failed.append(name)
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
