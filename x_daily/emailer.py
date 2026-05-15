"""Send HTML email via Gmail SMTP."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(html_body: str, subject: str, to_addr: str) -> bool:
    """Send an HTML email through Gmail SMTP.

    Reads credentials from env vars:
      GMAIL_USER     – your Gmail address
      GMAIL_APP_PASSWORD – Gmail app password (not your real password)

    Returns True on success.
    """
    smtp_user = os.environ.get("GMAIL_USER")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not smtp_user or not smtp_pass:
        raise RuntimeError(
            "GMAIL_USER and GMAIL_APP_PASSWORD env vars are required"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())
        server.quit()
        print(f"[emailer] Email sent to {to_addr}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[emailer] SMTP auth failed — check GMAIL_USER and GMAIL_APP_PASSWORD")
        return False
    except Exception as exc:
        print(f"[emailer] Failed to send: {exc}")
        return False
