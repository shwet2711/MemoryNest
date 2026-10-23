
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.event_model import DetectedEvent
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import (
    NotificationPreference,
    utc_now_naive,
)
from app.models.user import User
from app.services.gmail_service import (
    GmailReauthorizationRequired,
    send_notification_email_for_user,
)

logger = logging.getLogger(__name__)

EmailSender = Callable[[str, str, str], None]

STALE_PROCESSING_MINUTES = 15
MAX_ERROR_LENGTH = 2000

GMAIL_REAUTHORIZATION_ERROR = (
    "Gmail authorization has expired or been revoked. "
    "Reconnect Gmail in MemoryNest Settings before attempting "
    "to send this notification again."
)


def _utc_naive(value: datetime | None = None) -> datetime:
    """Return an aware or naive datetime as naive UTC."""
    if value is None:
        return datetime.now(UTC).replace(tzinfo=None)

    if value.tzinfo is None:
        return value

    return value.astimezone(UTC).replace(tzinfo=None)


def _event_email(event: DetectedEvent) -> tuple[str, str]:
    """Build a plain-text reminder from the confirmed event."""
    event_date = event.event_date.strftime("%d %B %Y")

    subject = f"MemoryNest reminder: {event.title}"
    body = (
        f"This is a reminder about your event in MemoryNest.\n\n"
        f"Event: {event.title}\n"
        f"Date: {event_date}\n"
        f"Type: {event.event_type}\n\n"
        "This reminder was created from an event you confirmed in "
        "MemoryNest.\n\n"
        "You can open MemoryNest to review your event details."
    )
    return subject, body


def _recover_stale_processing(
    db: Session,
    *,
    now: datetime,
    max_attempts: int,
) -> int:
    """Recover claims left behind by a worker that stopped unexpectedly."""
    cutoff = now - timedelta(minutes=STALE_PROCESSING_MINUTES)

    stale = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.status == "processing",
            NotificationDelivery.updated_at <= cutoff,
        )
        .all()
    )

    recovered = 0

    for delivery in stale:
        if delivery.attempts >= max_attempts:
            delivery.status = "failed"
            delivery.last_error = (
                "Worker stopped during processing; maximum attempts reached."
            )
        else:
            delivery.status = "pending"
            delivery.scheduled_for = now
            delivery.last_error = (
                "Recovered an interrupted processing claim; "
                "delivery outcome may be uncertain."
            )

        delivery.updated_at = now
        recovered += 1

    if recovered:
        db.commit()

    return recovered


def _cancel_delivery(
    db: Session,
    delivery: NotificationDelivery,
    reason: str,
    *,
    now: datetime,
) -> None:
    delivery.status = "cancelled"
    delivery.last_error = reason[:MAX_ERROR_LENGTH]
    delivery.updated_at = now
    db.commit()


def _fail_delivery(
    db: Session,
    delivery_id: int,
    reason: str,
    *,
    now: datetime,
) -> bool:
    """Mark a delivery as permanently failed without scheduling a retry."""
    delivery = db.get(NotificationDelivery, delivery_id)

    if delivery is None:
        return False

    delivery.status = "failed"
    delivery.last_error = reason[:MAX_ERROR_LENGTH]
    delivery.updated_at = now
    db.commit()
    return True


