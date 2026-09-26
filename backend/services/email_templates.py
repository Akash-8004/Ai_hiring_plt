"""Email template generators.

Each function returns a tuple of ``(subject, html_body, plain_body)`` ready to
be passed to ``email_service.send_email``.

All user-controlled values are HTML-escaped via ``html_escape()`` before
interpolation into ``html_body`` strings (BUG 28 — output encoding).
Plain-text bodies use raw values (no HTML context).
"""


from datetime import datetime

from backend.core.sanitizer import html_escape as _esc


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

    # BUG 28: escape user-controlled values for HTML context
    _candidate_name = _esc(candidate_name)
    _round_label = _esc(round_label)

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Interview Invitation</h2>
  <p>Dear {_candidate_name},</p>
  <p>You have been invited to complete the <strong>{_round_label}</strong> round of our interview process.</p>
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
    """Build a credentials delivery email for a newly onboarded company admin.

    .. deprecated::
        **SECURITY CONCERN (Issue #20, item 4)**: This function sends the plaintext
        password in the email body. This is an inherent risk — email is not a secure
        channel, and passwords can be logged, cached, or intercepted in transit.

        **Recommended migration path**:
        1. Replace ``password`` with a one-time, time-limited setup token/link
           (e.g. ``/setup-account?token=<token>``).
        2. The link lands on a "Set your password" page; the user chooses their own
           password (never transmitted via email).
        3. Until this migration is complete, the current implementation is retained
           as a stop-gap, but callers should plan to switch to the token-based flow.

        The ``create_company`` and ``send-credentials`` admin routes both invoke this
        function (see ``backend/admin/routes.py``).
    """
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

    # BUG 28: escape user-controlled values for HTML context
    _company_name = _esc(company_name)
    _admin_email = _esc(admin_email)
    _password = _esc(password)

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Welcome to AI Hiring Platform</h2>
  <p>Your company <strong>{_company_name}</strong> has been successfully onboarded.</p>
  <p>Here are your login credentials:</p>
  <table style="border-collapse: collapse; width: 100%; margin: 16px 0; background: #f8fafc; border-radius: 8px;">
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Login Email</td><td style="padding: 10px 16px; font-family: monospace;">{_admin_email}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Password</td><td style="padding: 10px 16px; font-family: monospace;">{_password}</td></tr>
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


def credits_adjusted_email(
    company_name: str,
    admin_email: str,
    delta: int,
    new_allowance: int,
    new_remaining: int,
    portal_url: str,
) -> tuple[str, str, str]:
    """Build a notification email for a super-admin credit adjustment.

    Sent to the company admin whenever a super admin adds or removes credits.
    """
    action_label = "added to" if delta > 0 else "removed from"
    change = f"+{delta:,}" if delta > 0 else f"{delta:,}"
    subject = f"AI Hiring Platform — Credits {('Added' if delta > 0 else 'Removed')}"

    plain_body = (
        f"Hello,\n\n"
        f"This is to inform you that your credit balance for \"{company_name}\" "
        f"has been updated by the platform administrator.\n\n"
        f"Credits {action_label} your account : {change}\n"
        f"Current Allowance                : {new_allowance:,}\n"
        f"Remaining Balance                : {new_remaining:,}\n\n"
        f"You can log in to review your usage: {portal_url}\n\n"
        f"— AI Hiring Platform"
    )

    # BUG 28: escape user-controlled values for HTML context
    _company_name = _esc(company_name)

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Credits {('Added' if delta > 0 else 'Removed')}</h2>
  <p>Your credit balance for <strong>{_company_name}</strong> has been updated by the platform administrator.</p>
  <table style="border-collapse: collapse; width: 100%; margin: 16px 0; background: #f8fafc; border-radius: 8px;">
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Credits {action_label} your account</td><td style="padding: 10px 16px; font-family: monospace;">{change}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Current Allowance</td><td style="padding: 10px 16px; font-family: monospace;">{new_allowance:,}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Remaining Balance</td><td style="padding: 10px 16px; font-family: monospace;">{new_remaining:,}</td></tr>
  </table>
  <p style="margin: 20px 0;">
    <a href="{portal_url}" style="display: inline-block; padding: 10px 24px; background: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600;">Go to Login Portal</a>
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="font-size: 12px; color: #94a3b8;">This is an automated notification from the AI Hiring Platform.</p>
</body>
</html>"""

    return subject, html_body, plain_body


def company_details_email(
    company_name: str,
    admin_email: str,
    plan: str,
    allowance: int,
    used: int,
    remaining: int,
    portal_url: str,
) -> tuple[str, str, str]:
    """Build an account summary email for a company admin.

    Sent on request from the super admin (e.g., to remind an admin of their
    account details).
    """
    subject = f"Your AI Hiring Platform Account Summary — {company_name}"

    plain_body = (
        f"Hello,\n\n"
        f"Here is a summary of your AI Hiring Platform account for "
        f"\"{company_name}\":\n\n"
        f"Company      : {company_name}\n"
        f"Admin Email  : {admin_email}\n"
        f"Plan         : {plan.title()}\n"
        f"Credit Allowance : {allowance:,}\n"
        f"Credits Used      : {used:,}\n"
        f"Credits Remaining : {remaining:,}\n\n"
        f"Login Portal : {portal_url}\n\n"
        f"— AI Hiring Platform"
    )

    # BUG 28: escape user-controlled values for HTML context
    _company_name = _esc(company_name)
    _admin_email = _esc(admin_email)
    _plan = _esc(plan.title())

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">Your AI Hiring Platform Account Summary</h2>
  <p>Here is a summary of your account for <strong>{_company_name}</strong>:</p>
  <table style="border-collapse: collapse; width: 100%; margin: 16px 0; background: #f8fafc; border-radius: 8px;">
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Company</td><td style="padding: 10px 16px;">{_company_name}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Admin Email</td><td style="padding: 10px 16px; font-family: monospace;">{_admin_email}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Plan</td><td style="padding: 10px 16px;">{_plan}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Credit Allowance</td><td style="padding: 10px 16px; font-family: monospace;">{allowance:,}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Credits Used</td><td style="padding: 10px 16px; font-family: monospace;">{used:,}</td></tr>
    <tr><td style="padding: 10px 16px; font-weight: 600; color: #475569;">Credits Remaining</td><td style="padding: 10px 16px; font-family: monospace;">{remaining:,}</td></tr>
  </table>
  <p style="margin: 20px 0;">
    <a href="{portal_url}" style="display: inline-block; padding: 10px 24px; background: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600;">Go to Login Portal</a>
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="font-size: 12px; color: #94a3b8;">This is an automated notification from the AI Hiring Platform.</p>
</body>
</html>"""

    return subject, html_body, plain_body


