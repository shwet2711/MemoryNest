from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
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
        raise ValueError(
            "Username or email is already registered."
        )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


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

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user