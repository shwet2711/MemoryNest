from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User
from app.services.gmail_service import GmailReauthorizationRequired
from app.services.notification_delivery_worker import (
    process_due_notifications,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'delivery_worker.sqlite').as_posix()}",
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


def setup_delivery(
    db,
    *,
    channel="email",
    scheduled_for=None,
    email_enabled=True,
    email_verified=True,
    event_status="confirmed",
    date_confidence="user_confirmed",
):
    user = User(
        username="delivery_test_user",
        email="delivery-test@example.com",
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()

    document = Document(
        user_id=user.id,
        original_filename="exam.txt",
        stored_filename="delivery-test-exam.txt",
        file_path="exam.txt",
        file_type="txt",
        file_size=100,
    )
    db.add(document)
    db.flush()

    event = DetectedEvent(
        user_id=user.id,
        document_id=document.id,
        title="Final Exam",
        event_type="exam",
        event_date=date(2026, 12, 20),
        event_end_date=None,
        date_text="20 December 2026",
        date_confidence=date_confidence,
        source_excerpt="Final exam announcement",
        status=event_status,
    )
    db.add(event)
    db.flush()

    preference = NotificationPreference(
        user_id=user.id,
        email_enabled=email_enabled,
        email_verified=email_verified,
        browser_push_enabled=False,
        whatsapp_enabled=False,
        whatsapp_verified=False,
        whatsapp_phone=None,
        whatsapp_opted_in_at=None,
        reminder_minutes_before=1440,
    )
    db.add(preference)

    now = datetime(2026, 10, 20, 4, 0)
    delivery = NotificationDelivery(
        user_id=user.id,
        event_id=event.id,
        channel=channel,
        reminder_key=f"test-delivery-{user.id}-{channel}",
        scheduled_for=scheduled_for or now - timedelta(minutes=1),
        status="pending",
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    return user, event, preference, delivery, now


def test_due_email_is_sent_and_marked_sent(db_session):
    _, _, _, delivery, now = setup_delivery(db_session)
    sent = []

    def fake_sender(recipient, subject, body):
        sent.append((recipient, subject, body))

    stats = process_due_notifications(
        db_session,
        sender=fake_sender,
        now=now,
    )

    db_session.refresh(delivery)

    assert stats["sent"] == 1
    assert len(sent) == 1
    assert sent[0][0] == "delivery-test@example.com"
    assert "Final Exam" in sent[0][1]
    assert "20 December 2026" in sent[0][2]
    assert delivery.status == "sent"
    assert delivery.attempts == 1
    assert delivery.sent_at is not None
    assert delivery.last_error is None


def test_future_delivery_is_not_claimed(db_session):
    future = datetime(2026, 10, 20, 5, 0)
    _, _, _, delivery, now = setup_delivery(
        db_session,
        scheduled_for=future,
    )

    stats = process_due_notifications(
        db_session,
        sender=lambda *args: pytest.fail("Sender must not be called"),
        now=now,
    )

    db_session.refresh(delivery)

    assert stats["claimed"] == 0
    assert delivery.status == "pending"
    assert delivery.attempts == 0


@pytest.mark.parametrize(
    ("email_enabled", "email_verified"),
    [(False, True), (True, False)],
)
def test_disabled_or_unverified_email_is_cancelled(
    db_session,
    email_enabled,
    email_verified,
):
    _, _, _, delivery, now = setup_delivery(
        db_session,
        email_enabled=email_enabled,
        email_verified=email_verified,
    )

    stats = process_due_notifications(
        db_session,
        sender=lambda *args: pytest.fail("Email must not be sent"),
        now=now,
    )

    db_session.refresh(delivery)

    assert stats["cancelled"] == 1
    assert delivery.status == "cancelled"
    assert delivery.last_error


def test_unconfirmed_event_is_cancelled(db_session):
    _, _, _, delivery, now = setup_delivery(
        db_session,
        event_status="pending_review",
    )

    stats = process_due_notifications(
        db_session,
        sender=lambda *args: pytest.fail("Email must not be sent"),
        now=now,
    )

    db_session.refresh(delivery)

    assert stats["cancelled"] == 1
    assert delivery.status == "cancelled"


def test_sender_failure_schedules_retry(db_session):
    _, _, _, delivery, now = setup_delivery(
        db_session,
        scheduled_for=datetime(2026, 10, 20, 3, 59),
    )

    def failing_sender(*args):
        raise RuntimeError("Temporary SMTP failure")

    stats = process_due_notifications(
        db_session,
        sender=failing_sender,
        now=now,
        max_attempts=3,
        retry_delay_minutes=5,
    )

    db_session.refresh(delivery)

    assert stats["retried"] == 1
    assert delivery.status == "pending"
    assert delivery.attempts == 1
    assert delivery.scheduled_for == now + timedelta(minutes=5)
    assert "Temporary SMTP failure" in delivery.last_error


def test_gmail_reauthorization_failure_is_not_retried(
    db_session,
    monkeypatch,
):
    _, _, _, delivery, now = setup_delivery(db_session)

    def require_reauthorization(*args, **kwargs):
        raise GmailReauthorizationRequired(
            "Gmail authorization must be renewed."
        )

    monkeypatch.setattr(
        "app.services.notification_delivery_worker."
        "send_notification_email_for_user",
        require_reauthorization,
    )

    stats = process_due_notifications(
        db_session,
        now=now,
        max_attempts=3,
        retry_delay_minutes=5,
    )

    db_session.refresh(delivery)

    assert stats["failed"] == 1
    assert stats["retried"] == 0
    assert delivery.status == "failed"
    assert delivery.attempts == 1
    assert delivery.scheduled_for == now - timedelta(minutes=1)
    assert "Reconnect Gmail" in delivery.last_error

def test_exhausted_attempts_mark_delivery_failed(db_session):
    _, _, _, delivery, now = setup_delivery(db_session)
    delivery.attempts = 1
    db_session.commit()

    def failing_sender(*args):
        raise RuntimeError("Permanent test failure")

    stats = process_due_notifications(
        db_session,
        sender=failing_sender,
        now=now,
        max_attempts=2,
    )

    db_session.refresh(delivery)

    assert stats["failed"] == 1
    assert delivery.status == "failed"
    assert delivery.attempts == 2
    assert "Permanent test failure" in delivery.last_error


def test_unsupported_channel_is_not_marked_sent(db_session):
    _, _, _, delivery, now = setup_delivery(
        db_session,
        channel="browser_push",
    )

    stats = process_due_notifications(
        db_session,
        sender=lambda *args: pytest.fail("Email sender must not be called"),
        now=now,
    )

    db_session.refresh(delivery)

    assert stats["failed"] == 1
    assert delivery.status == "failed"
    assert "Unsupported delivery channel" in delivery.last_error


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_size": 0},
        {"max_attempts": 0},
        {"retry_delay_minutes": 0},
    ],
)
def test_invalid_worker_settings_are_rejected(db_session, kwargs):
    with pytest.raises(ValueError):
        process_due_notifications(db_session, **kwargs)
