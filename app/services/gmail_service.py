
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from email.message import EmailMessage

from cryptography.fernet import Fernet, InvalidToken
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.core.config import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    MEMORYNEST_TOKEN_ENCRYPTION_KEY,
)
from app.db.gmail_connection_model import GmailConnection

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
]

_STATE_PREFIX = "gmail"


class GmailConfigurationError(RuntimeError):
    """Gmail OAuth or credential configuration is invalid."""


class GmailReauthorizationRequired(GmailConfigurationError):
    """Gmail credentials require the user to authorize again."""


def _is_definitive_gmail_refresh_failure(
    exc: RefreshError,
) -> bool:
    """Identify refresh failures that clearly require reauthorization."""

    message = str(exc).lower()

    definitive_markers = (
        "invalid_grant",
        "invalid_token",
        "invalid_rapt",
        "token has been expired or revoked",
        "token has been revoked",
        "refresh token has expired",
        "refresh token has been revoked",
    )

    return any(marker in message for marker in definitive_markers)


def gmail_oauth_configured() -> bool:
    return bool(
        GOOGLE_OAUTH_CLIENT_ID
        and GOOGLE_OAUTH_CLIENT_SECRET
        and GOOGLE_OAUTH_REDIRECT_URI
        and MEMORYNEST_TOKEN_ENCRYPTION_KEY
    )


