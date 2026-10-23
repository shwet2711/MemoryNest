from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document  # noqa: F401
from app.db.event_model import DetectedEvent  # noqa: F401
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User


@pytest.fixture
def db_session(tmp_path):
    """Provide an isolated database for notification model tests."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'notification_models.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = session_factory()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_user(db_session, suffix="one"):
    """Create a valid test user."""
    user = User(
        username=f"notification_{suffix}",
        email=f"notification_{suffix}@example.com",
        password_hash="test-only-password-hash",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_notification_preferences_have_safe_defaults(db_session):
    user = create_user(db_session)

    preference = NotificationPreference(user_id=user.id)
    db_session.add(preference)
    db_session.commit()
    db_session.refresh(preference)

    assert preference.email_enabled is False
    assert preference.email_verified is False
    assert preference.browser_push_enabled is False
    assert preference.whatsapp_enabled is False
    assert preference.whatsapp_verified is False
    assert preference.whatsapp_phone is None
    assert preference.reminder_minutes_before == 1440


def test_user_can_have_only_one_preference_record(db_session):
    user = create_user(db_session)

    db_session.add(NotificationPreference(user_id=user.id))
    db_session.commit()

    db_session.add(NotificationPreference(user_id=user.id))

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_delivery_record_has_pending_defaults(db_session):
    user = create_user(db_session)

    delivery = NotificationDelivery(
        user_id=user.id,
        event_id=None,
        channel="email",
        reminder_key="user-one-event-one-email",
        scheduled_for=datetime(2026, 10, 20, 9, 0),
    )
    db_session.add(delivery)
    db_session.commit()
    db_session.refresh(delivery)

    assert delivery.status == "pending"
    assert delivery.attempts == 0
    assert delivery.sent_at is None
    assert delivery.last_error is None
    assert delivery.event_id is None


def test_duplicate_reminder_key_is_rejected(db_session):
    user = create_user(db_session)

    first = NotificationDelivery(
        user_id=user.id,
        channel="email",
        reminder_key="same-reminder-key",
        scheduled_for=datetime(2026, 10, 20, 9, 0),
    )
    db_session.add(first)
    db_session.commit()

    duplicate = NotificationDelivery(
        user_id=user.id,
        channel="whatsapp",
        reminder_key="same-reminder-key",
        scheduled_for=datetime(2026, 10, 20, 9, 0),
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_different_reminder_keys_can_be_stored(db_session):
    user = create_user(db_session)

    db_session.add_all(
        [
            NotificationDelivery(
                user_id=user.id,
                channel="email",
                reminder_key="event-1-email",
                scheduled_for=datetime(2026, 10, 20, 9, 0),
            ),
            NotificationDelivery(
                user_id=user.id,
                channel="whatsapp",
                reminder_key="event-1-whatsapp",
                scheduled_for=datetime(2026, 10, 20, 9, 0),
            ),
        ]
    )
    db_session.commit()

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(NotificationDelivery.user_id == user.id)
        .all()
    )

    assert len(deliveries) == 2
    assert {item.channel for item in deliveries} == {"email", "whatsapp"}
