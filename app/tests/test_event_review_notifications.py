from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.db.notification_delivery_model import NotificationDelivery
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User
from app.services import calendar_service


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'event_review.sqlite').as_posix()}",
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


def setup_review_data(db):
    user = User(
        username="review_test_user",
        email="review-test@example.com",
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()

    document = Document(
        user_id=user.id,
        original_filename="exam.txt",
        stored_filename="review-test-exam.txt",
        file_path="exam.txt",
        file_type="txt",
        file_size=100,
    )
    db.add(document)
    db.flush()

    event = DetectedEvent(
        user_id=user.id,
        document_id=document.id,
        title="Detected Exam",
        event_type="exam",
        event_date=None,
        event_end_date=None,
        date_text="date needs confirmation",
        date_confidence="needs_review",
        source_excerpt="Final exam announcement",
        status="pending_review",
    )
    db.add(event)
    db.flush()

    preference = NotificationPreference(
        user_id=user.id,
        email_enabled=True,
        email_verified=True,
        browser_push_enabled=False,
        whatsapp_enabled=False,
        whatsapp_verified=False,
        whatsapp_phone=None,
        whatsapp_opted_in_at=None,
        reminder_minutes_before=1440,
    )
    db.add(preference)
    db.commit()

    return user, event


def review_event(db, user_id, event_id, event_date, *, title="Final Exam"):
    return calendar_service.update_event_review(
        db,
        user_id,
        event_id,
        title=title,
        event_type="exam",
        event_date_text=event_date.isoformat(),
        event_end_date_text="",
        status="confirmed",
        original_date_text="Exam date from uploaded document",
    )


def test_confirming_event_schedules_one_email_reminder(db_session):
    user, event = setup_review_data(db_session)
    future_date = date.today() + timedelta(days=30)

    reviewed = review_event(
        db_session,
        user.id,
        event.id,
        future_date,
    )

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(NotificationDelivery.event_id == event.id)
        .all()
    )

    assert reviewed.status == "confirmed"
    assert reviewed.date_confidence == "user_confirmed"
    assert reviewed.event_date == future_date
    assert len(deliveries) == 1
    assert deliveries[0].channel == "email"
    assert deliveries[0].status == "pending"
    assert deliveries[0].scheduled_for is not None


def test_repeated_event_review_does_not_duplicate_reminders(db_session):
    user, event = setup_review_data(db_session)
    future_date = date.today() + timedelta(days=30)

    review_event(db_session, user.id, event.id, future_date)
    review_event(
        db_session,
        user.id,
        event.id,
        future_date,
        title="Final Exam Updated",
    )

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(NotificationDelivery.event_id == event.id)
        .all()
    )

    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"

    saved_event = (
        db_session.query(DetectedEvent)
        .filter(DetectedEvent.id == event.id)
        .one()
    )
    assert saved_event.title == "Final Exam Updated"


def test_scheduler_failure_rolls_back_event_and_reminder(db_session, monkeypatch):
    user, event = setup_review_data(db_session)
    future_date = date.today() + timedelta(days=30)
    event_id = event.id
    user_id = user.id

    def fail_after_adding_delivery(db, current_event):
        db.add(
            NotificationDelivery(
                user_id=current_event.user_id,
                event_id=current_event.id,
                channel="email",
                reminder_key=f"test-failure:event:{current_event.id}",
                scheduled_for=datetime(2099, 1, 1, 3, 30),
                status="pending",
            )
        )
        db.flush()
        raise RuntimeError("Simulated scheduler failure")

    monkeypatch.setattr(
        calendar_service,
        "schedule_event_reminders",
        fail_after_adding_delivery,
    )

    with pytest.raises(RuntimeError, match="Simulated scheduler failure"):
        review_event(
            db_session,
            user_id,
            event_id,
            future_date,
        )

    saved_event = (
        db_session.query(DetectedEvent)
        .filter(DetectedEvent.id == event_id)
        .one()
    )
    delivery_count = (
        db_session.query(NotificationDelivery)
        .filter(NotificationDelivery.event_id == event_id)
        .count()
    )

    assert saved_event.status == "pending_review"
    assert saved_event.title == "Detected Exam"
    assert saved_event.event_date is None
    assert saved_event.date_confidence == "needs_review"
    assert delivery_count == 0
