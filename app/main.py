
import streamlit as st
import extra_streamlit_components as stx

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.services.session_service import get_user_for_session
from app.ui.auth_ui import authentication_page
from app.ui.dashboard import dashboard_page, placeholder_page
from app.ui.documents import documents_page
from app.ui.sidebar import render_sidebar
from app.ui.styles import apply_custom_css
from app.ui.ai_chat import ai_chat_page
from app.ui.summary import summary_page
from app.ui.knowledge_graph import knowledge_graph_page
from app.ui.events import events_page
from app.ui.calendar_view import calendar_page
from app.ui.memories import memories_page
from app.ui.search import search_page
from app.ui.google_calendar import (
    google_calendar_page,
    handle_google_oauth_callback,
)
from app.ui.gmail_settings import (
    gmail_settings_page,
    handle_gmail_oauth_callback,
)


SESSION_COOKIE_NAME = "memorynest_session"


st.set_page_config(
    page_title="MemoryNest",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()
init_database()

# Keep this component key stable across Streamlit reruns.
cookies = stx.CookieManager(key="memorynest_cookies")


def restore_login_from_cookie() -> bool:
    """Restore the logged-in user from a valid browser session cookie."""

    token = cookies.get(cookie=SESSION_COOKIE_NAME)

    if not token or not isinstance(token, str):
        return False

    db = SessionLocal()
    try:
        user = get_user_for_session(db, token)

        if user is None:
            return False

        st.session_state["user_id"] = user.id
        st.session_state["username"] = user.username
        st.session_state["session_token"] = token
        return True
    finally:
        db.close()


def main() -> None:
    if "user_id" not in st.session_state:
        if not restore_login_from_cookie():
            authentication_page(cookies)
            return

    # Handle Gmail redirects before Calendar so each integration
    # processes only its own signed OAuth state.
    if handle_gmail_oauth_callback():
        return

    if handle_google_oauth_callback():
        return

    selected_page = render_sidebar(cookies)

    if selected_page == "Dashboard":
        dashboard_page()
    elif selected_page == "Documents":
        documents_page()
    elif selected_page == "AI Chat":
        ai_chat_page()
    elif selected_page == "Summaries":
        summary_page()
    elif selected_page == "Events":
        events_page()
    elif selected_page == "Calendar":
        # Keep Google Calendar controls within the existing Calendar page.
        google_calendar_page()
        calendar_page()
    elif selected_page == "Knowledge Graph":
        knowledge_graph_page()
    elif selected_page == "Memories":
        memories_page()
    elif selected_page == "Search":
        search_page()
    elif selected_page == "Settings":
        gmail_settings_page()


if __name__ == "__main__":
    main()
