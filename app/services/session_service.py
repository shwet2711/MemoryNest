import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.user_session_model import UserSession
from app.models.user import User


SESSION_LIFETIME_DAYS = 14


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user_session(
    db: Session,
    user_id: int,
) -> tuple[str, datetime]:
    """Create a session and return its raw token and expiry."""

    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise ValueError("user_id must be an integer.")

    if user_id <= 0:
        raise ValueError("user_id must be positive.")

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise ValueError("Cannot create a session for this user.")

    token = secrets.token_urlsafe(32)
    expires_at = _utc_now() + timedelta(
        days=SESSION_LIFETIME_DAYS
    )

    session_record = UserSession(
        user_id=user_id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
    )

    db.add(session_record)
    db.commit()

    return token, expires_at


def get_user_for_session(
    db: Session,
    token: str | None,
) -> User | None:
    """Return an active user for a valid, unexpired session token."""

    if not token or not isinstance(token, str):
        return None

    session_record = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == _hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )

    if session_record is None:
        return None

    expires_at = session_record.expires_at

    # SQLite may return timezone-aware columns as naive datetimes.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= _utc_now():
        return None

    user = db.get(User, session_record.user_id)

    if user is None or not user.is_active:
        return None

    return user


def revoke_user_session(
    db: Session,
    token: str | None,
) -> bool:
    """Revoke a session token if it exists and is still active."""

    if not token or not isinstance(token, str):
        return False

    session_record = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == _hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )

    if session_record is None:
        return False

    session_record.revoked_at = _utc_now()
    db.commit()

    return True
