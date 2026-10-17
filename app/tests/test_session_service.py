from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.user_session_model import UserSession
from app.models.user import User
from app.services.auth_service import create_user
from app.services.session_service import (
    SESSION_LIFETIME_DAYS,
    create_user_session,
    get_user_for_session,
    revoke_user_session,
)


def make_session_factory(tmp_path):
    database_file = tmp_path / "test_sessions.db"
    engine = create_engine(
        f"sqlite:///{database_file}",
        connect_args={"check_same_thread": False},
    )

    # Import all models needed by Base before creating tables.
    from app.db import user_session_model  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def make_user(db):
    return create_user(
        db=db,
        username="sessionuser",
        email="session@example.com",
        password="TestPassword123!",
    )


def test_create_session_stores_only_token_hash(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            user = make_user(db)
            token, expires_at = create_user_session(db, user.id)

            record = db.scalar(
                select(UserSession).where(UserSession.user_id == user.id)
            )

            assert token
            assert record is not None
            assert record.token_hash != token
            assert len(record.token_hash) == 64
            assert expires_at.tzinfo is not None
            assert expires_at > datetime.now(timezone.utc)
            assert record.expires_at is not None
    finally:
        engine.dispose()


def test_session_restores_active_user(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            user = make_user(db)
            token, _ = create_user_session(db, user.id)

            restored_user = get_user_for_session(db, token)

            assert restored_user is not None
            assert restored_user.id == user.id
            assert restored_user.username == user.username
    finally:
        engine.dispose()


def test_expired_session_is_rejected(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            user = make_user(db)
            token, _ = create_user_session(db, user.id)

            record = db.scalar(
                select(UserSession).where(UserSession.user_id == user.id)
            )
            record.expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=1
            )
            db.commit()

            assert get_user_for_session(db, token) is None
    finally:
        engine.dispose()


def test_revoked_session_cannot_restore_user(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            user = make_user(db)
            token, _ = create_user_session(db, user.id)

            assert revoke_user_session(db, token) is True
            assert get_user_for_session(db, token) is None
            assert revoke_user_session(db, token) is False
    finally:
        engine.dispose()


def test_missing_and_invalid_tokens_are_rejected(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            make_user(db)

            assert get_user_for_session(db, None) is None
            assert get_user_for_session(db, "") is None
            assert get_user_for_session(db, "invalid-token") is None
            assert revoke_user_session(db, None) is False
            assert revoke_user_session(db, "invalid-token") is False
    finally:
        engine.dispose()


def test_session_cannot_be_created_for_missing_user(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            try:
                create_user_session(db, 999999)
            except ValueError as error:
                assert "Cannot create a session" in str(error)
            else:
                raise AssertionError("Expected ValueError for missing user")
    finally:
        engine.dispose()


def test_session_expiry_uses_configured_lifetime(tmp_path):
    engine, factory = make_session_factory(tmp_path)

    try:
        with factory() as db:
            user = make_user(db)
            before = datetime.now(timezone.utc)
            _, expires_at = create_user_session(db, user.id)
            after = datetime.now(timezone.utc)

            earliest = before + timedelta(days=SESSION_LIFETIME_DAYS)
            latest = after + timedelta(days=SESSION_LIFETIME_DAYS)

            assert earliest <= expires_at <= latest
    finally:
        engine.dispose()
