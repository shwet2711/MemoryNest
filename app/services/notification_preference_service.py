
from sqlalchemy.orm import Session

from app.db.event_model import DetectedEvent
from app.db.gmail_connection_model import GmailConnection
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User
from app.services.notification_scheduler_service import (
    schedule_event_reminders,
)


MAX_REMINDER_MINUTES = 30 * 24 * 60


def get_or_create_notification_preference(
    db: Session,
    user_id: int,
) -> NotificationPreference:
    """Return a user's preferences, creating safe defaults if necessary."""
    user = db.get(User, int(user_id))
    if user is None:
        raise ValueError("The MemoryNest user does not exist.")

    preference = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == int(user_id))
        .first()
    )

    if preference is None:
        preference = NotificationPreference(
            user_id=int(user_id),
            email_enabled=False,
            email_verified=False,
            browser_push_enabled=False,
            whatsapp_enabled=False,
            whatsapp_verified=False,
            reminder_minutes_before=1440,
        )
        db.add(preference)
        db.flush()

    return preference


def update_notification_preferences(
    db: Session,
    user_id: int,
    *,
    email_enabled: bool,
    reminder_minutes_before: int,
) -> NotificationPreference:
    """Save email reminder preferences and reconcile scheduled reminders.

    Email is eligible only when the user explicitly enables it and the
    connected Gmail identity matches the user's registered email address.
    The Gmail OAuth flow must validate the identity before saving it.
    """
    if not isinstance(email_enabled, bool):
        raise ValueError("Email reminder preference must be true or false.")

    if (
        isinstance(reminder_minutes_before, bool)
        or not isinstance(reminder_minutes_before, int)
        or not 0 <= reminder_minutes_before <= MAX_REMINDER_MINUTES
    ):
        raise ValueError(
            "Reminder timing must be between 0 minutes and 30 days."
        )

    try:
        user = db.get(User, int(user_id))
        if user is None:
            raise ValueError("The MemoryNest user does not exist.")

        preference = get_or_create_notification_preference(
            db, int(user_id)
        )

        connection = (
            db.query(GmailConnection)
            .filter(GmailConnection.user_id == int(user_id))
            .first()
        )

        addresses_match = (
            connection is not None
            and connection.connected_email.strip().casefold()
            == user.email.strip().casefold()
        )

        if email_enabled and not addresses_match:
            raise ValueError(
                "To enable email reminders, connect the Gmail account "
                "that matches your registered MemoryNest email address."
            )

        preference.email_enabled = email_enabled
        preference.email_verified = bool(addresses_match)
        preference.reminder_minutes_before = reminder_minutes_before

        # Persist preference changes to the current transaction before
        # the scheduler queries them. This also works with autoflush=False.
        db.flush()

        # Reconcile existing events whenever reminder settings change.

        # Reconcile existing events whenever reminder settings change.
        events = (
            db.query(DetectedEvent)
            .filter(DetectedEvent.user_id == int(user_id))
            .all()
        )

        for event in events:
            schedule_event_reminders(db, event)

        db.commit()
        db.refresh(preference)
        return preference

    except Exception:
        db.rollback()
        raise
