import streamlit as st

from app.db.init_db import init_database
from app.ui.auth_ui import authentication_page
from app.ui.dashboard import dashboard_page
from app.ui.documents import documents_page
from app.ui.dashboard import placeholder_page
from app.ui.sidebar import render_sidebar
from app.ui.styles import apply_custom_css
from app.ui.ai_chat import ai_chat_page
from app.ui.summary import summary_page

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="MemoryNest",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# GLOBAL STYLING
# ============================================================

apply_custom_css()


# ============================================================
# DATABASE
# ============================================================

init_database()


# ============================================================
# MAIN
# ============================================================

def main():

    if "user_id" not in st.session_state:

        authentication_page()

        return

    selected_page = render_sidebar()

    if selected_page == "Dashboard":

        dashboard_page()

    elif selected_page == "Documents":

        documents_page()

    elif selected_page == "AI Chat":
        ai_chat_page()

    elif selected_page == "Summaries":

        summary_page()

    elif selected_page == "Memories":

        placeholder_page(
            title="Memories",
            icon="🧠",
            description=(
                "Explore important information "
                "extracted from your knowledge base."
            ),
        )

    elif selected_page == "Search":

        placeholder_page(
            title="Search",
            icon="🔎",
            description=(
                "Search your personal knowledge "
                "using semantic search."
            ),
        )

    elif selected_page == "Settings":

        placeholder_page(
            title="Settings",
            icon="⚙️",
            description=(
                "Manage your MemoryNest account "
                "and application preferences."
            ),
        )


if __name__ == "__main__":

    main()