def demo_confirmation_email(
    contact_name: str,
    company_name: str,
    work_email: str,
    team_size: str = "",
    hiring_volume: str = "",
    message: str = "",
) -> tuple[str, str, str]:
    """Build a confirmation email for a public 'Book a demo' request.

    Sent to the requester only; the sales team sees the lead in the admin
    leads section.
    """
    subject = "We've received your demo request — AI Hiring Platform"

    details_lines = [
        ("Company", company_name),
        ("Contact Name", contact_name),
        ("Work Email", work_email),
    ]
    if team_size:
        details_lines.append(("Team Size", team_size))
    if hiring_volume:
        details_lines.append(("Hiring Volume", hiring_volume))

    plain_rows = "\n".join(
        f"{'%-14s'} : {value}" % label for label, value in details_lines
    )
    plain_summary = (
        f"\nHere is a summary of your request:\n\n{plain_rows}\n"
    ) if details_lines else ""
    plain_message = (
        f"\nYour message:\n{message.strip()}\n" if message.strip() else ""
    )

    # BUG 28: escape user-controlled values for HTML context
    _contact_name = _esc(contact_name)
    _company_name = _esc(company_name)
    _message = _esc(message.strip())

    html_rows = "".join(
        f'<tr><td style="padding: 10px 16px; font-weight: 600; color: #475569; white-space: nowrap;">{_esc(label)}</td>'
        f'<td style="padding: 10px 16px;">{_esc(value)}</td></tr>'
        for label, value in details_lines
    )
    html_summary = (
        '<p style="margin: 16px 0;">Here is a summary of your request:</p>'
        '<table style="border-collapse: collapse; width: 100%; margin: 12px 0 20px; background: #f8fafc; border-radius: 8px;">'
        f'{html_rows}</table>'
    ) if details_lines else ""
    html_message = (
        f'<p style="margin: 16px 0;"><strong>Your message:</strong><br />{_message}</p>'
        if message.strip()
        else ""
    )

    plain_body = (
        f"Dear {contact_name},\n\n"
        f"Thank you for requesting a live demo of the AI Hiring Platform "
        f"for {company_name}.\n\n"
        f"Our hiring technology specialists have received your details and "
        f"will reach out to schedule your personalized session.\n"
        f"{plain_summary}"
        f"{plain_message}"
        f"\nWe look forward to speaking with you!\n\n"
        f"— AI Hiring Platform"
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="margin-top: 0; color: #0f172a;">We've received your demo request</h2>
  <p>Dear {_contact_name},</p>
  <p>Thank you for requesting a live demo of the <strong>AI Hiring Platform</strong> for <strong>{_company_name}</strong>.</p>
  <p>Our hiring technology specialists have received your details and will reach out to schedule your personalized session.</p>
  {html_summary}
  {html_message}
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="font-size: 12px; color: #94a3b8;">We look forward to speaking with you!</p>
</body>
</html>"""

    return subject, html_body, plain_body
