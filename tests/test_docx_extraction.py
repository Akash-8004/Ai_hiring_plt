"""Regression tests for DOCX extraction (Phase 0b).

Guards against silently dropping table cells, text boxes, headers, and footers.

Run directly:
    python tests/test_docx_extraction.py
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.resume_parser import _read_docx, parse_uploaded_resume_with_ai


def _make_sample_docx() -> io.BytesIO:
    from docx import Document

    doc = Document()

    # Paragraphs in body
    p = doc.add_paragraph("Candidate Name: Jane Doe")
    doc.add_paragraph("Summary: Experienced Full Stack Engineer with 6 years experience.")

    # Table with contact details & skills (real resumes frequently use tables)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Email: jane.doe@example.com"
    table.cell(0, 1).text = "Phone: +1 555 123 4567"
    table.cell(1, 0).text = "Skills: Python, FastAPI, React, PostgreSQL"
    table.cell(1, 1).text = "Education: Master of Science in Computer Science"

    # Header and Footer
    section = doc.sections[0]
    section.header.paragraphs[0].text = "Portfolio: https://janedoe.dev"
    section.footer.paragraphs[0].text = "LinkedIn: https://linkedin.com/in/janedoe"

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    buf.name = "jane_doe_resume.docx"
    return buf


def test_docx_extracts_body_tables_and_headers_footers():
    """Verify tables and headers/footers are captured in extracted text."""
    docx_stream = _make_sample_docx()
    text = _read_docx(docx_stream)

    assert "Jane Doe" in text, "Failed to extract body paragraph"
    assert "jane.doe@example.com" in text, "Failed to extract table cell email"
    assert "Python, FastAPI" in text, "Failed to extract table cell skills"
    assert "janedoe.dev" in text, "Failed to extract header text"
    assert "linkedin.com/in/janedoe" in text, "Failed to extract footer text"


def test_docx_parsing_recovers_all_fields():
    """Verify parsed resume contains details located in tables and headers/footers."""
    docx_stream = _make_sample_docx()
    raw_bytes = docx_stream.getvalue()

    parsed = parse_uploaded_resume_with_ai(docx_stream, raw_bytes=raw_bytes)

    assert parsed.full_name == "Jane Doe"
    assert parsed.email == "jane.doe@example.com"
    assert "Python" in parsed.skills
    assert "FastAPI" in parsed.skills
    assert parsed.linkedin == "https://linkedin.com/in/janedoe"


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
