
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.core.config import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    MEMORYNEST_TOKEN_ENCRYPTION_KEY,
)
from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.db.google_calendar_model import (
    GoogleCalendarConnection,
    GoogleCalendarSync,
)

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleReauthorizationRequired(ValueError):
    """Google Calendar credentials require the user to authorize again."""


def _is_definitive_google_refresh_failure(
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


def google_oauth_configured() -> bool:
    """Return whether all required Google configuration is present."""
    return bool(
        GOOGLE_OAUTH_CLIENT_ID
        and GOOGLE_OAUTH_CLIENT_SECRET
        and GOOGLE_OAUTH_REDIRECT_URI
        and MEMORYNEST_TOKEN_ENCRYPTION_KEY
    )


def _validate_google_configuration() -> None:
    if not GOOGLE_OAUTH_CLIENT_ID:
        raise ValueError("Google OAuth client ID is not configured.")

    if not GOOGLE_OAUTH_CLIENT_SECRET:
        raise ValueError("Google OAuth client secret is not configured.")

    if not GOOGLE_OAUTH_REDIRECT_URI:
        raise ValueError("Google OAuth redirect URI is not configured.")

    if not MEMORYNEST_TOKEN_ENCRYPTION_KEY:
        raise ValueError(
            "The MemoryNest token encryption key is not configured."
        )


def _fernet() -> Fernet:
    """Create the authenticated encryption helper."""
    _validate_google_configuration()

    try:
        return Fernet(
            MEMORYNEST_TOKEN_ENCRYPTION_KEY.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY is invalid. "
            "Generate a Fernet key and keep it stable."
        ) from exc


def _encrypt_credentials(credentials: Credentials) -> str:
    raw = credentials.to_json().encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def _decrypt_credentials(encrypted: str) -> Credentials:
    try:
        raw = _fernet().decrypt(
            encrypted.encode("utf-8")
        ).decode("utf-8")
        data = json.loads(raw)
        return Credentials.from_authorized_user_info(
            data,
            scopes=GOOGLE_SCOPES,
        )
    except (
        InvalidToken,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "Stored Google credentials could not be decrypted. "
            "Check the configured encryption key."
        ) from exc


def _client_config() -> dict:
    _validate_google_configuration()

    return {
        "web": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def create_google_oauth_state(
    user_id: int,
    code_verifier: str | None = None,
) -> str:
    """Create signed OAuth state with an optional encrypted PKCE verifier."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A valid MemoryNest user ID is required.")

    _validate_google_configuration()

    nonce = secrets.token_urlsafe(32)
    payload_parts = [str(user_id), nonce]

    if code_verifier is not None:
        encrypted_verifier = _fernet().encrypt(
            code_verifier.encode("utf-8")
        ).decode("ascii")
        payload_parts.append(encrypted_verifier)

    payload = ":".join(payload_parts).encode("utf-8")
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


def _decode_google_oauth_state(
    state: str,
) -> tuple[int, str | None]:
    """Verify signed state and recover its encrypted PKCE verifier."""
    if not state or "." not in state:
        raise ValueError("Google OAuth state is missing or invalid.")

    _validate_google_configuration()

    encoded, supplied_signature = state.rsplit(".", 1)

    expected_signature = hmac.new(
        MEMORYNEST_TOKEN_ENCRYPTION_KEY.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        supplied_signature,
        expected_signature,
    ):
        raise ValueError("Google OAuth state signature is invalid.")

    padded = encoded + "=" * (-len(encoded) % 4)
    payload = base64.urlsafe_b64decode(
        padded
    ).decode("utf-8")
    parts = payload.split(":", 2)

    if len(parts) < 2:
        raise ValueError("Google OAuth state payload is invalid.")

    state_user_id = int(parts[0])
    nonce = parts[1]

    if state_user_id <= 0 or not nonce:
        raise ValueError("Google OAuth state payload is invalid.")

    verifier = None

    if len(parts) == 3:
        verifier = _fernet().decrypt(
            parts[2].encode("ascii")
        ).decode("utf-8")

        if not verifier:
            raise ValueError("The PKCE verifier is empty.")

    return state_user_id, verifier


def verify_google_oauth_state(
    state: str,
    user_id: int,
) -> bool:
    """Verify the signed state belongs to the current MemoryNest user."""
    try:
        state_user_id, _ = _decode_google_oauth_state(state)
        return state_user_id == user_id
    except (
        ValueError,
        TypeError,
        UnicodeError,
        InvalidToken,
    ):
        return False


def build_google_authorization_url(state: str) -> str:
    """Build a PKCE-protected Google authorization URL."""
    state_user_id, _ = _decode_google_oauth_state(state)

    verifier = secrets.token_urlsafe(64)
    protected_state = create_google_oauth_state(
        state_user_id,
        code_verifier=verifier,
    )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_SCOPES,
        state=protected_state,
        redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
        code_verifier=verifier,
        autogenerate_code_verifier=False,
    )

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge_method="S256",
    )

    return authorization_url


def complete_google_oauth(
    db: Session,
    user_id: int,
    code: str,
    state: str,
) -> str:
    """Exchange the authorization code and save encrypted credentials."""
    if not code.strip() or not state.strip():
        raise ValueError("The Google authorization response is incomplete.")

    state_user_id, verifier = _decode_google_oauth_state(state)

    if state_user_id != user_id:
        raise ValueError("Google OAuth state verification failed.")

    if not verifier:
        raise ValueError(
            "The Google OAuth state does not contain a PKCE verifier. "
            "Please start a new authorization attempt."
        )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
        code_verifier=verifier,
        autogenerate_code_verifier=False,
    )

    flow.fetch_token(code=code)
    credentials = flow.credentials

    oauth_service = build(
        "oauth2",
        "v2",
        credentials=credentials,
        cache_discovery=False,
    )
    user_info = oauth_service.userinfo().get().execute()
    email = str(user_info.get("email", "")).strip()

    if not email:
        raise ValueError(
            "Google did not return an email address for this account."
        )

    encrypted = _encrypt_credentials(credentials)
    connection = get_google_connection(db, user_id)

    try:
        if connection is None:
            connection = GoogleCalendarConnection(
                user_id=user_id,
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
    except Exception:
        db.rollback()
        raise

    return email


def get_google_connection(
    db: Session,
    user_id: int,
) -> GoogleCalendarConnection | None:
    """Get the Google connection belonging to this MemoryNest user."""
    return (
        db.query(GoogleCalendarConnection)
        .filter(GoogleCalendarConnection.user_id == user_id)
        .first()
    )


def disconnect_google_calendar(
    db: Session,
    user_id: int,
) -> bool:
    """Remove stored credentials without deleting Google Calendar events."""
    connection = get_google_connection(db, user_id)

    if connection is None:
        return False

    try:
        db.delete(connection)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def _get_google_credentials(
    db: Session,
    connection: GoogleCalendarConnection,
) -> Credentials:
    credentials = _decrypt_credentials(
        connection.encrypted_credentials
    )

    if credentials.expired:
        if not credentials.refresh_token:
            connection.reauthorization_required = True
            db.commit()

            raise GoogleReauthorizationRequired(
                "Google Calendar authorization has expired. "
                "Reconnect Google Calendar in MemoryNest."
            )

        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            if _is_definitive_google_refresh_failure(exc):
                connection.reauthorization_required = True
                db.commit()

                # Never expose Google's raw token response to the user.
                raise GoogleReauthorizationRequired(
                    "Google Calendar authorization has expired or "
                    "been revoked. Reconnect Google Calendar in MemoryNest."
                ) from None

            # Temporary or unclassified failures should remain retryable.
            raise

        connection.encrypted_credentials = _encrypt_credentials(
            credentials
        )

    if not credentials.valid:
        connection.reauthorization_required = True
        db.commit()

        raise GoogleReauthorizationRequired(
            "Google Calendar credentials are no longer valid. "
            "Reconnect Google Calendar in MemoryNest."
        )

    connection.reauthorization_required = False

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return credentials


def _stable_google_event_id(
    user_id: int,
    event_id: int,
) -> str:
    """Generate a stable Google-compatible ID to help prevent duplicates."""
    value = f"memorynest-user-{user_id}-event-{event_id}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _http_status(exc: HttpError) -> int | None:
    """Read the HTTP status from a Google API error."""
    return getattr(getattr(exc, "resp", None), "status", None)


def _build_google_event(
    event: DetectedEvent,
    filename: str,
) -> dict:
    """Build a Google all-day event from a confirmed MemoryNest event."""
    if event.event_date is None:
        raise ValueError("A dated event is required.")

    inclusive_end = event.event_end_date or event.event_date

    if inclusive_end < event.event_date:
        raise ValueError("The event end date precedes its start date.")

    exclusive_end = inclusive_end + timedelta(days=1)

    description = (
        f"Source document: {filename}\n\n"
        f"MemoryNest event type: {event.event_type}\n\n"
        f"Source evidence:\n{event.source_excerpt}"
    )

    return {
        "summary": event.title,
        "description": description[:8000],
        "start": {"date": event.event_date.isoformat()},
        "end": {"date": exclusive_end.isoformat()},
    }


def sync_confirmed_events(
    db: Session,
    user_id: int,
) -> dict[str, int]:
    """Sync confirmed, dated events individually to Google Calendar."""
    connection = get_google_connection(db, user_id)

    if connection is None:
        raise ValueError(
            "Connect Google Calendar before synchronizing."
        )

    credentials = _get_google_credentials(db, connection)

    google_service = build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    rows = (
        db.query(DetectedEvent, Document.original_filename)
        .join(
            Document,
            DetectedEvent.document_id == Document.id,
        )
        .filter(
            DetectedEvent.user_id == user_id,
            Document.user_id == user_id,
            DetectedEvent.status == "confirmed",
            DetectedEvent.event_date.is_not(None),
        )
        .order_by(
            DetectedEvent.event_date,
            DetectedEvent.id,
        )
        .all()
    )

    result = {
        "created": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }

    for event, filename in rows:
        try:
            mapping = (
                db.query(GoogleCalendarSync)
                .filter(
                    GoogleCalendarSync.user_id == user_id,
                    GoogleCalendarSync.event_id == event.id,
                )
                .first()
            )

            body = _build_google_event(event, filename)
            calendar_id = (
                mapping.calendar_id if mapping else "primary"
            )

            if mapping is not None:
                try:
                    google_service.events().update(
                        calendarId=calendar_id,
                        eventId=mapping.google_event_id,
                        body=body,
                    ).execute()
                    result["updated"] += 1

                except HttpError as exc:
                    if _http_status(exc) != 404:
                        raise

                    # The mapped Google event no longer exists.
                    mapping = None

            if mapping is None:
                google_id = _stable_google_event_id(
                    user_id,
                    event.id,
                )
                body["id"] = google_id

                try:
                    created = google_service.events().insert(
                        calendarId="primary",
                        body=body,
                    ).execute()

                except HttpError as exc:
                    # Recover if Google created the event previously,
                    # but MemoryNest did not save its mapping.
                    if _http_status(exc) != 409:
                        raise

                    created = google_service.events().get(
                        calendarId="primary",
                        eventId=google_id,
                    ).execute()

                    google_service.events().update(
                        calendarId="primary",
                        eventId=google_id,
                        body=body,
                    ).execute()

                google_id = created.get("id", google_id)

                mapping = GoogleCalendarSync(
                    user_id=user_id,
                    event_id=event.id,
                    google_event_id=google_id,
                    calendar_id="primary",
                )
                db.add(mapping)
                result["created"] += 1

            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

        except Exception:
            db.rollback()
            logger.exception(
                "Google Calendar sync failed for user %s, event %s",
                user_id,
                event.id,
            )
            result["failed"] += 1

    return result
