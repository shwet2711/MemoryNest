
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.services.auth_service import (
    authenticate_user,
    change_user_password,
    create_user,
)


@pytest.fixture
def db_session(tmp_path):
    database_file = tmp_path / "test_password_management.db"
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
    db = TestSession()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def test_user(db_session):
    return create_user(
        db=db_session,
        username="passwordtest",
        email="passwordtest@example.com",
        password="OriginalPassword123!",
    )


def test_change_password_success(db_session, test_user):
    change_user_password(
        db_session,
        test_user.id,
        "OriginalPassword123!",
        "BrandNewPassword456!",
        "BrandNewPassword456!",
    )

    assert authenticate_user(
        db_session, "passwordtest", "BrandNewPassword456!"
    ) is not None

    assert authenticate_user(
        db_session, "passwordtest", "OriginalPassword123!"
    ) is None


@pytest.mark.parametrize(
    ("current", "new", "confirmation", "expected"),
    [
        ("WrongPassword123!", "BrandNewPassword456!",
         "BrandNewPassword456!", "current password is incorrect"),
        ("OriginalPassword123!", "short", "short",
         "at least 12 characters"),
        ("OriginalPassword123!", "BrandNewPassword456!",
         "DifferentPassword789!", "do not match"),
        ("OriginalPassword123!", "OriginalPassword123!",
         "OriginalPassword123!", "differ from your current password"),
    ],
)
def test_change_password_rejects_invalid_input(
    db_session, test_user, current, new, confirmation, expected
):
    old_hash = test_user.password_hash

    with pytest.raises(ValueError, match=expected):
        change_user_password(
            db_session,
            test_user.id,
            current,
            new,
            confirmation,
        )

    db_session.refresh(test_user)
    assert test_user.password_hash == old_hash
    assert authenticate_user(
        db_session, "passwordtest", "OriginalPassword123!"
    ) is not None


def test_change_password_rejects_unknown_user(db_session):
    with pytest.raises(ValueError, match="could not be verified"):
        change_user_password(
            db_session,
            999999,
            "OriginalPassword123!",
            "BrandNewPassword456!",
            "BrandNewPassword456!",
        )
