"""Email template generators.

Each function returns a tuple of ``(subject, html_body, plain_body)`` ready to
be passed to ``email_service.send_email``.
"""


from datetime import datetime


def _format_deadline(deadline: str | None) -> str:
    """Format an ISO 8601 deadline for display in the invitation email."""
    if not deadline:
        return ""
    try:
        dt = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(deadline)
    if dt.tzinfo is None:
        local_now = datetime.now()
        return local_now.strftime("%B %d, %Y") + " " + dt.strftime("%I:%M %p")
    return dt.strftime("%B %d, %Y at %I:%M %p %Z")


def interview_invite_email(
    candidate_name: str,
    interview_type: str,
    link: str,
    deadline: str | None = None,
) -> tuple[str, str, str]:
    """Build an interview invitation email with an optional completion deadline."""
    round_label = interview_type.replace("_", " ").title()
    subject = f"Interview Invitation — {round_label} Round"

    formatted_deadline = _format_deadline(deadline)
    plain_deadline = (
        f"\nPlease complete this interview before: {formatted_deadline}\n"
        if formatted_deadline
        else ""
    )
    html_deadline = (
        f'<p style="margin: 16px 0; padding: 10px 14px; background: #fef3c7; color: #92400e; border-radius: 6px; font-weight: 600;">'
        f'<span role="img" aria-label="calendar">\U0001f4c5</span> Please complete this interview before: '
        f'{formatted_deadline}</p>'
        if formatted_deadline
        else ""
    )
    expiry_notice = "After the deadline passes, this link will no longer work.\n\n" if formatted_deadline else ""
    html_expiry_notice = '<p style="font-size: 12px; color: #94a3b8;">After the deadline passes, this link will no longer work.</p>' if formatted_deadline else ""

    plain_body = (
        f"Dear {candidate_name},\n\n"
        f"You have been invited to complete the {round_label} round of our interview process.\n\n"
        f"Please use the link below to begin your interview:\n"
        f"{link}\n"
        f"{plain_deadline}\n"
        f"{expiry_notice}"
        f"This link is unique to you — please do not share it with anyone.\n\n"
        f"Good luck!\n"
        f"— AI Hiring Platform"
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Interview Invitation</h2>
  <p>Dear {candidate_name},</p>
  <p>You have been invited to complete the <strong>{round_label}</strong> round of our interview process.</p>
  <p>Please click the link below to begin your interview:</p>
  <p style="margin: 20px 0;">
    <a href="{link}" style="display: inline-block; padding: 10px 24px; background: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600;">Start Interview</a>
  </p>
  <p style="font-size: 13px; color: #64748b;">Or copy this URL: <a href="{link}" style="color: #6366f1;">{link}</a></p>
  {html_deadline}
  {html_expiry_notice}
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="font-size: 12px; color: #94a3b8;">This link is unique to you — please do not share it with anyone.</p>
</body>
</html>"""

    return subject, html_body, plain_body


def credential_delivery_email(
    company_name: str,
    admin_email: str,
    password: str,
    portal_url: str,
) -> tuple[str, str, str]:
    """Build a credentials delivery email for a newly onboarded company admin."""
    subject = "Your AI Hiring Platform Credentials"

    plain_body = (
        f"Welcome to the AI Hiring Platform!\n\n"
        f"Your company \"{company_name}\" has been onboarded. Below are your login credentials:\n\n"
        f"Login Email : {admin_email}\n"
        f"Password    : {password}\n"
        f"Portal URL  : {portal_url}\n\n"
        f"IMPORTANT: Please change your password after your first login.\n\n"
        f"— AI Hiring Platform"
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Welcome to AI Hiring Platform</h2>
  <p>Your company <strong>{company_name}</strong> has been successfully onboarded.</p>
  <p>Here are your login credentials:</p>
  <table style="border-collapse: collapse; width: 100%; margin: 16px 0; background: #f8fafc; border-radius: 8px;">
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Login Email</td><td style="padding: 10px 16px; font-family: monospace;">{admin_email}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Password</td><td style="padding: 10px 16px; font-family: monospace;">{password}</td></tr>
  </table>
  <p style="margin: 20px 0;">
    <a href="{portal_url}" style="display: inline-block; padding: 10px 24px; background: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600;">Go to Login Portal</a>
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="font-size: 13px; color: #ef4444; font-weight: 600;">⚠ Security Notice</p>
  <p style="font-size: 13px; color: #64748b;">Please change your password immediately after your first login.</p>
</body>
</html>"""

    return subject, html_body, plain_body
