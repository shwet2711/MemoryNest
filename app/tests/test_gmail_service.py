
import base64
from email import message_from_bytes
from email.policy import default

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.gmail_service as service
from app.db.database import Base
from app.db.gmail_connection_model import GmailConnection
from app.models.user import User


@pytest.fixture
def configured_gmail(monkeypatch):
    monkeypatch.setattr(service, "GOOGLE_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setattr(
        service, "GOOGLE_OAUTH_CLIENT_SECRET", "test-secret"
    )
    monkeypatch.setattr(
        service, "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501"
    )
    monkeypatch.setattr(
        service,
        "MEMORYNEST_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gmail.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_gmail_state_is_bound_to_user(configured_gmail):
    state, _ = service.build_gmail_authorization_url(42)

    assert service.verify_gmail_oauth_state(state, 42)
    assert not service.verify_gmail_oauth_state(state, 43)
    assert service.is_gmail_oauth_state(state)


def test_gmail_state_rejects_tampering(configured_gmail):
    state, _ = service.build_gmail_authorization_url(42)
    encoded, signature = state.rsplit(".", 1)
    altered = ("0" if signature[0] != "0" else "1") + signature[1:]

    assert not service.verify_gmail_oauth_state(
        f"{encoded}.{altered}", 42
    )


def test_calendar_state_is_not_a_gmail_state():
    assert not service.is_gmail_oauth_state("calendar-state.invalid")


def test_gmail_connection_is_scoped_to_user(db_session):
    first = User(
        username="gmail_user_one",
        email="gmail-one@example.com",
        password_hash="test-hash",
    )
    second = User(
        username="gmail_user_two",
        email="gmail-two@example.com",
        password_hash="test-hash",
    )
    db_session.add_all([first, second])
    db_session.flush()

    first_connection = GmailConnection(
        user_id=first.id,
        connected_email="first@gmail.com",
        encrypted_credentials="test-encrypted-value",
    )
    db_session.add(first_connection)
    db_session.commit()

    assert service.get_gmail_connection(db_session, first.id).connected_email \
        == "first@gmail.com"
    assert service.get_gmail_connection(db_session, second.id) is None


def test_send_email_uses_gmail_api_and_encodes_message(
    configured_gmail, db_session, monkeypatch
):
    from google.oauth2.credentials import Credentials

    user = User(
        username="gmail_sender_user",
        email="gmail-sender@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    credentials = Credentials(
        token="test-access-token",
        refresh_token="test-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client",
        client_secret="test-secret",
        scopes=service.GMAIL_SCOPES,
    )
    db_session.add(
        GmailConnection(
            user_id=user.id,
            connected_email="sender@gmail.com",
            encrypted_credentials=service._encrypt_credentials(credentials),
        )
    )
    db_session.commit()

    captured = {}

    class FakeSendRequest:
        def execute(self):
            return {"id": "mock-message-id"}

    class FakeMessages:
        def send(self, *, userId, body):
            captured["userId"] = userId
            captured["raw"] = body["raw"]
            return FakeSendRequest()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    monkeypatch.setattr(
        service,
        "build",
        lambda *args, **kwargs: FakeService(),
    )

    # Keep this unit test offline; do not contact Google's OAuth server.
    from datetime import UTC, datetime, timedelta

    def fake_refresh(self, request):
        self.token = "refreshed-test-access-token"
        self.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)

    service.send_gmail_api_email(
        db_session,
        user.id,
        "recipient@example.com",
        "MemoryNest test reminder",
        "Your confirmed event is tomorrow.",
    )

    assert captured["userId"] == "me"

    raw = captured["raw"]
    decoded = base64.urlsafe_b64decode(
        raw + "=" * (-len(raw) % 4)
    )
    message = message_from_bytes(decoded, policy=default)

    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "recipient@example.com"
    assert message["Subject"] == "MemoryNest test reminder"
    assert "confirmed event is tomorrow" in message.get_content()


def test_missing_gmail_connection_raises_clear_error(
    configured_gmail, db_session
):
    with pytest.raises(
        service.GmailConfigurationError,
        match="Connect Gmail",
    ):
        service.send_gmail_api_email(
            db_session,
            999,
            "recipient@example.com",
            "Test",
            "Body",
        )



def _add_gmail_connection_with_credentials(db_session, credentials):
    user = User(
        username="gmail_refresh_test_user",
        email="gmail-refresh-test@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    connection = GmailConnection(
        user_id=user.id,
        connected_email="refresh-test@gmail.com",
        encrypted_credentials=service._encrypt_credentials(credentials),
        reauthorization_required=False,
    )
    db_session.add(connection)
    db_session.commit()

    return user, connection



def _expired_gmail_credentials(refresh_token="test-refresh-token"):
    from datetime import UTC, datetime, timedelta
    from google.oauth2.credentials import Credentials

    credentials = Credentials(
        token="expired-test-token",
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client",
        client_secret="test-secret",
        scopes=service.GMAIL_SCOPES,
        expiry=(
            datetime.now(UTC).replace(tzinfo=None)
            - timedelta(hours=1)
        ),
    )

    return credentials


def test_revoked_gmail_refresh_token_requires_reauthorization(
    configured_gmail, db_session, monkeypatch
):
    from google.oauth2.credentials import Credentials

    user, connection = _add_gmail_connection_with_credentials(
        db_session,
        _expired_gmail_credentials(),
    )

    def fail_refresh(self, request):
        raise service.RefreshError(
            "invalid_grant: Token has been expired or revoked."
        )

    monkeypatch.setattr(Credentials, "refresh", fail_refresh)

    with pytest.raises(
        service.GmailReauthorizationRequired,
        match="Reconnect Gmail",
    ):
        service._get_valid_credentials(db_session, user.id)

    db_session.refresh(connection)
    assert connection.reauthorization_required is True


def test_temporary_gmail_refresh_error_does_not_require_reauthorization(
    configured_gmail, db_session, monkeypatch
):
    from google.oauth2.credentials import Credentials

    user, connection = _add_gmail_connection_with_credentials(
        db_session,
        _expired_gmail_credentials(),
    )

    def fail_refresh(self, request):
        raise service.RefreshError("temporarily unavailable")

    monkeypatch.setattr(Credentials, "refresh", fail_refresh)

    with pytest.raises(
        service.RefreshError,
        match="temporarily unavailable",
    ):
        service._get_valid_credentials(db_session, user.id)

    db_session.refresh(connection)
    assert connection.reauthorization_required is False


def test_gmail_without_refresh_token_requires_reauthorization(
    configured_gmail, db_session, monkeypatch
):
    from types import SimpleNamespace

    user = User(
        username="gmail_no_refresh_user",
        email="gmail-no-refresh@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    connection = GmailConnection(
        user_id=user.id,
        connected_email="no-refresh@gmail.com",
        encrypted_credentials="test-encrypted-value",
        reauthorization_required=False,
    )
    db_session.add(connection)
    db_session.commit()

    # The service only needs these credential attributes for this branch.
    credentials = SimpleNamespace(
        expired=True,
        refresh_token=None,
        valid=False,
    )
    monkeypatch.setattr(
        service,
        "_decrypt_credentials",
        lambda value: credentials,
    )

    with pytest.raises(
        service.GmailReauthorizationRequired,
        match="Reconnect Gmail",
    ):
        service._get_valid_credentials(db_session, user.id)

    db_session.refresh(connection)
    assert connection.reauthorization_required is True
