
import logging

import streamlit as st

from app.db.session import SessionLocal
from app.services.session_service import revoke_user_session
from app.ui.components import render_brand


SESSION_COOKIE_NAME = "memorynest_session"


def render_sidebar(cookies) -> str:
    """Render navigation, preserve the selected page, and handle logout."""
    pages = {
        "Overview": "Dashboard",
        "Documents": "Documents",
        "AI Assistant": "AI Chat",
        "Summaries": "Summaries",
        "Memories": "Memories",
        "Search": "Search",
        "Knowledge Graph": "Knowledge Graph",
        "Settings": "Settings",
    }

    valid_pages = set(pages.values())
    requested_page = st.query_params.get("page", "Dashboard")

    if requested_page not in valid_pages:
        requested_page = "Dashboard"

    page_labels = list(pages.keys())
    page_values = list(pages.values())
    default_index = page_values.index(requested_page)

    with st.sidebar:
        render_brand()
        st.divider()
        st.caption("WORKSPACE")

        selected = st.radio(
            "Navigation",
            options=page_labels,
            index=default_index,
            label_visibility="collapsed",
            key="navigation_radio",
        )

        selected_page = pages[selected]

        # Store the selection in the URL so it survives a browser refresh.
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
            "🚪 Logout",
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
                        "Failed to revoke the MemoryNest session during logout."
                    )
                finally:
                    if db is not None:
                        try:
                            db.close()
                        except Exception:
                            logging.exception(
                                "Failed to close the database session during logout."
                            )

            # Clear local authentication state even if database revocation fails.
            try:
                cookies.delete(cookie=SESSION_COOKIE_NAME)
            except Exception:
                logging.exception(
                    "Failed to delete the MemoryNest session cookie during logout."
                )
            finally:
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()

        st.divider()
        st.caption("MemoryNest v0.1.0")
        st.caption("Building your second brain.")

    return selected_page