def _fernet() -> Fernet:
    if not MEMORYNEST_TOKEN_ENCRYPTION_KEY:
        raise GmailConfigurationError(
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY is not configured."
        )

    try:
        return Fernet(
            MEMORYNEST_TOKEN_ENCRYPTION_KEY.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        raise GmailConfigurationError(
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY is invalid."
        ) from exc


def _encrypt_credentials(credentials: Credentials) -> str:
    return _fernet().encrypt(
        credentials.to_json().encode("utf-8")
    ).decode("utf-8")


def _decrypt_credentials(encrypted: str) -> Credentials:
    try:
        payload = _fernet().decrypt(encrypted.encode("utf-8"))
        data = json.loads(payload.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise GmailConfigurationError(
            "Stored Gmail credentials could not be decrypted."
        ) from exc

    return Credentials.from_authorized_user_info(
        data,
        scopes=GMAIL_SCOPES,
    )


def _client_config() -> dict:
    if not gmail_oauth_configured():
        raise GmailConfigurationError(
            "Configure the Google OAuth client settings and "
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY in .env."
        )

    return {
        "web": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def _encode_state(
    user_id: int,
    nonce: str,
    verifier: str | None,
) -> str:
    parts = [_STATE_PREFIX, str(user_id), nonce]

    if verifier:
        encrypted_verifier = _fernet().encrypt(
            verifier.encode("utf-8")
        ).decode("utf-8")
        parts.append(encrypted_verifier)

    payload = ":".join(parts).encode("utf-8")
    encoded = (
        base64.urlsafe_b64encode(payload)
        .decode("ascii")
        .rstrip("=")
    )

    signature = hmac.new(
        MEMORYNEST_TOKEN_ENCRYPTION_KEY.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    return f"{encoded}.{signature}"


def _decode_state(state: str) -> tuple[int, str | None]:
    if not MEMORYNEST_TOKEN_ENCRYPTION_KEY:
        raise GmailConfigurationError(
            "The token encryption key is not configured."
        )

    try:
        encoded, signature = state.rsplit(".", 1)

        expected = hmac.new(
            MEMORYNEST_TOKEN_ENCRYPTION_KEY.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid state signature.")

        padded = encoded + "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(
            padded
        ).decode("utf-8")

        parts = payload.split(":", 3)

        if len(parts) < 3 or parts[0] != _STATE_PREFIX:
            raise ValueError("Not a Gmail OAuth state.")

        user_id = int(parts[1])

        if user_id < 1 or not parts[2]:
            raise ValueError("Invalid Gmail OAuth state.")

        verifier = None

        if len(parts) == 4:
            verifier = _fernet().decrypt(
                parts[3].encode("utf-8")
            ).decode("utf-8")

        return user_id, verifier

    except GmailConfigurationError:
        raise
    except Exception as exc:
        raise ValueError("Invalid Gmail OAuth state.") from exc


def is_gmail_oauth_state(state: str | None) -> bool:
    """Identify Gmail callback states without accepting Calendar states."""

    if not state:
        return False

    try:
        _decode_state(state)
        return True
    except Exception:
        # Route invalid Gmail-prefixed states to the Gmail callback too.
        try:
            encoded = state.rsplit(".", 1)[0]
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = base64.urlsafe_b64decode(
                padded
            ).decode("utf-8")

            return payload.startswith("gmail:")

        except Exception:
            return False


def build_gmail_authorization_url(
    user_id: int,
) -> tuple[str, str]:
    """Return (signed state, Google authorization URL)."""

    if int(user_id) < 1:
        raise ValueError("A valid user ID is required.")

    _client_config()

    verifier = secrets.token_urlsafe(64)[:96]

    state = _encode_state(
        int(user_id),
        secrets.token_urlsafe(24),
        verifier,
    )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        state=state,
        redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
        code_verifier=verifier,
    )

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge_method="S256",
    )

    return state, authorization_url


def verify_gmail_oauth_state(
    state: str,
    user_id: int,
) -> bool:
    try:
        state_user_id, verifier = _decode_state(state)

        return (
            state_user_id == int(user_id)
            and bool(verifier)
        )

    except Exception:
        return False


def complete_gmail_oauth(
    db: Session,
    user_id: int,
    code: str,
    state: str,
) -> str:
    """Exchange an OAuth code and save encrypted Gmail credentials."""

    state_user_id, verifier = _decode_state(state)

    if state_user_id != int(user_id) or not verifier:
        raise ValueError(
            "Gmail OAuth state does not match this user."
        )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        state=state,
        redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
        code_verifier=verifier,
    )

    # Permit additional scopes already granted to this OAuth client,
    # while explicitly checking the required Gmail sending permission.
    flow.oauth2session.scope = None
    flow.fetch_token(code=code)

    granted_scope_value = flow.oauth2session.token.get(
        "scope", ""
    )

    if isinstance(granted_scope_value, str):
        granted_scopes = set(granted_scope_value.split())
    else:
        granted_scopes = set(granted_scope_value or [])

    if (
        granted_scopes
        and "https://www.googleapis.com/auth/gmail.send"
        not in granted_scopes
    ):
        raise ValueError(
            "Google did not grant the required Gmail sending permission."
        )

    credentials = flow.credentials

    oauth_service = build(
        "oauth2",
        "v2",
        credentials=credentials,
        cache_discovery=False,
    )

    profile = oauth_service.userinfo().get().execute()

    email = str(
        profile.get("email", "")
    ).strip().lower()

    if not email or not profile.get("verified_email", True):
        raise ValueError(
            "Google did not return a verified Gmail email address."
        )

    encrypted = _encrypt_credentials(credentials)

    connection = (
        db.query(GmailConnection)
        .filter(
            GmailConnection.user_id == int(user_id)
        )
        .first()
    )

    if connection is None:
        connection = GmailConnection(
            user_id=int(user_id),
            connected_email=email,
            encrypted_credentials=encrypted,
            reauthorization_required=False,
        )
        db.add(connection)
    else:
        connection.connected_email = email
        connection.encrypted_credentials = encrypted
        connection.reauthorization_required = False

    db.commit()
    db.refresh(connection)

    return email


def get_gmail_connection(
    db: Session,
    user_id: int,
) -> GmailConnection | None:
    return (
        db.query(GmailConnection)
        .filter(
            GmailConnection.user_id == int(user_id)
        )
        .first()
    )


def disconnect_gmail(
    db: Session,
    user_id: int,
) -> None:
    connection = get_gmail_connection(db, user_id)

    if connection is not None:
        db.delete(connection)
        db.commit()


def _get_valid_credentials(
    db: Session,
    user_id: int,
) -> tuple[GmailConnection, Credentials]:
    connection = get_gmail_connection(db, user_id)

    if connection is None:
        raise GmailConfigurationError(
            "Connect Gmail in MemoryNest Settings before sending reminders."
        )

    credentials = _decrypt_credentials(
        connection.encrypted_credentials
    )

    if credentials.expired:
        if not credentials.refresh_token:
            connection.reauthorization_required = True
            db.commit()

            raise GmailReauthorizationRequired(
                "Gmail authorization has expired. "
                "Reconnect Gmail in MemoryNest Settings."
            )

        try:
            credentials.refresh(Request())

        except RefreshError as exc:
            if _is_definitive_gmail_refresh_failure(exc):
                connection.reauthorization_required = True
                db.commit()

                # Do not expose Google's raw token error response.
                raise GmailReauthorizationRequired(
                    "Gmail authorization has expired or been revoked. "
                    "Reconnect Gmail in MemoryNest Settings."
                ) from None

            # Temporary or unclassified refresh failures remain retryable.
            raise

        connection.encrypted_credentials = (
            _encrypt_credentials(credentials)
        )

    if not credentials.valid:
        connection.reauthorization_required = True
        db.commit()

        raise GmailReauthorizationRequired(
            "Gmail credentials are no longer valid. "
            "Reconnect Gmail in MemoryNest Settings."
        )

    # Clear any stale warning after credentials are valid.
    connection.reauthorization_required = False
    db.commit()

    return connection, credentials


def send_gmail_api_email(
    db: Session,
    user_id: int,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Send a plain-text email using the user's connected Gmail account."""

    if not recipient or "@" not in recipient:
        raise ValueError(
            "A valid recipient email address is required."
        )

    connection, credentials = _get_valid_credentials(
        db,
        user_id,
    )

    message = EmailMessage()
    message["From"] = connection.connected_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    raw = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("ascii")

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    service.users().messages().send(
        userId="me",
        body={"raw": raw.rstrip("=")},
    ).execute()


def send_notification_email_for_user(
    db: Session,
    user_id: int,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Worker entry point for sending reminders through the Gmail API."""

    send_gmail_api_email(
        db,
        user_id,
        recipient,
        subject,
        body,
    )