def process_due_notifications(
    db: Session,
    *,
    sender: EmailSender | None = None,
    now: datetime | None = None,
    batch_size: int = 25,
    max_attempts: int = 3,
    retry_delay_minutes: int = 5,
) -> dict[str, int]:
    """Process due email notifications.

    Production delivery uses the user's connected Gmail account.
    An injected sender is retained for tests and controlled callers.

    Database timestamps are naive UTC. Unsupported channels are failed
    instead of being incorrectly reported as delivered. Temporary sender
    exceptions trigger bounded retries with exponential backoff.
    Permanent Gmail reauthorization failures are failed immediately.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    if retry_delay_minutes < 1:
        raise ValueError("retry_delay_minutes must be at least 1.")

    now_utc = _utc_naive(now)

    stats = {
        "claimed": 0,
        "sent": 0,
        "retried": 0,
        "failed": 0,
        "cancelled": 0,
        "skipped": 0,
        "recovered": 0,
    }

    try:
        stats["recovered"] = _recover_stale_processing(
            db,
            now=now_utc,
            max_attempts=max_attempts,
        )

        due_ids = [
            row[0]
            for row in (
                db.query(NotificationDelivery.id)
                .filter(
                    NotificationDelivery.status == "pending",
                    NotificationDelivery.scheduled_for <= now_utc,
                )
                .order_by(
                    NotificationDelivery.scheduled_for,
                    NotificationDelivery.id,
                )
                .limit(batch_size)
                .all()
            )
        ]

        for delivery_id in due_ids:
            # Conditional update prevents two workers claiming the same row.
            claim = db.execute(
                update(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery_id,
                    NotificationDelivery.status == "pending",
                    NotificationDelivery.scheduled_for <= now_utc,
                )
                .values(
                    status="processing",
                    attempts=NotificationDelivery.attempts + 1,
                    updated_at=now_utc,
                )
            )

            if claim.rowcount != 1:
                db.rollback()
                stats["skipped"] += 1
                continue

            db.commit()
            db.expire_all()
            stats["claimed"] += 1

            delivery = db.get(NotificationDelivery, delivery_id)

            if delivery is None:
                stats["skipped"] += 1
                continue

            if delivery.channel != "email":
                delivery.status = "failed"
                delivery.last_error = (
                    f"Unsupported delivery channel: {delivery.channel}"
                )[:MAX_ERROR_LENGTH]
                delivery.updated_at = now_utc
                db.commit()
                stats["failed"] += 1
                continue

            preference = (
                db.query(NotificationPreference)
                .filter(
                    NotificationPreference.user_id == delivery.user_id
                )
                .first()
            )

            if (
                preference is None
                or not preference.email_enabled
                or not preference.email_verified
            ):
                _cancel_delivery(
                    db,
                    delivery,
                    "Email notifications are disabled or the email "
                    "address is not verified.",
                    now=now_utc,
                )
                stats["cancelled"] += 1
                continue

            user = db.get(User, delivery.user_id)
            event = (
                db.get(DetectedEvent, delivery.event_id)
                if delivery.event_id is not None
                else None
            )

            if user is None or not user.is_active or not user.email:
                _cancel_delivery(
                    db,
                    delivery,
                    "Recipient account is unavailable or inactive.",
                    now=now_utc,
                )
                stats["cancelled"] += 1
                continue

            if (
                event is None
                or event.user_id != delivery.user_id
                or event.status != "confirmed"
                or event.event_date is None
                or event.date_confidence != "user_confirmed"
            ):
                _cancel_delivery(
                    db,
                    delivery,
                    "The associated event is missing or no longer confirmed.",
                    now=now_utc,
                )
                stats["cancelled"] += 1
                continue

            try:
                subject, body = _event_email(event)

                if sender is not None:
                    # Preserve the existing three-argument sender contract.
                    sender(user.email, subject, body)
                else:
                    # Production delivery sends via the user's Gmail OAuth.
                    send_notification_email_for_user(
                        db,
                        user.id,
                        user.email,
                        subject,
                        body,
                    )

                delivery.status = "sent"
                delivery.sent_at = utc_now_naive()
                delivery.last_error = None
                delivery.updated_at = utc_now_naive()
                db.commit()
                stats["sent"] += 1

            except GmailReauthorizationRequired:
                db.rollback()

                logger.warning(
                    "Gmail reauthorization required for delivery_id=%s",
                    delivery_id,
                )

                try:
                    delivery_failed = _fail_delivery(
                        db,
                        delivery_id,
                        GMAIL_REAUTHORIZATION_ERROR,
                        now=now_utc,
                    )
                except Exception:
                    db.rollback()
                    logger.exception(
                        "Could not mark delivery_id=%s as failed after "
                        "Gmail reauthorization was required",
                        delivery_id,
                    )
                    raise

                if delivery_failed:
                    stats["failed"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as exc:
                db.rollback()

                logger.exception(
                    "Notification delivery failed for delivery_id=%s",
                    delivery_id,
                )

                delivery = db.get(NotificationDelivery, delivery_id)

                if delivery is None:
                    stats["failed"] += 1
                    continue

                error_message = (
                    f"{type(exc).__name__}: {exc}"
                )[:MAX_ERROR_LENGTH]

                delivery.last_error = error_message
                delivery.updated_at = now_utc

                if delivery.attempts >= max_attempts:
                    delivery.status = "failed"
                    db.commit()
                    stats["failed"] += 1
                else:
                    delay = retry_delay_minutes * (
                        2 ** (delivery.attempts - 1)
                    )

                    delivery.status = "pending"
                    delivery.scheduled_for = now_utc + timedelta(
                        minutes=delay
                    )

                    db.commit()
                    stats["retried"] += 1

        return stats

    except Exception:
        db.rollback()
        raise
