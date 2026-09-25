"""
app/auth/email.py
-----------------
Async SMTP email sender.

Design decisions
----------------
- Uses aiosmtplib so sending never blocks the FastAPI event loop.
- Configuration comes exclusively from settings — no hardcoded credentials.
- Falls back gracefully in DEBUG mode: if SMTP is not configured the OTP
  is printed to stdout so development works without a real mail server.
- OTP values are NEVER logged — only "OTP email sent to <email>" is recorded.

Security notes
--------------
- TLS via STARTTLS on port 587 (EMAIL_USE_TLS=true).
- Implicit TLS on port 465 when EMAIL_PORT=465.
- Credentials from environment variables only.
"""

from __future__ import annotations

import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_OTP_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f4f6f9;padding:40px 0;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;
                    box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;">
        <tr>
          <td style="background:linear-gradient(135deg,#6366f1,#4f46e5);
                     padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">
              {app_name}
            </h1>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;">
            <p style="margin:0 0 8px;color:#374151;font-size:16px;">
              Hello{name_part},
            </p>
            <p style="margin:0 0 28px;color:#6b7280;font-size:14px;line-height:1.6;">
              {purpose_text}
            </p>
            <div style="background:#f0f1ff;border:2px dashed #6366f1;
                        border-radius:10px;padding:24px;text-align:center;
                        margin:0 0 28px;">
              <p style="margin:0 0 4px;color:#6366f1;font-size:11px;
                         font-weight:700;letter-spacing:1.5px;">
                YOUR VERIFICATION CODE
              </p>
              <p style="margin:0;color:#1e1b4b;font-size:42px;font-weight:900;
                         letter-spacing:10px;font-family:'Courier New',monospace;">
                {otp}
              </p>
            </div>
            <p style="margin:0 0 8px;color:#9ca3af;font-size:12px;">
              This code expires in <strong>{expire_min} minutes</strong>.
            </p>
            <p style="margin:0 0 28px;color:#9ca3af;font-size:12px;">
              You have <strong>{max_attempts} attempts</strong> to enter it correctly.
            </p>
            <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;">
            <p style="margin:0;color:#d1d5db;font-size:11px;line-height:1.5;">
              If you did not request this code, please ignore this email.
              Never share this code with anyone.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;padding:20px 40px;text-align:center;
                     border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:11px;">
              {app_name} &nbsp;·&nbsp; Automated notification — do not reply
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

_PURPOSE_TEXT = {
    "login":          "Use the code below to complete your sign-in.",
    "email_verify":   "Use the code below to verify your email address.",
    "password_reset": "Use the code below to reset your account password.",
}

_SUBJECT = {
    "login":          "{app} \u2014 Sign-in verification code",
    "email_verify":   "{app} \u2014 Email verification code",
    "password_reset": "{app} \u2014 Password reset code",
}


def _build_otp_message(
    to_email: str,
    otp: str,
    purpose: str,
    to_name: Optional[str],
) -> MIMEMultipart:
    subject  = _SUBJECT.get(purpose, "{app} — Verification code").format(app=settings.APP_NAME)
    name_p   = f" {to_name}" if to_name else ""
    p_text   = _PURPOSE_TEXT.get(purpose, "Use the code below to verify your identity.")

    html = _OTP_HTML.format(
        app_name=settings.APP_NAME,
        name_part=name_p,
        purpose_text=p_text,
        otp=otp,
        expire_min=settings.OTP_EXPIRE_SECONDS // 60,
        max_attempts=settings.OTP_MAX_ATTEMPTS,
    )
    plain = textwrap.dedent(f"""
        {settings.APP_NAME} — Verification Code

        {p_text}

        Your code: {otp}

        Expires in {settings.OTP_EXPIRE_SECONDS // 60} minutes.
        Maximum attempts: {settings.OTP_MAX_ATTEMPTS}.

        If you did not request this, please ignore this email.
    """).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_otp_email(
    to_email: str,
    otp: str,
    purpose: str = "login",
    to_name: Optional[str] = None,
) -> None:
    """
    Send the OTP email asynchronously.

    Dev mode (no SMTP configured): prints OTP to stdout only.
    Production: connects to SMTP host with STARTTLS / implicit TLS.

    NEVER logs the OTP value.
    """
    if settings.DEBUG and not settings.EMAIL_USERNAME:
        logger.info(
            "DEV MODE — OTP email suppressed (no SMTP configured)",
            extra={"to": to_email, "purpose": purpose},
        )
        print(f"\n{'='*52}")
        print(f"  [DEV OTP] {to_email}  purpose={purpose}")
        print(f"  Code: {otp}   (expires {settings.OTP_EXPIRE_SECONDS//60} min)")
        print(f"{'='*52}\n")
        return

    msg = _build_otp_message(to_email, otp, purpose, to_name)

    try:
        import aiosmtplib  # lazy import — only needed when actually sending

        await aiosmtplib.send(
            msg,
            hostname=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_USERNAME or None,
            password=settings.EMAIL_PASSWORD or None,
            use_tls=(settings.EMAIL_PORT == 465),
            start_tls=(settings.EMAIL_USE_TLS and settings.EMAIL_PORT != 465),
        )
        logger.info(
            "OTP email sent",
            extra={"to": to_email, "purpose": purpose},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to send OTP email",
            extra={"to": to_email, "purpose": purpose, "error": str(exc)},
        )
        raise


async def send_password_reset_email(
    to_email: str,
    reset_token: str,
    to_name: Optional[str] = None,
) -> None:
    """
    Send a password-reset link email.  NEVER logs the token.
    """
    reset_url = f"http://localhost:8501/reset-password?token={reset_token}"

    if settings.DEBUG and not settings.EMAIL_USERNAME:
        logger.info("DEV MODE — password reset email suppressed",
                    extra={"to": to_email})
        print(f"\n{'='*52}")
        print(f"  [DEV RESET] {to_email}")
        print(f"  URL: {reset_url}")
        print(f"{'='*52}\n")
        return

    subject = f"{settings.APP_NAME} — Password Reset"
    html    = (
        "<html><body style='font-family:Arial,sans-serif;padding:40px;'>"
        "<h2>Password Reset</h2>"
        "<p>Click below to reset your password (expires in 30 minutes).</p>"
        f"<p><a href='{reset_url}' style='color:#6366f1;'>Reset my password</a></p>"
        "<p style='color:#9ca3af;font-size:12px;'>If you did not request this, ignore this email.</p>"
        "</body></html>"
    )
    plain = f"Reset your password: {reset_url}\n\nExpires in 30 minutes."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        import aiosmtplib
        await aiosmtplib.send(
            msg,
            hostname=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_USERNAME or None,
            password=settings.EMAIL_PASSWORD or None,
            use_tls=(settings.EMAIL_PORT == 465),
            start_tls=(settings.EMAIL_USE_TLS and settings.EMAIL_PORT != 465),
        )
        logger.info("Password reset email sent", extra={"to": to_email})
    except Exception as exc:
        logger.error("Failed to send password reset email",
                     extra={"to": to_email, "error": str(exc)})
        raise
