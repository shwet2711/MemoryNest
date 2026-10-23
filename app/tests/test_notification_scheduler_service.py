from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User
from app.services.notification_scheduler_service import (
    schedule_event_reminders,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'scheduler.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def setup_event(db, event_date=date(2026, 10, 25)):
    user = User(
        username="scheduler_user",
        email="scheduler@example.com",
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()

    document = Document(
        user_id=user.id,
        original_filename="exam.txt",
        stored_filename="scheduler-exam.txt",
        file_path="exam.txt",
        file_type="txt",
        file_size=100,
    )
    db.add(document)
    db.flush()

    event = DetectedEvent(
        user_id=user.id,
        document_id=document.id,
        title="Exam",
        event_type="exam",
        event_date=event_date,
        event_end_date=None,
        date_text=event_date.isoformat(),
        date_confidence="user_confirmed",
        source_excerpt="Exam date",
        status="confirmed",
    )
    db.add(event)
    db.flush()
    return user, event


def setup_preference(db, user_id, **overrides):
    values = {
        "email_enabled": True,
        "email_verified": True,
        "browser_push_enabled": False,
        "whatsapp_enabled": False,
        "whatsapp_verified": False,
        "whatsapp_phone": None,
        "whatsapp_opted_in_at": None,
        "reminder_minutes_before": 1440,
    }
    values.update(overrides)
    preference = NotificationPreference(user_id=user_id, **values)
    db.add(preference)
    db.flush()
    return preference


def test_date_only_event_schedules_24_hours_before_at_9am_ist(db_session):
    user, event = setup_event(db_session)
    setup_preference(db_session, user.id)

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, 0, 0, tzinfo=UTC),
    )

    assert len(created) == 1
    assert created[0].channel == "email"
    # 25 Oct 09:00 IST = 25 Oct 03:30 UTC.
    # Twenty-four hours before = 24 Oct 03:30 UTC.
    assert created[0].scheduled_for == datetime(2026, 10, 24, 3, 30)
    assert created[0].status == "pending"


def test_scheduling_is_idempotent(db_session):
    user, event = setup_event(db_session)
    setup_preference(db_session, user.id)
    now = datetime(2026, 10, 20, 0, 0, tzinfo=UTC)

    first = schedule_event_reminders(db_session, event, now=now)
    second = schedule_event_reminders(db_session, event, now=now)

    assert len(first) == 1
    assert second == []
    assert db_session.query(NotificationDelivery).count() == 1


def test_unverified_email_is_not_scheduled(db_session):
    user, event = setup_event(db_session)
    setup_preference(
        db_session,
        user.id,
        email_enabled=True,
        email_verified=False,
    )

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )

    assert created == []
    assert db_session.query(NotificationDelivery).count() == 0


def test_whatsapp_requires_verification_opt_in_and_phone(db_session):
    user, event = setup_event(db_session)
    setup_preference(
        db_session,
        user.id,
        email_enabled=False,
        whatsapp_enabled=True,
        whatsapp_verified=True,
        whatsapp_phone=None,
        whatsapp_opted_in_at=datetime(2026, 10, 1),
    )

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )

    assert created == []


def test_past_reminder_is_not_moved_to_future(db_session):
    user, event = setup_event(db_session, date(2026, 10, 20))
    setup_preference(db_session, user.id)

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, 4, 0, tzinfo=UTC),
    )

    assert created == []
    assert db_session.query(NotificationDelivery).count() == 0


def test_unconfirmed_or_unreviewed_event_is_not_scheduled(db_session):
    user, event = setup_event(db_session)
    setup_preference(db_session, user.id)
    event.status = "pending_review"

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )

    assert created == []

    event.status = "confirmed"
    event.date_confidence = "needs_review"

    created = schedule_event_reminders(
        db_session,
        event,
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )
    assert created == []


def test_date_change_cancels_obsolete_pending_reminder(db_session):
    user, event = setup_event(db_session)
    setup_preference(db_session, user.id)
    now = datetime(2026, 10, 20, tzinfo=UTC)

    schedule_event_reminders(db_session, event, now=now)
    db_session.flush()

    event.event_date = date(2026, 10, 26)
    schedule_event_reminders(db_session, event, now=now)

    deliveries = (
        db_session.query(NotificationDelivery)
        .order_by(NotificationDelivery.id)
        .all()
    )
    assert len(deliveries) == 2
    assert deliveries[0].status == "cancelled"
    assert deliveries[1].status == "pending"


def test_invalid_reminder_lead_is_rejected(db_session):
    user, event = setup_event(db_session)
    setup_preference(
        db_session,
        user.id,
        reminder_minutes_before=-1,
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        schedule_event_reminders(
            db_session,
            event,
            now=datetime(2026, 10, 20, tzinfo=UTC),
        )


def test_cancelled_reminder_is_reactivated_when_preference_is_restored(
    db_session,
):
    user, event = setup_event(db_session)
    preference = setup_preference(
        db_session,
        user.id,
        reminder_minutes_before=2880,
    )
    now = datetime(2026, 10, 20, 0, 0, tzinfo=UTC)

    # Initially schedule the 48-hour reminder.
    first = schedule_event_reminders(db_session, event, now=now)
    assert len(first) == 1
    assert first[0].status == "pending"

    # Switching to 7 days makes the reminder time a past date.
    preference.reminder_minutes_before = 10080
    schedule_event_reminders(db_session, event, now=now)
    db_session.flush()

    deliveries = db_session.query(NotificationDelivery).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "cancelled"

    # Restoring 48 hours must reactivate the existing record.
    preference.reminder_minutes_before = 2880
    schedule_event_reminders(db_session, event, now=now)
    db_session.flush()

    deliveries = db_session.query(NotificationDelivery).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"
    assert deliveries[0].scheduled_for == datetime(2026, 10, 23, 3, 30)
    assert deliveries[0].attempts == 0
    assert deliveries[0].last_error is None
