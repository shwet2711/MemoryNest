
import logging

import streamlit as st

from app.db.session import SessionLocal
from app.services.google_calendar_service import (
    GoogleReauthorizationRequired,
    build_google_authorization_url,
    complete_google_oauth,
    create_google_oauth_state,
    disconnect_google_calendar,
    get_google_connection,
    google_oauth_configured,
    sync_confirmed_events,
    verify_google_oauth_state,
)

logger = logging.getLogger(__name__)

OAUTH_STATE_KEY = "google_oauth_state"
OAUTH_USER_KEY = "google_oauth_user_id"
OAUTH_URL_KEY = "google_oauth_url"
REAUTH_NOTICE_KEY = "google_calendar_reauthorization_notice"


def _clean_oauth_query_params() -> None:
    """Remove temporary OAuth values from the browser URL."""
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


def handle_google_oauth_callback() -> bool:
    """Handle Google's redirect before normal navigation is rendered."""
    code = st.query_params.get("code")
    error = st.query_params.get("error")

    if not code and not error:
        return False

    returned_state = st.query_params.get("state")
    current_user_id = st.session_state.get("user_id")

    try:
        if error:
            st.session_state["google_oauth_error"] = (
                "Google authorization was cancelled or denied."
            )

        elif (
            current_user_id is None
            or not returned_state
            or not verify_google_oauth_state(
                str(returned_state),
                int(current_user_id),
            )
        ):
            st.session_state["google_oauth_error"] = (
                "Google authorization could not be verified. "
                "Please try connecting again."
            )

        else:
            db = SessionLocal()
            try:
                email = complete_google_oauth(
                    db,
                    int(current_user_id),
                    str(code),
                    str(returned_state),
                )
                st.session_state["google_oauth_success"] = email
                st.session_state.pop(REAUTH_NOTICE_KEY, None)
            finally:
                db.close()

    except Exception:
        logger.exception("Google OAuth callback failed")
        st.session_state["google_oauth_error"] = (
            "Google Calendar could not be connected. "
            "Check your configuration and application logs."
        )

    finally:
        st.session_state.pop(OAUTH_STATE_KEY, None)
        st.session_state.pop(OAUTH_USER_KEY, None)
        st.session_state.pop(OAUTH_URL_KEY, None)

    st.query_params["page"] = "Calendar"
    _clean_oauth_query_params()
    st.rerun()

    return True


def _start_google_authorization(user_id: int) -> None:
    """Prepare a Google authorization URL for connect or reconnect."""
    try:
        state = create_google_oauth_state(user_id)
        authorization_url = build_google_authorization_url(state)
    except Exception:
        logger.exception(
            "Could not start Google Calendar authorization for user %s",
            user_id,
        )
        st.error(
            "Could not start Google authorization. "
            "Check your OAuth configuration."
        )
        return

    st.session_state[OAUTH_STATE_KEY] = state
    st.session_state[OAUTH_USER_KEY] = user_id
    st.session_state[OAUTH_URL_KEY] = authorization_url
    st.rerun()


def _render_authorization_link(user_id: int) -> None:
    """Show the pending authorization link only to its initiating user."""
    authorization_url = st.session_state.get(OAUTH_URL_KEY)
    authorization_user = st.session_state.get(OAUTH_USER_KEY)

    if (
        authorization_url
        and authorization_user is not None
        and int(authorization_user) == user_id
    ):
        st.link_button(
            "Continue to Google",
            authorization_url,
            use_container_width=True,
        )
        st.caption(
            "After granting permission, Google will return you "
            "to MemoryNest."
        )


