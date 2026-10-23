from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.event_model import DetectedEvent
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import NotificationPreference


EVENT_TIMEZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_EVENT_TIME = time(9, 0)


def _as_utc_naive(value: datetime) -> datetime:
    """Normalize an aware datetime to naive UTC for database storage."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _event_datetime(event_date: date) -> datetime:
    """Interpret a date-only event as 9:00 AM India time."""
    local_datetime = datetime.combine(event_date, DEFAULT_EVENT_TIME)
    return local_datetime.replace(tzinfo=EVENT_TIMEZONE)


def _eligible_channels(preference: NotificationPreference) -> list[str]:
    """Return channels explicitly enabled and eligible for scheduling."""
    channels = []

    if preference.email_enabled and preference.email_verified:
        channels.append("email")

    # This queues a delivery record only. A working push sender and
    # browser subscription are separate implementation requirements.
    if preference.browser_push_enabled:
        channels.append("browser_push")

    if (
        preference.whatsapp_enabled
        and preference.whatsapp_verified
        and preference.whatsapp_opted_in_at is not None
        and bool((preference.whatsapp_phone or "").strip())
    ):
        channels.append("whatsapp")

    return channels


def schedule_event_reminders(
    db: Session,
    event: DetectedEvent,
    *,
    now: datetime | None = None,
) -> list[NotificationDelivery]:
    """Schedule eligible reminders and reconcile obsolete pending reminders.

    Only confirmed events with user-confirmed dates are eligible.
    Scheduled timestamps are stored as naive UTC values.
    """
    if now is None:
        now = datetime.now(UTC)
    now_utc = _as_utc_naive(now)

    preference = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == event.user_id)
        .first()
    )

    lead_minutes = 1440
    channels = []

    if preference is not None:
        lead_minutes = preference.reminder_minutes_before

        if (
            isinstance(lead_minutes, bool)
            or not isinstance(lead_minutes, int)
            or lead_minutes < 0
        ):
            raise ValueError(
                "Reminder minutes before must be a non-negative integer."
            )

        channels = _eligible_channels(preference)

    eligible = (
        event.status == "confirmed"
        and event.event_date is not None
        and event.date_confidence == "user_confirmed"
        and (
            event.event_end_date is None
            or event.event_end_date >= event.event_date
        )
        and preference is not None
    )

    desired: dict[str, datetime] = {}

    if eligible:
        event_instant = _event_datetime(event.event_date)
        scheduled_for = _as_utc_naive(
            event_instant - timedelta(minutes=lead_minutes)
        )

        # Never shift a past reminder forward to make it deliverable.
        if scheduled_for > now_utc:
            for channel in channels:
                key = (
                    f"event:{event.id}:date:{event.event_date.isoformat()}"
                    f":channel:{channel}:lead:{lead_minutes}"
                )
                desired[key] = scheduled_for

    existing = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.user_id == event.user_id,
            NotificationDelivery.event_id == event.id,
        )
        .all()
    )

    # Cancel obsolete pending reminders when a date, preference, or status
    # changes. Delivered records are retained for audit history.
    for delivery in existing:
        if (
            delivery.status == "pending"
            and delivery.reminder_key not in desired
        ):
            delivery.status = "cancelled"

    existing_by_key = {
        delivery.reminder_key: delivery
        for delivery in existing
    }
    created = []

    for key, scheduled_for in desired.items():
        existing_delivery = existing_by_key.get(key)

        if existing_delivery is not None:
            if existing_delivery.status == "cancelled":
                # Reactivate the same reminder instead of inserting a
                # duplicate reminder_key, which must remain unique.
                existing_delivery.status = "pending"
                existing_delivery.scheduled_for = scheduled_for
                existing_delivery.attempts = 0
                existing_delivery.last_error = None
                existing_delivery.sent_at = None

            # Keep existing pending or sent records unchanged.
            continue

        delivery = NotificationDelivery(
            user_id=event.user_id,
            event_id=event.id,
            channel=key.split(":channel:", 1)[1].split(":lead:", 1)[0],
            reminder_key=key,
            scheduled_for=scheduled_for,
            status="pending",
        )
        db.add(delivery)
        created.append(delivery)

    # The caller owns the transaction and commits the event and its reminders
    # together. This keeps scheduling atomic with event confirmation.
    db.flush()
    return created
