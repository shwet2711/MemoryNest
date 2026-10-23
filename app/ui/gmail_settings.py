
import logging

import streamlit as st

from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth_service import change_user_password
from app.services.gmail_service import (
    build_gmail_authorization_url,
    complete_gmail_oauth,
    disconnect_gmail,
    get_gmail_connection,
    gmail_oauth_configured,
    is_gmail_oauth_state,
    verify_gmail_oauth_state,
)
from app.services.notification_preference_service import (
    get_or_create_notification_preference,
    update_notification_preferences,
)

logger = logging.getLogger(__name__)

STATE_KEY = "gmail_oauth_state"
URL_KEY = "gmail_oauth_url"
USER_KEY = "gmail_oauth_user_id"

REMINDER_OPTIONS = {
    "15 minutes before": 15,
    "1 hour before": 60,
    "6 hours before": 360,
    "24 hours before": 1440,
    "48 hours before": 2880,
    "7 days before": 10080,
}


def _clean_query_params() -> None:
    for key in (
        "code",
        "state",
        "scope",
        "authuser",
        "prompt",
        "error",
        "error_description",
    ):
        if key in st.query_params:
            del st.query_params[key]


def handle_gmail_oauth_callback() -> bool:
    """Handle Gmail callbacks without consuming Calendar OAuth callbacks."""
    code = st.query_params.get("code")
    error = st.query_params.get("error")
    returned_state = st.query_params.get("state")

    if not code and not error:
        return False

    if not is_gmail_oauth_state(
        str(returned_state) if returned_state else None
    ):
        return False

    user_id = st.session_state.get("user_id")

    try:
        if error:
            st.session_state["gmail_oauth_error"] = (
                "Gmail authorization was cancelled or denied."
            )
        elif (
            user_id is None
            or not verify_gmail_oauth_state(
                str(returned_state), int(user_id)
            )
        ):
            st.session_state["gmail_oauth_error"] = (
                "Gmail authorization could not be verified. "
                "Please connect Gmail again."
            )
        else:
            db = SessionLocal()
            try:
                email = complete_gmail_oauth(
                    db,
                    int(user_id),
                    str(code),
                    str(returned_state),
                )
                st.session_state["gmail_oauth_success"] = email
            finally:
                db.close()

    except Exception:
        logger.exception("Gmail OAuth callback failed")
        st.session_state["gmail_oauth_error"] = (
            "Gmail could not be connected. Check the Google OAuth "
            "configuration and application logs."
        )

    finally:
        st.session_state.pop(STATE_KEY, None)
        st.session_state.pop(URL_KEY, None)
        st.session_state.pop(USER_KEY, None)

    st.query_params["page"] = "Settings"
    _clean_query_params()
    st.rerun()
    return True


def _render_reminder_preferences(
    user_id: int,
    registered_email: str,
    connected_email: str | None,
    preference_email_enabled: bool,
    preference_reminder_minutes_before: int,
) -> None:
    """Render and save Gmail event reminder preferences."""
    st.divider()
    st.subheader("Event reminder preferences")

    st.write(
        "Choose whether MemoryNest should email you reminders for "
        "confirmed events. Only events with user-confirmed dates are "
        "eligible."
    )

    addresses_match = bool(
        connected_email
        and connected_email.strip().casefold()
        == registered_email.strip().casefold()
    )

    if addresses_match:
        st.caption(
            "Your connected Gmail account matches your registered "
            "MemoryNest email address."
        )
    elif connected_email:
        st.warning(
            "Your connected Gmail account does not match your "
            "registered MemoryNest email. Email reminders cannot be "
            "enabled until the addresses match."
        )
    else:
        st.info("Connect Gmail before enabling email reminders.")

    current_label = next(
        (
            label
            for label, minutes in REMINDER_OPTIONS.items()
            if minutes == preference_reminder_minutes_before
        ),
        "24 hours before",
    )

    email_enabled = st.checkbox(
        "Enable Gmail event reminders",
        value=preference_email_enabled,
        key="notification_email_enabled",
        help=(
            "Reminders are sent to your registered email address. "
            "Gmail must be connected to that same address."
        ),
    )

    reminder_label = st.selectbox(
        "Send the reminder",
        options=list(REMINDER_OPTIONS.keys()),
        index=list(REMINDER_OPTIONS.keys()).index(current_label),
        key="notification_reminder_lead_time",
    )

    if st.button(
        "Save reminder preferences",
        key="save_notification_preferences",
        use_container_width=True,
    ):
        save_db = SessionLocal()
        try:
            update_notification_preferences(
                save_db,
                user_id,
                email_enabled=email_enabled,
                reminder_minutes_before=REMINDER_OPTIONS[reminder_label],
            )
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception(
                "Could not save notification preferences for user %s",
                user_id,
            )
            st.error(
                "Could not save reminder preferences. Check the application "
                "logs and try again."
            )
        else:
            st.success("Reminder preferences saved.")
        finally:
            save_db.close()

    st.caption(
        "The scheduler uses 9:00 AM Asia/Kolkata as the default event time "
        "when a document contains a date but no specific time. A reminder "
        "whose scheduled time has already passed is not shifted forward."
    )