def google_calendar_page() -> None:
    """Render Google Calendar controls inside the existing Calendar page."""
    user_id = st.session_state.get("user_id")

    if not user_id:
        st.warning("Please sign in to manage Google Calendar.")
        return

    user_id = int(user_id)

    st.divider()
    st.subheader("Google Calendar sync")
    st.caption(
        "Connect your Google account to synchronize confirmed "
        "MemoryNest events with your primary Google Calendar."
    )

    success_email = st.session_state.pop(
        "google_oauth_success",
        None,
    )
    if success_email:
        st.success(f"Google Calendar connected: {success_email}")

    oauth_error = st.session_state.pop(
        "google_oauth_error",
        None,
    )
    if oauth_error:
        st.error(oauth_error)

    reauthorization_notice = st.session_state.pop(
        REAUTH_NOTICE_KEY,
        False,
    )
    if reauthorization_notice:
        st.warning(
            "Google Calendar authorization has expired or been revoked. "
            "Reconnect Google Calendar to resume syncing."
        )

    if not google_oauth_configured():
        st.info(
            "Google Calendar is not configured. Add "
            "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, "
            "GOOGLE_OAUTH_REDIRECT_URI, and "
            "MEMORYNEST_TOKEN_ENCRYPTION_KEY to your local .env file, "
            "then restart MemoryNest."
        )
        return

    db = SessionLocal()

    try:
        connection = get_google_connection(db, user_id)
        connected_email = (
            connection.connected_email if connection else None
        )
        reauthorization_required = bool(
            connection and connection.reauthorization_required
        )
    except Exception:
        logger.exception(
            "Could not load Google connection for user %s",
            user_id,
        )
        st.error("Could not load your Google Calendar connection.")
        return
    finally:
        db.close()

    if connected_email:
        st.success(f"Connected to Google as {connected_email}")

        if reauthorization_required:
            st.warning(
                "Google Calendar authorization needs to be renewed. "
                "Reconnect your Google account to continue syncing."
            )

            if st.button(
                "Reconnect Google Calendar",
                type="primary",
                use_container_width=True,
                key="google_calendar_reconnect",
            ):
                _start_google_authorization(user_id)

        st.write(
            "Only confirmed events with valid dates are eligible "
            "for synchronization."
        )

        sync_clicked = st.button(
            "Sync Confirmed Events",
            type="primary",
            use_container_width=True,
            key="google_calendar_sync",
            disabled=reauthorization_required,
        )

        disconnect_clicked = st.button(
            "Disconnect Google Calendar",
            use_container_width=True,
            key="google_calendar_disconnect",
        )

        if sync_clicked:
            sync_db = SessionLocal()

            try:
                counts = sync_confirmed_events(sync_db, user_id)
            except GoogleReauthorizationRequired:
                logger.warning(
                    "Google Calendar reauthorization required for user %s",
                    user_id,
                )
                st.session_state[REAUTH_NOTICE_KEY] = True
                st.rerun()
            except Exception:
                logger.exception(
                    "Google Calendar sync failed for user %s",
                    user_id,
                )
                st.error(
                    "Synchronization could not be completed. "
                    "Check the application logs."
                )
            else:
                st.success(
                    f"Synchronization finished. "
                    f"Created: {counts['created']}, "
                    f"updated: {counts['updated']}, "
                    f"failed: {counts['failed']}."
                )

                if counts["failed"]:
                    st.warning(
                        "Some events failed to synchronize. "
                        "Review the application logs and retry."
                    )

                if (
                    counts["created"] == 0
                    and counts["updated"] == 0
                    and counts["failed"] == 0
                ):
                    st.info(
                        "No confirmed events with valid dates "
                        "were available to synchronize."
                    )
            finally:
                sync_db.close()

        if disconnect_clicked:
            disconnect_db = SessionLocal()

            try:
                disconnect_google_calendar(disconnect_db, user_id)
            except Exception:
                logger.exception(
                    "Could not disconnect Google Calendar for user %s",
                    user_id,
                )
                st.error("Google Calendar could not be disconnected.")
            else:
                st.session_state.pop(OAUTH_STATE_KEY, None)
                st.session_state.pop(OAUTH_USER_KEY, None)
                st.session_state.pop(OAUTH_URL_KEY, None)
                st.success("Google Calendar has been disconnected.")
                st.rerun()
            finally:
                disconnect_db.close()

        st.caption(
            "Disconnecting removes the stored credentials from "
            "MemoryNest. It does not delete events already in "
            "Google Calendar."
        )

    else:
        st.info("Google Calendar is not connected.")

        if st.button(
            "Connect Google Calendar",
            type="primary",
            use_container_width=True,
            key="google_calendar_connect",
        ):
            _start_google_authorization(user_id)

    _render_authorization_link(user_id)
