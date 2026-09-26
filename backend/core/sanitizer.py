"""Input sanitization and output encoding utilities (BUG 28).

**Design policy — strip-on-write + escape-on-read (defense-in-depth):**

- *Write path* (``strip_html``): Dangerous HTML tags (``<script>``, ``<iframe>``,
  ``<object>``, ``<embed>``, ``<style>``, ``<svg>``, ``<math>``) and all ``on*``
  event-handler attributes are stripped on ingestion, so stored values never
  contain executable markup.  Benign tags like ``<b>`` or ``<br>`` are also
  removed to keep stored text consistently plain-text, but their *text content*
  is preserved (e.g. ``<b>Acme</b>`` → ``Acme``).

- *Read path* (``html_escape``): All user-controlled values are HTML-escaped
  before interpolation into HTML contexts (email bodies).  This is the primary
  defense; strip-on-write is a secondary belt-and-suspenders layer.

- *Prompt path* (``sanitize_for_prompt``): Control characters and excessive
  whitespace are collapsed before text is spliced into LLM system prompts, as a
  lightweight prompt-injection hardening measure.

**No external dependencies** — uses only the Python standard library
(``html``, ``re``).
"""

import html
import re

# ── Tags considered dangerous (executable or embedding) ─────────────────────
_DANGEROUS_TAG_RE = re.compile(
    r"<\s*/?\s*"
    r"(script|iframe|object|embed|style|svg|math|link|base|meta|form|input|textarea|button|select|applet)"
    r"(?:\s[^>]*)?\s*/?\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Matches HTML tags (starting with ASCII letter or !) while preserving
# legitimate text with comparison symbols like "< 5 years" or "<50k and >20k"
_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>", re.DOTALL)

# Matches on*="..." event-handler attributes (e.g. onerror="alert(1)")
_EVENT_ATTR_RE = re.compile(
    r"""\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)""",
    re.IGNORECASE,
)

# Control characters (except tab, newline, carriage return)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Collapse runs of whitespace beyond double-newline
_EXCESSIVE_WS_RE = re.compile(r"\n{3,}")


def html_escape(value: str) -> str:
    """Escape a string for safe interpolation in an HTML context.

    Uses ``html.escape`` with ``quote=True`` so the result is safe inside
    both element content and attribute values.  Plain-text email bodies
    should use the raw value, not the escaped one.
    """
    if not isinstance(value, str):
        return str(value)
    return html.escape(value, quote=True)


def strip_html(value: str) -> str:
    """Remove all HTML tags from *value*, preserving inner text content.

    This is the **write-path** sanitizer — applied when persisting user input
    so that stored values are consistently plain-text.

    Processing order:
    1. Remove event-handler attributes (``on*="..."``).
    2. Repeatedly remove all HTML tags until fixed-point (handles nested bypasses).
    3. Collapse whitespace and strip.

    Examples::

        >>> strip_html('<script>alert(1)</script>')
        'alert(1)'
        >>> strip_html('<b>Acme & Co</b>')
        'Acme & Co'
        >>> strip_html('< 5 years experience')
        '< 5 years experience'
        >>> strip_html('Looking for < 5 years, target > 2 years')
        'Looking for < 5 years, target > 2 years'
        >>> strip_html('<img src=x onerror=alert(1)>')
        ''
    """
    if not isinstance(value, str):
        return str(value)
    # 1) Strip event-handler attributes first
    text = _EVENT_ATTR_RE.sub("", value)
    # 2) Repeatedly remove HTML tags to neutralize nested tags
    while True:
        cleaned = _TAG_RE.sub("", text)
        if cleaned == text:
            break
        text = cleaned
    # 3) Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def sanitize_for_prompt(value: str, max_length: int = 8000) -> str:
    """Prepare user-supplied text for inclusion in an LLM system prompt.

    - Strips HTML tags (prompt context is plain-text).
    - Removes control characters that could confuse tokenisers.
    - Collapses excessive whitespace.
    - Truncates to *max_length* characters.

    This is a **lightweight** prompt-injection hardening measure — it does NOT
    make prompt injection impossible, but it removes the most common attack
    vectors (HTML/JS payloads, control chars).
    """
    if not isinstance(value, str):
        return str(value)[:max_length]
    text = strip_html(value)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _EXCESSIVE_WS_RE.sub("\n\n", text)
    return text[:max_length]


def sanitize_dict_fields(doc: dict, fields: list[str]) -> dict:
    """Apply ``strip_html`` to the specified *fields* of a dict, in-place.

    Fields that are missing or non-string are silently skipped.
    Returns the same dict for convenience.
    """
    for field in fields:
        val = doc.get(field)
        if isinstance(val, str):
            doc[field] = strip_html(val)
    return doc
