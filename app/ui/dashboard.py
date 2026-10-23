from __future__ import annotations

import logging

import streamlit as st

from app.db.chunk_model import DocumentChunk
from app.db.conversation_model import Conversation
from app.db.document_model import Document
from app.db.embedding_model import ChunkEmbedding
from app.db.session import SessionLocal
from app.ui.components import render_footer

logger = logging.getLogger(__name__)

def _navigate(page_label: str, page_value: str) -> None:
    """Queue navigation for the sidebar before its radio widget is created."""
    st.session_state["pending_navigation_label"] = page_label
    st.query_params["page"] = page_value
    st.rerun()


def _load_dashboard_data(user_id: int) -> dict:
    """Load dashboard counts and recent documents for one user."""
    db = SessionLocal()

    try:
        documents_query = db.query(Document).filter(
            Document.user_id == user_id
        )

        return {
            "document_count": documents_query.count(),
            "conversation_count": (
                db.query(Conversation)
                .filter(Conversation.user_id == user_id)
                .count()
            ),
            "chunk_count": (
                db.query(DocumentChunk)
                .filter(DocumentChunk.user_id == user_id)
                .count()
            ),
            "embedding_count": (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.user_id == user_id)
                .count()
            ),
            "recent_documents": (
                documents_query
                .order_by(Document.created_at.desc())
                .limit(5)
                .all()
            ),
        }
    finally:
        db.close()


def dashboard_page() -> None:
    """Render the signed-in user's personal knowledge dashboard."""
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username") or "there"

    st.markdown(
        """
        <style>
        .mn-hero {
            padding: 1.5rem 1.7rem;
            margin-bottom: 1.25rem;
            border-radius: 18px;
            background: linear-gradient(120deg, #172554, #1d4ed8);
            color: #ffffff;
        }
        .mn-hero h1 {
            color: #ffffff;
            font-size: 1.85rem;
            margin: 0 0 0.45rem 0;
        }
        .mn-hero p {
            color: #e0eaff;
            margin: 0;
            font-size: 1rem;
        }
        .mn-section-title {
            font-size: 1.2rem;
            font-weight: 650;
            margin-top: 1.2rem;
            margin-bottom: 0.15rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="mn-hero">
            <h1>Welcome back, {username}</h1>
            <p>Your personal knowledge workspace, all in one place.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not user_id:
        st.error("Your session could not be verified. Please sign in again.")
        return

    try:
        data = _load_dashboard_data(user_id)
    except Exception:
        logger.exception(
            "Could not load dashboard metrics for user %s",
            user_id,
        )
        st.error(
            "Dashboard data could not be loaded. "
            "Please check the database connection and try again."
        )
        return

    search_col, button_col = st.columns([5, 1])

    with search_col:
        search_query = st.text_input(
            "Search your knowledge",
            placeholder="Search your documents and their content...",
            label_visibility="collapsed",
            key="dashboard_search",
        ).strip()

    with button_col:
        search_clicked = st.button(
            "Search",
            type="primary",
            use_container_width=True,
            key="dashboard_search_button",
        )

    if search_clicked:
        if search_query:
            st.session_state["memory_search_prefill"] = search_query
        _navigate("Search", "Search")

    st.markdown(
        '<div class="mn-section-title">Workspace overview</div>',
        unsafe_allow_html=True,
    )
    st.caption("Live totals from your account.")

    metric_columns = st.columns(4)

    metrics = [
        ("Documents", data["document_count"]),
        ("AI Conversations", data["conversation_count"]),
        ("Indexed Chunks", data["chunk_count"]),
        ("Stored Embeddings", data["embedding_count"]),
    ]

    for column, (label, value) in zip(metric_columns, metrics):
        with column:
            with st.container(border=True):
                st.metric(label, value)

    st.markdown(
        '<div class="mn-section-title">Quick actions</div>',
        unsafe_allow_html=True,
    )
    st.caption("Continue working with your personal knowledge.")

    action1, action2, action3 = st.columns(3)

    with action1:
        with st.container(border=True):
            st.markdown("### Upload documents")
            st.caption(
                "Add PDF, DOCX, TXT or supported image files "
                "to your knowledge library."
            )
            if st.button(
                "Open Documents",
                key="dashboard_upload",
                use_container_width=True,
                type="primary",
            ):
                _navigate("Documents", "Documents")

    with action2:
        with st.container(border=True):
            st.markdown("### Ask AI")
            st.caption(
                "Ask questions about your documents "
                "and review answers with sources."
            )
            if st.button(
                "Open AI Assistant",
                key="dashboard_ai",
                use_container_width=True,
            ):
                _navigate("AI Assistant", "AI Chat")

    with action3:
        with st.container(border=True):
            st.markdown("### Explore memories")
            st.caption(
                "Review the memories and information "
                "available in your workspace."
            )
            if st.button(
                "View Memories",
                key="dashboard_memories",
                use_container_width=True,
            ):
                _navigate("Memories", "Memories")

    recent_column, snapshot_column = st.columns([1.5, 1])

    with recent_column:
        st.markdown(
            '<div class="mn-section-title">Recent documents</div>',
            unsafe_allow_html=True,
        )

        recent_documents = data["recent_documents"]

        if not recent_documents:
            with st.container(border=True):
                st.markdown("### Your library starts here")
                st.write(
                    "Upload a document to start building "
                    "your personal knowledge library."
                )
                if st.button(
                    "Upload your first document",
                    key="dashboard_first_upload",
                    type="primary",
                ):
                    _navigate("Documents", "Documents")
        else:
            for document in recent_documents:
                with st.container(border=True):
                    st.markdown(
                        f"**{document.original_filename}**"
                    )
                    status = (
                        getattr(document, "extraction_status", None)
                        or "unknown"
                    )
                    st.caption(
                        f"Status: {status.replace('_', ' ').title()}"
                    )

    with snapshot_column:
        st.markdown(
            '<div class="mn-section-title">Knowledge snapshot</div>',
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.metric("Indexed content chunks", data["chunk_count"])
            st.divider()
            st.metric("Stored embeddings", data["embedding_count"])
            st.divider()
            st.metric("Documents in your library", data["document_count"])

    render_footer()


def placeholder_page(
    title: str,
    icon: str,
    description: str,
) -> None:
    """Render an application placeholder page."""
    st.title(f"{icon} {title}")
    st.caption(description)
    st.info("This section is not yet available.")
    render_footer()
