import logging

import streamlit as st

from app.db.session import SessionLocal
from app.services.session_service import revoke_user_session
from app.ui.components import render_brand


SESSION_COOKIE_NAME = "memorynest_session"

PAGES = {
    "Overview": "Dashboard",
    "Documents": "Documents",
    "AI Assistant": "AI Chat",
    "Summaries": "Summaries",
    "Events": "Events",
    "Calendar": "Calendar",
    "Memories": "Memories",
    "Search": "Search",
    "Knowledge Graph": "Knowledge Graph",
    "Settings": "Settings",
}


def _sync_page_from_navigation() -> None:
    """Update the URL after the user changes the sidebar selection."""
    selected_label = st.session_state.get("navigation_radio")
    selected_page = PAGES.get(selected_label)

    if selected_page:
        st.query_params["page"] = selected_page


def render_sidebar(cookies) -> str:
    """Render sidebar navigation and handle logout."""

    page_labels = list(PAGES.keys())

    # Read the URL only when initializing the widget state.
    # Do not overwrite the widget state on every rerun.
    if "navigation_radio" not in st.session_state:
        requested_page = st.query_params.get("page", "Dashboard")

        if requested_page not in PAGES.values():
            requested_page = "Dashboard"

        requested_label = next(
            label
            for label, page in PAGES.items()
            if page == requested_page
        )

        st.session_state["navigation_radio"] = requested_label

    with st.sidebar:
        render_brand()
        st.divider()
        st.caption("WORKSPACE")

        selected = st.radio(
            "Navigation",
            options=page_labels,
            label_visibility="collapsed",
            key="navigation_radio",
            on_change=_sync_page_from_navigation,
        )

        selected_page = PAGES[selected]

        # Keep the URL aligned with the selected page.
        if st.query_params.get("page") != selected_page:
            st.query_params["page"] = selected_page

        st.divider()
        st.caption("ACCOUNT")

        username = st.session_state.get("username", "User")
        first_letter = username[0].upper() if username else "U"

        st.markdown(f"### {first_letter}  {username}")
        st.caption("Personal workspace")
        st.write("")

        logout_clicked = st.button(
            "Logout",
            use_container_width=True,
        )

        if logout_clicked:
            token = st.session_state.get("session_token")

            if not token:
                token = cookies.get(cookie=SESSION_COOKIE_NAME)

            if token:
                db = None

                try:
                    db = SessionLocal()
                    revoke_user_session(db, token)
                except Exception:
                    logging.exception(
                        "Failed to revoke the MemoryNest session "
                        "during logout."
                    )
                finally:
                    if db is not None:
                        try:
                            db.close()
                        except Exception:
                            logging.exception(
                                "Failed to close the database session "
                                "during logout."
                            )

            try:
                cookies.delete(cookie=SESSION_COOKIE_NAME)
            except Exception:
                logging.exception(
                    "Failed to delete the MemoryNest session cookie "
                    "during logout."
                )
            finally:
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()

        st.divider()
        st.caption("MemoryNest v0.1.0")
        st.caption("Building your second brain.")

    return selected_page
