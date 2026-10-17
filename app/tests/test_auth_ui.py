
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ui import auth_ui


def test_cookie_secure_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MEMORYNEST_COOKIE_SECURE", raising=False)

    assert auth_ui.cookie_secure_enabled() is False


def test_cookie_secure_accepts_true_values(monkeypatch):
    for value in ("true", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("MEMORYNEST_COOKIE_SECURE", value)
        assert auth_ui.cookie_secure_enabled() is True


def test_cookie_secure_rejects_false_values(monkeypatch):
    for value in ("false", "0", "no", "off", ""):
        monkeypatch.setenv("MEMORYNEST_COOKIE_SECURE", value)
        assert auth_ui.cookie_secure_enabled() is False


def test_login_creates_session_and_sets_cookie(monkeypatch):
    user = SimpleNamespace(id=7, username="testuser")
    token = "test-session-token"
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    db = MagicMock()
    cookies = MagicMock()

    monkeypatch.setenv("MEMORYNEST_COOKIE_SECURE", "true")

    with (
        patch.object(auth_ui, "SessionLocal", return_value=db),
        patch.object(
            auth_ui,
            "authenticate_user",
            return_value=user,
        ) as authenticate,
        patch.object(
            auth_ui,
            "create_user_session",
            return_value=(token, expires_at),
        ) as create_session,
        patch.object(auth_ui.st, "text_input", side_effect=[
            " testuser ",
            "password123",
        ]),
        patch.object(auth_ui.st, "button", return_value=True),
        patch.object(auth_ui.st, "markdown"),
        patch.object(auth_ui.st, "caption"),
        patch.object(auth_ui.st, "divider"),
        patch.object(auth_ui.st, "subheader"),
        patch.object(auth_ui.st, "write"),
        patch.object(auth_ui.st, "success"),
        patch.object(auth_ui.st, "error") as show_error,
        patch.object(auth_ui.st, "session_state", {}),
    ):
        auth_ui.login_page(cookies)

    authenticate.assert_called_once_with(
        db=db,
        username_or_email="testuser",
        password="password123",
    )
    create_session.assert_called_once_with(db, user.id)

    cookies.set.assert_called_once_with(
        cookie=auth_ui.SESSION_COOKIE_NAME,
        val=token,
        key="memorynest_session_write",
        expires_at=expires_at,
        path="/",
        secure=True,
        same_site="strict",
    )

    db.close.assert_called_once()
    show_error.assert_not_called()


def test_login_rejects_invalid_credentials(monkeypatch):
    db = MagicMock()
    cookies = MagicMock()

    with (
        patch.object(auth_ui, "SessionLocal", return_value=db),
        patch.object(
            auth_ui,
            "authenticate_user",
            return_value=None,
        ),
        patch.object(auth_ui.st, "text_input", side_effect=[
            "unknown-user",
            "wrong-password",
        ]),
        patch.object(auth_ui.st, "button", return_value=True),
        patch.object(auth_ui.st, "markdown"),
        patch.object(auth_ui.st, "caption"),
        patch.object(auth_ui.st, "divider"),
        patch.object(auth_ui.st, "subheader"),
        patch.object(auth_ui.st, "write"),
        patch.object(auth_ui.st, "error") as show_error,
        patch.object(auth_ui.st, "session_state", {}),
    ):
        auth_ui.login_page(cookies)

    show_error.assert_called_once_with(
        "Invalid username/email or password."
    )
    cookies.set.assert_not_called()
    db.close.assert_called_once()


def test_login_does_nothing_when_button_not_clicked():
    with (
        patch.object(auth_ui.st, "text_input", side_effect=[
            "testuser",
            "password123",
        ]),
        patch.object(auth_ui.st, "button", return_value=False),
        patch.object(auth_ui.st, "markdown"),
        patch.object(auth_ui.st, "caption"),
        patch.object(auth_ui.st, "divider"),
        patch.object(auth_ui.st, "subheader"),
        patch.object(auth_ui.st, "write"),
        patch.object(auth_ui, "SessionLocal") as session_factory,
    ):
        auth_ui.login_page(MagicMock())

    session_factory.assert_not_called()