def _render_password_management(user_id: int) -> None:
    """Render the password-change form."""
    st.divider()
    st.subheader("Password management")
    st.write(
        "Verify your current password before setting a new password. "
        "Your new password must contain at least 12 characters."
    )

    with st.form("change_password_form", clear_on_submit=True):
        current_password = st.text_input(
            "Current password",
            type="password",
            autocomplete="current-password",
        )
        new_password = st.text_input(
            "New password",
            type="password",
            autocomplete="new-password",
        )
        confirm_password = st.text_input(
            "Confirm new password",
            type="password",
            autocomplete="new-password",
        )

        submitted = st.form_submit_button(
            "Change password",
            use_container_width=True,
        )

    if not submitted:
        return

    db = SessionLocal()
    try:
        change_user_password(
            db,
            user_id,
            current_password,
            new_password,
            confirm_password,
        )
    except ValueError as exc:
        st.error(str(exc))
    except Exception:
        logger.exception(
            "Password change failed for user %s",
            user_id,
        )
        st.error("Your password could not be changed. Please try again.")
    else:
        st.success("Your password has been changed successfully.")
    finally:
        db.close()


def _start_gmail_authorization(user_id: int) -> None:
    try:
        state, url = build_gmail_authorization_url(user_id)
    except Exception:
        logger.exception(
            "Could not start Gmail authorization for user %s",
            user_id,
        )
        st.error(
            "Could not start Google authorization. "
            "Check the OAuth configuration."
        )
        return

    st.session_state[STATE_KEY] = state
    st.session_state[URL_KEY] = url
    st.session_state[USER_KEY] = user_id
    st.rerun()


def _render_gmail_connection(
    user_id: int,
    connected_email: str | None,
    reauthorization_required: bool,
    oauth_configured: bool,
) -> None:
    """Render one Gmail connection block without duplicate widget keys."""
    if not oauth_configured:
        st.warning(
            "Google OAuth is not configured. Gmail connection changes "
            "are unavailable until you configure "
            "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, "
            "GOOGLE_OAUTH_REDIRECT_URI, and "
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY in your .env file."
        )

    if connected_email:
        st.success(f"Connected Gmail account: {connected_email}")

        if reauthorization_required:
            st.warning(
                "Gmail authorization has expired or been revoked. "
                "Reconnect Gmail to resume sending reminders."
            )

        st.caption(
            "MemoryNest stores encrypted OAuth credentials. "
            "Disconnecting removes the saved connection from MemoryNest; "
            "it does not necessarily revoke access in your Google account."
        )

        if oauth_configured and reauthorization_required:
            if st.button(
                "Reconnect Gmail",
                type="primary",
                key="gmail_reconnect",
                use_container_width=True,
            ):
                _start_gmail_authorization(user_id)

        if st.button(
            "Disconnect Gmail",
            key="gmail_disconnect",
            use_container_width=True,
        ):
            disconnect_db = SessionLocal()
            try:
                disconnect_gmail(disconnect_db, user_id)
            except Exception:
                logger.exception(
                    "Could not disconnect Gmail for user %s",
                    user_id,
                )
                st.error("Gmail could not be disconnected.")
            else:
                st.session_state.pop(STATE_KEY, None)
                st.session_state.pop(URL_KEY, None)
                st.session_state.pop(USER_KEY, None)
                st.success("Gmail disconnected.")
                st.rerun()
            finally:
                disconnect_db.close()
    else:
        st.info("Gmail is not connected.")

        if oauth_configured and st.button(
            "Connect Gmail",
            type="primary",
            key="gmail_connect",
            use_container_width=True,
        ):
            _start_gmail_authorization(user_id)

    url = st.session_state.get(URL_KEY)
    pending_user = st.session_state.get(USER_KEY)

    if (
        oauth_configured
        and url
        and pending_user is not None
        and int(pending_user) == user_id
    ):
        st.link_button(
            "Continue to Google",
            url,
            use_container_width=True,
        )


def gmail_settings_page() -> None:
    """Render Gmail reminders and password-management settings."""
    st.title("Settings")

    user_id = st.session_state.get("user_id")
    if user_id is None:
        st.warning("Please sign in to manage your settings.")
        return

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        st.error("Your session could not be verified. Please sign in again.")
        return

    success_email = st.session_state.pop("gmail_oauth_success", None)
    if success_email:
        st.success(f"Gmail connected: {success_email}")

    oauth_error = st.session_state.pop("gmail_oauth_error", None)
    if oauth_error:
        st.error(oauth_error)

    oauth_configured = gmail_oauth_configured()

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            st.error("Your MemoryNest account could not be found.")
            return

        registered_email = user.email

        connection = get_gmail_connection(db, user_id)
        connected_email = (
            connection.connected_email if connection else None
        )
        reauthorization_required = bool(
            connection and connection.reauthorization_required
        )

        preference = get_or_create_notification_preference(db, user_id)
        db.commit()
        db.refresh(preference)

        preference_email_enabled = bool(preference.email_enabled)
        preference_reminder_minutes_before = int(
            preference.reminder_minutes_before
        )
    except Exception:
        logger.exception(
            "Could not load Settings for user %s",
            user_id,
        )
        st.error("Could not load your account settings. Please try again.")
        return
    finally:
        db.close()

    st.subheader("Gmail reminder delivery")
    st.write(
        "Connect a Google account so MemoryNest can send event reminders "
        "through the Gmail API."
    )

    _render_gmail_connection(
        user_id,
        connected_email,
        reauthorization_required,
        oauth_configured,
    )

    _render_reminder_preferences(
        user_id,
        registered_email,
        connected_email,
        preference_email_enabled,
        preference_reminder_minutes_before,
    )

    _render_password_management(user_id)
