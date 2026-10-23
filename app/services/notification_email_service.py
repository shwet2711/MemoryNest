from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Final

from app.core.config import (
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USE_SSL,
    SMTP_USE_STARTTLS,
    SMTP_USERNAME,
)


class EmailConfigurationError(RuntimeError):
    """Raised when SMTP settings are incomplete or invalid."""


def validate_email_configuration() -> None:
    """Validate email settings before starting the delivery worker."""
    if not SMTP_HOST:
        raise EmailConfigurationError(
            "SMTP_HOST is missing. Configure your SMTP settings in .env."
        )

    if not SMTP_FROM_EMAIL:
        raise EmailConfigurationError(
            "SMTP_FROM_EMAIL is missing. Configure your sender address in .env."
        )

    if SMTP_PORT < 1 or SMTP_PORT > 65535:
        raise EmailConfigurationError("SMTP_PORT must be between 1 and 65535.")

    if SMTP_TIMEOUT_SECONDS <= 0:
        raise EmailConfigurationError("SMTP_TIMEOUT_SECONDS must be positive.")

    if SMTP_USE_SSL and SMTP_USE_STARTTLS:
        raise EmailConfigurationError(
            "Enable either SMTP_USE_SSL or SMTP_USE_STARTTLS, not both."
        )

    if SMTP_USERNAME and not SMTP_PASSWORD:
        raise EmailConfigurationError(
            "SMTP_PASSWORD is required when SMTP_USERNAME is configured."
        )


def send_notification_email(
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Send a plain-text email using the configured SMTP server.

    Returns only after the SMTP server accepts the message.
    Raises an exception if configuration or delivery fails.
    """
    validate_email_configuration()

    if not recipient or "@" not in recipient:
        raise ValueError("A valid recipient email address is required.")

    message = EmailMessage()
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    smtp: smtplib.SMTP | smtplib.SMTP_SSL

    if SMTP_USE_SSL:
        smtp = smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    else:
        smtp = smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        )

    with smtp:
        if SMTP_USE_STARTTLS:
            smtp.starttls()
            smtp.ehlo()

        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)

        refused = smtp.send_message(message)

        if recipient in refused:
            raise RuntimeError("SMTP server refused the recipient.")
