"""SMTP email sending service with MongoDB logging.

Uses Python's built-in smtplib and email.mime — no external dependencies needed.
Configuration is pulled from environment variables.
"""

import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import load_env
from backend.storage import database

load_env()


def _smtp_configured() -> bool:
    """Return True only when the minimum SMTP vars are set."""
    return bool(os.getenv("SMTP_HOST")) and bool(os.getenv("SMTP_USER"))


def send_email(to_email: str, subject: str, html_body: str, plain_body: str | None = None) -> dict:
    """Send an email via SMTP/TLS.

    Returns ``{"ok": True}`` on success or ``{"ok": False, "error": "..."}`` on
    failure.  Never raises — all exceptions are caught and surfaced in the
    return dict.
    """
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

        with smtplib.SMTP(host, port, timeout=15) as server:
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
