import streamlit as st

from app.ui.components import (
    render_empty_state,
    render_feature_card,
    render_footer,
    render_metric_card,
    render_section_header,
    render_status_card,
)


def dashboard_page() -> None:
    """Render the MemoryNest dashboard."""

    username = st.session_state.get(
        "username",
        "User",
    )

    # ========================================================
    # TOP HEADER
    # ========================================================

    st.title(
        f"Good evening, {username} 👋"
    )

    st.caption(
        "Here's what's happening in your personal "
        "knowledge workspace."
    )

    st.write("")

    # ========================================================
    # SEARCH BAR
    # ========================================================

    search_col, button_col = st.columns(
        [5, 1]
    )

    with search_col:

        search_query = st.text_input(
            "Search",
            placeholder=(
                "🔎 Search documents, memories, "
                "conversations..."
            ),
            label_visibility="collapsed",
            key="dashboard_search",
        )

    with button_col:

        st.button(
            "Search",
            use_container_width=True,
            type="primary",
            key="dashboard_search_button",
        )

    st.write("")

    # ========================================================
    # OVERVIEW
    # ========================================================

    render_section_header(
        "Workspace Overview",
        "A quick look at your MemoryNest activity.",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        render_metric_card(
            icon="📄",
            label="Documents",
            value="0",
        )

    with col2:

        render_metric_card(
            icon="🧠",
            label="Memories",
            value="0",
        )

    with col3:

        render_metric_card(
            icon="💬",
            label="AI Conversations",
            value="0",
        )

    with col4:

        render_metric_card(
            icon="🔎",
            label="Searches",
            value="0",
        )

    # ========================================================
    # QUICK ACTIONS
    # ========================================================

    st.write("")

    render_section_header(
        "Quick Actions",
        "Start working with your personal knowledge.",
    )

    action1, action2, action3 = st.columns(3)

    with action1:

        clicked = render_feature_card(
            icon="📤",
            title="Upload Documents",
            description=(
                "Add PDF, DOCX, TXT or image files "
                "to your personal knowledge base."
            ),
            button_text="Upload Documents →",
            button_key="dashboard_upload",
        )

        if clicked:

            st.info(
                "Document upload will be available "
                "in the next development phase."
            )

    with action2:

        clicked = render_feature_card(
            icon="💬",
            title="Ask AI",
            description=(
                "Ask questions about your documents "
                "and get answers with sources."
            ),
            button_text="Open AI Assistant →",
            button_key="dashboard_ai",
        )

        if clicked:

            st.info(
                "AI Assistant will be connected "
                "after the RAG pipeline is implemented."
            )

    with action3:

        clicked = render_feature_card(
            icon="🧠",
            title="Explore Memories",
            description=(
                "Discover useful information and "
                "important memories from your documents."
            ),
            button_text="View Memories →",
            button_key="dashboard_memories",
        )

        if clicked:

            st.info(
                "Memory extraction will be implemented "
                "in a later phase."
            )

    # ========================================================
    # LOWER DASHBOARD
    # ========================================================

    st.write("")

    left, right = st.columns(
        [1.6, 1]
    )

    # --------------------------------------------------------
    # RECENT DOCUMENTS
    # --------------------------------------------------------

    with left:

        render_section_header(
            "Recent Documents",
            "Your latest uploaded files.",
        )

        render_empty_state(
            icon="📚",
            title="No documents yet",
            description=(
                "Upload your first document and "
                "MemoryNest will begin building "
                "your personal knowledge base."
            ),
        )

    # --------------------------------------------------------
    # KNOWLEDGE SNAPSHOT
    # --------------------------------------------------------

    with right:

        render_section_header(
            "Knowledge Snapshot",
            "Your current knowledge base.",
        )

        with st.container(border=True):

            st.metric(
                "Indexed Knowledge",
                "0 chunks",
            )

            st.divider()

            st.metric(
                "Stored Embeddings",
                "0",
            )

            st.divider()

            st.metric(
                "Saved Memories",
                "0",
            )

    # ========================================================
    # SYSTEM STATUS
    # ========================================================

    st.write("")

    render_section_header(
        "System Status",
        "Current MemoryNest services.",
    )

    status1, status2, status3 = st.columns(3)

    with status1:

        render_status_card(
            icon="🗄️",
            title="Database",
            description=(
                "SQLite database and user accounts."
            ),
            status="success",
        )

    with status2:

        render_status_card(
            icon="🔐",
            title="Authentication",
            description=(
                "Secure user authentication system."
            ),
            status="success",
        )

    with status3:

        render_status_card(
            icon="🤖",
            title="AI Engine",
            description=(
                "RAG and local LLM integration."
            ),
            status="warning",
        )

    # ========================================================
    # ROADMAP
    # ========================================================

    st.write("")

    render_section_header(
        "MemoryNest Roadmap",
        "Features planned for the project.",
    )

    roadmap1, roadmap2, roadmap3, roadmap4 = st.columns(4)

    with roadmap1:

        with st.container(border=True):

            st.markdown("### 📄")

            st.markdown(
                "**Document Intelligence**"
            )

            st.caption(
                "PDF, DOCX, TXT and image extraction."
            )

            st.progress(
                0.15,
                text="In progress",
            )

    with roadmap2:

        with st.container(border=True):

            st.markdown("### 🔎")

            st.markdown(
                "**Semantic Search**"
            )

            st.caption(
                "Search knowledge using embeddings."
            )

            st.progress(
                0.05,
                text="Planned",
            )

    with roadmap3:

        with st.container(border=True):

            st.markdown("### 💬")

            st.markdown(
                "**RAG AI Assistant**"
            )

            st.caption(
                "Ask questions with document sources."
            )

            st.progress(
                0.05,
                text="Planned",
            )

    with roadmap4:

        with st.container(border=True):

            st.markdown("### 🧠")

            st.markdown(
                "**Memory Engine**"
            )

            st.caption(
                "Extract and organize important memories."
            )

            st.progress(
                0.05,
                text="Planned",
            )

    # ========================================================
    # FOOTER
    # ========================================================

    render_footer()


def placeholder_page(
    title: str,
    icon: str,
    description: str,
) -> None:
    """Render an application placeholder page."""

    st.title(
        f"{icon} {title}"
    )

    st.caption(description)

    st.write("")

    with st.container(border=True):

        st.markdown(
            "### 🚧 Feature under development"
        )

        st.write(
            "This section is part of the MemoryNest "
            "development roadmap."
        )

        st.caption(
            "The backend functionality will be connected "
            "during the upcoming implementation phases."
        )

    render_footer()