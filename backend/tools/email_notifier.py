"""Email notifier tool for Project Nightmare (Phase 8D).
Uses Python built-in smtplib and email.message.EmailMessage.

STRICT SECURITY RULE:
Nightmare must NEVER send an email automatically. Emails are sent ONLY after
explicit user approval at Security Clearance Level 5.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


def create_nudge_email_draft(
    to_email: str,
    assigned_team: str,
    task_name: str,
    current_count: float,
    target_count: float,
    days_stale: float,
    sender: str = "",
) -> tuple[str, str, EmailMessage]:
    """Generates subject, plain body text, and EmailMessage for a stale task reminder."""
    pct = round((current_count / target_count) * 100, 1) if target_count > 0 else 0.0
    curr_str = f"{int(current_count)}" if current_count.is_integer() else f"{current_count}"
    tgt_str = f"{int(target_count)}" if target_count.is_integer() else f"{target_count}"
    days_str = f"{int(days_stale)}" if days_stale.is_integer() else f"{days_stale:.1f}"

    subject = f"[Nightmare Reminder] Progress Update Needed: {task_name} ({assigned_team})"
    body = (
        f"Hi {assigned_team},\n\n"
        f"This is an automated progress reminder from Project Nightmare.\n\n"
        f"Task: {task_name}\n"
        f"Current Progress: {curr_str} / {tgt_str} ({pct}% completed)\n"
        f"Status: No updates recorded for {days_str}+ days.\n\n"
        f"Please update the project timeline or reach out if any assistance or unblocking is needed.\n\n"
        f"Thank you,\nProject Nightmare"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender or "nightmare@localhost"
    msg["To"] = to_email
    msg.set_content(body)
    return subject, body, msg


def send_nudge_email(
    to_email: str,
    subject: str,
    body: str,
    settings: Settings | None = None,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
) -> tuple[bool, str]:
    """Sends a reminder email via SMTP.
    
    Level 5 authorization and explicit click approval must be validated BEFORE calling this.
    """
    smtp_host = host or (settings.smtp_host if settings else os.environ.get("SMTP_HOST", "smtp.gmail.com"))
    smtp_port = port or (settings.smtp_port if settings else int(os.environ.get("SMTP_PORT", "587")))
    smtp_user = user or (settings.smtp_user if settings else os.environ.get("SMTP_USER", ""))
    smtp_password = password or (settings.smtp_app_password if settings else os.environ.get("SMTP_APP_PASSWORD", ""))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user or "nightmare@localhost"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        logger.info("Sent team nudge email to %s", to_email)
        return True, f"Reminder email successfully sent to {to_email}."
    except Exception as exc:
        logger.exception("Failed to send nudge email to %s: %s", to_email, exc)
        return False, f"Failed to send email: {exc}"
