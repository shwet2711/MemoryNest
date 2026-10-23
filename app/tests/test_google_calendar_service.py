
from datetime import date
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

import app.services.google_calendar_service as service


def test_stable_google_event_id_is_deterministic():
    first = service._stable_google_event_id(10, 25)
    second = service._stable_google_event_id(10, 25)

    assert first == second
    assert len(first) == 64
    assert all(char in "0123456789abcdef" for char in first)


def test_stable_google_event_ids_differ_by_user():
    first = service._stable_google_event_id(10, 25)
    second = service._stable_google_event_id(11, 25)

    assert first != second


def test_build_google_event_uses_exclusive_end_date():
    event = SimpleNamespace(
        id=1,
        title="Project Review",
        event_type="meeting",
        event_date=date(2026, 10, 25),
        event_end_date=date(2026, 10, 27),
        source_excerpt="Review project milestones.",
    )

    payload = service._build_google_event(
        event,
        "project_review.txt",
    )

    assert payload["summary"] == "Project Review"
    assert payload["start"] == {"date": "2026-10-25"}
    assert payload["end"] == {"date": "2026-10-28"}
    assert "project_review.txt" in payload["description"]
    assert "Review project milestones." in payload["description"]


def test_build_google_event_without_end_date_is_one_day():
    event = SimpleNamespace(
        id=2,
        title="Exam",
        event_type="exam",
        event_date=date(2026, 10, 30),
        event_end_date=None,
        source_excerpt="Midterm examination.",
    )

    payload = service._build_google_event(event, "exam.txt")

    assert payload["start"] == {"date": "2026-10-30"}
    assert payload["end"] == {"date": "2026-10-31"}


def test_build_google_event_rejects_missing_start_date():
    event = SimpleNamespace(
        id=3,
        title="Undated Event",
        event_type="general",
        event_date=None,
        event_end_date=None,
        source_excerpt="No date available.",
    )

    with pytest.raises(ValueError, match="dated event"):
        service._build_google_event(event, "undated.txt")


def test_build_google_event_rejects_end_before_start():
    event = SimpleNamespace(
        id=4,
        title="Invalid Event",
        event_type="general",
        event_date=date(2026, 10, 27),
        event_end_date=date(2026, 10, 25),
        source_excerpt="Invalid date range.",
    )

    with pytest.raises(ValueError, match="precedes"):
        service._build_google_event(event, "invalid.txt")


def test_google_oauth_configuration_is_optional(monkeypatch):
    monkeypatch.setattr(service, "GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8501",
    )
    monkeypatch.setattr(
        service,
        "MEMORYNEST_TOKEN_ENCRYPTION_KEY",
        "",
    )

    assert service.google_oauth_configured() is False


def test_signed_oauth_state_is_bound_to_user(monkeypatch):
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_ID",
        "test-client-id",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "test-client-secret",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8501",
    )
    monkeypatch.setattr(
        service,
        "MEMORYNEST_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )

    state = service.create_google_oauth_state(42)

    assert service.verify_google_oauth_state(state, 42) is True
    assert service.verify_google_oauth_state(state, 43) is False


def test_signed_oauth_state_rejects_tampering(monkeypatch):
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_ID",
        "test-client-id",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "test-client-secret",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8501",
    )
    monkeypatch.setattr(
        service,
        "MEMORYNEST_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )

    state = service.create_google_oauth_state(42)
    encoded, signature = state.rsplit(".", 1)
    changed_signature = (
        ("0" if signature[0] != "0" else "1")
        + signature[1:]
    )
    tampered_state = f"{encoded}.{changed_signature}"

    assert service.verify_google_oauth_state(tampered_state, 42) is False


@pytest.fixture
def calendar_db_session(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base
    from app.db.google_calendar_model import GoogleCalendarConnection
    from app.models.user import User

    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_ID",
        "test-client-id",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "test-client-secret",
    )
    monkeypatch.setattr(
        service,
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8501",
    )
    monkeypatch.setattr(
        service,
        "MEMORYNEST_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'calendar-refresh.sqlite').as_posix()}",
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
        user = User(
            username="calendar_refresh_user",
            email="calendar-refresh@example.com",
            password_hash="test-hash",
        )
        db.add(user)
        db.flush()

        yield db, user

    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _add_calendar_connection(db, user, credentials):
    from app.db.google_calendar_model import GoogleCalendarConnection

    connection = GoogleCalendarConnection(
        user_id=user.id,
        connected_email="calendar-refresh@gmail.com",
        encrypted_credentials=service._encrypt_credentials(credentials),
        reauthorization_required=False,
    )
    db.add(connection)
    db.commit()
    return connection


def _expired_calendar_credentials():
    from datetime import UTC, datetime, timedelta

    from google.oauth2.credentials import Credentials

    return Credentials(
        token="expired-calendar-test-token",
        refresh_token="test-calendar-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client-id",
        client_secret="test-client-secret",
        scopes=service.GOOGLE_SCOPES,
        expiry=(
            datetime.now(UTC).replace(tzinfo=None)
            - timedelta(hours=1)
        ),
    )


def test_revoked_calendar_refresh_token_requires_reauthorization(
    calendar_db_session, monkeypatch
):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    db, user = calendar_db_session
    connection = _add_calendar_connection(
        db, user, _expired_calendar_credentials()
    )

    def fail_refresh(self, request):
        raise RefreshError(
            "invalid_grant: Token has been expired or revoked."
        )

    monkeypatch.setattr(Credentials, "refresh", fail_refresh)

    with pytest.raises(
        service.GoogleReauthorizationRequired,
        match="Reconnect Google Calendar",
    ):
        service._get_google_credentials(db, connection)

    db.refresh(connection)
    assert connection.reauthorization_required is True


def test_temporary_calendar_refresh_error_does_not_require_reauthorization(
    calendar_db_session, monkeypatch
):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    db, user = calendar_db_session
    connection = _add_calendar_connection(
        db, user, _expired_calendar_credentials()
    )

    def fail_refresh(self, request):
        raise RefreshError("temporarily unavailable")

    monkeypatch.setattr(Credentials, "refresh", fail_refresh)

    with pytest.raises(
        RefreshError,
        match="temporarily unavailable",
    ):
        service._get_google_credentials(db, connection)

    db.refresh(connection)
    assert connection.reauthorization_required is False


def test_calendar_without_refresh_token_requires_reauthorization(
    calendar_db_session, monkeypatch
):
    from types import SimpleNamespace

    db, user = calendar_db_session
    connection = _add_calendar_connection(
        db, user, _expired_calendar_credentials()
    )

    credentials = SimpleNamespace(
        expired=True,
        refresh_token=None,
        valid=False,
    )
    monkeypatch.setattr(
        service,
        "_decrypt_credentials",
        lambda encrypted: credentials,
    )

    with pytest.raises(
        service.GoogleReauthorizationRequired,
        match="Reconnect Google Calendar",
    ):
        service._get_google_credentials(db, connection)

    db.refresh(connection)
    assert connection.reauthorization_required is True
