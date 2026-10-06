import streamlit as st

from app.ui.components import render_brand


def render_sidebar() -> str:
    """Render the MemoryNest navigation sidebar."""

    with st.sidebar:

        render_brand()

        st.divider()

        st.caption("WORKSPACE")

        pages = {
            "Overview": "Dashboard",
            "Documents": "Documents",
            "AI Assistant": "AI Chat",
            "Summaries": "Summaries",
            "Memories": "Memories",
            "Search": "Search",
        }

        selected = st.radio(
            "Navigation",
            options=list(pages.keys()),
            label_visibility="collapsed",
        )

        selected_page = pages[selected]

        st.divider()

        st.caption("ACCOUNT")

        username = st.session_state.get(
            "username",
            "User",
        )

        first_letter = (
            username[0].upper()
            if username
            else "U"
        )

        st.markdown(
            f"### {first_letter}  {username}"
        )

        st.caption(
            "Personal workspace"
        )

        st.write("")

        settings_clicked = st.button(
            "⚙️  Settings",
            use_container_width=True,
        )

        if settings_clicked:
            selected_page = "Settings"

        logout_clicked = st.button(
            "🚪  Logout",
            use_container_width=True,
        )

        if logout_clicked:

            st.session_state.clear()
            st.rerun()

        st.divider()

        st.caption(
            "MemoryNest v0.1.0"
        )

        st.caption(
            "Building your second brain."
        )

    return selected_page