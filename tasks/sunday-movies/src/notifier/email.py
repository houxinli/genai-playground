"""Utility helpers for sending markdown emails."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Iterable

import markdown2


def send_markdown_email(markdown_text: str, *, subject: str, to_addresses: Iterable[str]) -> None:
    """Send a markdown email using SMTP credentials from environment variables."""
    to_list = [addr.strip() for addr in to_addresses if addr.strip()]
    if not to_list:
        raise ValueError("At least one recipient email must be provided.")

    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not user or not password:
        raise RuntimeError("EMAIL_USER and EMAIL_APP_PASSWORD must be set in the environment.")

    host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "465"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_list)
    msg.set_content(markdown_text, subtype="plain")
    html_body = markdown2.markdown(markdown_text, extras=["tables"])
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL(host, port) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def send_markdown_email_from_file(markdown_path: str, *, subject: str, to_addresses: Iterable[str]) -> None:
    """Load Markdown from a file and send it via email."""
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()
    send_markdown_email(markdown_text, subject=subject, to_addresses=to_addresses)
