"""Email sending service with MongoDB logging.

Supports two transports chosen via the ``EMAIL_PROVIDER`` env var:

* ``smtp`` (default): SMTP/TLS via Python's built-in smtplib + email.mime.
* ``sendgrid``: HTTPS API (port 443, works on Render's free tier where outbound
  SMTP ports 25/465/587 are blocked).

Configuration is pulled from environment variables.
"""

import json
import os
import smtplib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import load_env
from backend.storage import database

load_env()

EMAIL_TIMEOUT = int(os.getenv("EMAIL_API_TIMEOUT", "15"))


def _smtp_configured() -> bool:
    """Return True only when the minimum SMTP vars are set."""
    return bool(os.getenv("SMTP_HOST")) and bool(os.getenv("SMTP_USER"))


def _active_provider() -> str:
    """Return the configured email provider (``smtp`` or ``sendgrid``)."""
    return os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()


def _post_json(url: str, headers: dict, payload: dict, timeout: int = EMAIL_TIMEOUT) -> dict:
    """POST a JSON payload to *url* over HTTPS.

    Returns ``{"ok": bool, "status": int, "body": str}``.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "body": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "body": str(exc)}


def _send_via_sendgrid(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str | None,
    from_email: str,
    from_name: str,
) -> dict:
    """Send an email through the SendGrid v3 Mail Send API."""
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "EMAIL_PROVIDER=sendgrid but SENDGRID_API_KEY is not set"}

    content = [{"type": "text/plain", "value": plain_body or html_body}]
    content.append({"type": "text/html", "value": html_body})

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": content,
    }

    res = _post_json(
        "https://api.sendgrid.com/v3/mail/send",
        {"Authorization": f"Bearer {api_key}"},
        payload,
    )
    if res["ok"]:
        return {"ok": True}
    detail = res["body"] or "unknown error"
    return {"ok": False, "error": f"SendGrid HTTP {res['status']}: {detail[:500]}"}


def send_email(to_email: str, subject: str, html_body: str, plain_body: str | None = None) -> dict:
    """Send an email.

    Returns ``{"ok": True}`` on success or ``{"ok": False, "error": "..."}`` on
    failure.  Never raises — all exceptions are caught and surfaced in the
    return dict.
    """
    provider = _active_provider()

    if provider == "sendgrid":
        from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
        from_name = os.getenv("SMTP_FROM_NAME", "AI Hiring Platform").strip()
        if not from_email:
            return {"ok": False, "error": "SMTP_FROM_EMAIL not set (used as the SendGrid sender)"}
        return _send_via_sendgrid(to_email, subject, html_body, plain_body, from_email, from_name)

    if not _smtp_configured():
        return {"ok": False, "error": "SMTP not configured"}

    try:
        host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASSWORD", "")
        from_email = os.getenv("SMTP_FROM_EMAIL", user)
        from_name = os.getenv("SMTP_FROM_NAME", "AI Hiring Platform")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email

        # Plain-text fallback
        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))

        # HTML body (primary)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(host, port, timeout=EMAIL_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())

        return {"ok": True}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def log_email_send(
    to_email: str,
    subject: str,
    email_type: str,
    status: str,
    error_message: str | None = None,
    metadata: dict | None = None,
    sent_by: str | None = None,
) -> None:
    """Insert a record into the ``email_logs`` MongoDB collection."""
    try:
        database.insert_email_log({
            "to_email": to_email,
            "subject": subject,
            "email_type": email_type,
            "status": status,
            "error_message": error_message,
            "metadata": metadata or {},
            "sent_at": datetime.now(timezone.utc),
            "sent_by": sent_by or "system",
        })
    except Exception:
        pass  # Logging should never crash the main flow