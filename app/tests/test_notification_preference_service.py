
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document  # noqa: F401
from app.db.event_model import DetectedEvent  # noqa: F401
from app.db.gmail_connection_model import GmailConnection  # noqa: F401
from app.db.notification_delivery_model import NotificationDelivery  # noqa: F401
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User  # noqa: F401
from app.services.auth_service import create_user
from app.services.notification_preference_service import (
    get_or_create_notification_preference,
    update_notification_preferences,
)


@pytest.fixture
def db(tmp_path):
    database_file = tmp_path / "test_notification_preferences.db"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)

    TestSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    session = TestSession()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def make_user(db):
    return create_user(
        db=db,
        username="preference_user",
        email="preference@example.com",
        password="TestPassword123!",
    )


def test_registration_creates_safe_notification_defaults(db):
    user = make_user(db)

    preference = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == user.id)
        .one()
    )

    assert preference.email_enabled is False
    assert preference.email_verified is False
    assert preference.browser_push_enabled is False
    assert preference.whatsapp_enabled is False
    assert preference.whatsapp_verified is False
    assert preference.reminder_minutes_before == 1440


def test_get_or_create_preserves_existing_preferences(db):
    user = make_user(db)

    first = get_or_create_notification_preference(db, user.id)
    first.reminder_minutes_before = 60
    db.commit()

    second = get_or_create_notification_preference(db, user.id)

    assert second.id == first.id
    assert second.reminder_minutes_before == 60


def test_email_cannot_be_enabled_without_matching_gmail(db):
    user = make_user(db)

    db.add(
        GmailConnection(
            user_id=user.id,
            connected_email="another@example.com",
            encrypted_credentials="test-placeholder",
        )
    )
    db.commit()

    with pytest.raises(ValueError, match="matches your registered"):
        update_notification_preferences(
            db,
            user.id,
            email_enabled=True,
            reminder_minutes_before=1440,
        )

    db.expire_all()
    preference = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == user.id)
        .one()
    )
    assert preference.email_enabled is False


def test_matching_gmail_allows_explicit_email_opt_in(db):
    user = make_user(db)

    db.add(
        GmailConnection(
            user_id=user.id,
            connected_email=user.email,
            encrypted_credentials="test-placeholder",
        )
    )
    db.commit()

    preference = update_notification_preferences(
        db,
        user.id,
        email_enabled=True,
        reminder_minutes_before=60,
    )

    assert preference.email_enabled is True
    assert preference.email_verified is True
    assert preference.reminder_minutes_before == 60


@pytest.mark.parametrize("invalid_minutes", [-1, 43201, True, 1.5, "60"])
def test_invalid_reminder_timing_is_rejected(db, invalid_minutes):
    user = make_user(db)

    with pytest.raises(ValueError, match="between 0 minutes and 30 days"):
        update_notification_preferences(
            db,
            user.id,
            email_enabled=False,
            reminder_minutes_before=invalid_minutes,
        )


def test_missing_user_is_rejected(db):
    with pytest.raises(ValueError, match="does not exist"):
        get_or_create_notification_preference(db, 99999)
