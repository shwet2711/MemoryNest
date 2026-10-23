
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User
from app.services.auth_service import authenticate_user, create_user


def test_user_creation_and_login(tmp_path):
    database_file = tmp_path / "test_memorynest.db"
    test_engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    db = TestSession()

    try:
        user = create_user(
            db=db,
            username="testuser",
            email="test@example.com",
            password="TestPassword123!",
        )

        assert user.id is not None
        assert user.username == "testuser"

        preference = (
            db.query(NotificationPreference)
            .filter(NotificationPreference.user_id == user.id)
            .one()
        )
        assert preference.email_enabled is False
        assert preference.email_verified is False
        assert preference.reminder_minutes_before == 1440

        authenticated_user = authenticate_user(
            db=db,
            username_or_email="testuser",
            password="TestPassword123!",
        )
        assert authenticated_user is not None
        assert authenticated_user.id == user.id

        wrong_password = authenticate_user(
            db=db,
            username_or_email="testuser",
            password="WrongPassword",
        )
        assert wrong_password is None

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
