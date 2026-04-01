"""SMTP email sender — transactional emails for auth flows."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

VERIFY_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
  <h2>Verify your RepoInsight email</h2>
  <p>Hi {name},</p>
  <p>Click the link below to verify your email address. This link expires in <strong>24 hours</strong>.</p>
  <p>
    <a href="{verify_url}"
       style="display:inline-block;padding:12px 24px;background:#4F46E5;color:#fff;
              border-radius:6px;text-decoration:none;font-weight:bold">
      Verify Email
    </a>
  </p>
  <p>If you didn't create an account, you can safely ignore this email.</p>
  <hr/>
  <p style="font-size:12px;color:#666">RepoInsight &mdash; {verify_url}</p>
</body>
</html>
"""


async def send_verification_email(to_email: str, name: str, raw_token: str) -> None:
    verify_url = f"{settings.frontend_url}/auth/verify-email?token={raw_token}"
    html = VERIFY_EMAIL_TEMPLATE.format(name=name, verify_url=verify_url)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your RepoInsight email"
    msg["From"] = f"{settings.email_from_name} <{settings.email_from}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(settings.email_from, to_email, msg.as_string())
        logger.info("Verification email sent to %s", to_email)
    except smtplib.SMTPException as exc:
        logger.error("Failed to send verification email to %s: %s", to_email, exc)
        # Don't raise — email failure shouldn't abort signup; rely on resend endpoint
