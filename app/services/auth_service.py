
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.notification_preference_model import NotificationPreference
from app.models.user import User


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
) -> User:
    username = username.strip()
    email = email.strip().lower()

    existing_user = db.scalar(
        select(User).where(
            or_(
                User.username == username,
                User.email == email,
            )
        )
    )

    if existing_user:
        raise ValueError("Username or email is already registered.")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )

    try:
        db.add(user)
        db.flush()

        db.add(
            NotificationPreference(
                user_id=user.id,
                email_enabled=False,
                email_verified=False,
                browser_push_enabled=False,
                whatsapp_enabled=False,
                whatsapp_verified=False,
                reminder_minutes_before=1440,
            )
        )

        db.commit()
        db.refresh(user)
        return user

    except Exception:
        db.rollback()
        raise


def authenticate_user(
    db: Session,
    username_or_email: str,
    password: str,
) -> User | None:
    identifier = username_or_email.strip()

    user = db.scalar(
        select(User).where(
            or_(
                User.username == identifier,
                User.email == identifier.lower(),
            )
        )
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.password_hash)
    ):
        return None

    return user


def change_user_password(
    db: Session,
    user_id: int,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> None:
    """Verify the current password and securely change it."""

    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("Invalid user account.")

    if not current_password:
        raise ValueError("Enter your current password.")

    if not new_password:
        raise ValueError("Enter a new password.")

    if len(new_password) < 12:
        raise ValueError(
        "Your new password must contain at least 12 characters."
    )

    if len(new_password.encode("utf-8")) > 72:
        raise ValueError(
        "Your new password is too long for the configured password hasher."
    )

    if new_password != confirm_password:
        raise ValueError("The new password and confirmation do not match.")

    if current_password == new_password:
        raise ValueError("Your new password must differ from your current password.")

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise ValueError("Your account could not be verified.")

    if not verify_password(current_password, user.password_hash):
        raise ValueError("Your current password is incorrect.")

    try:
        user.password_hash = hash_password(new_password)
        db.commit()
    except Exception:
        db.rollback()
        raise
