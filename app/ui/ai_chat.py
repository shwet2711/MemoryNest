from __future__ import annotations

from typing import Any

import streamlit as st

from app.services.answer_service import (
    get_ollama_model,
    is_ollama_available,
)
from app.services.chat_service import (
    chat_with_memorynest,
    get_chat_documents,
    get_retrieved_passages,
    get_source_details,
    save_chat_exchange,
)
from app.services.conversation_service import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversations,
    rename_conversation,
    update_conversation_scope,
)


DEFAULT_TOP_K = 5
MAX_TITLE_LENGTH = 50


def _initialize_chat_state() -> None:
    """Initialize AI Chat session state."""

    defaults = {
        "ai_chat_messages": [],
        "ai_chat_conversations": [],
        "ai_chat_conversation_id": None,
        "ai_chat_document_id": None,
        "ai_chat_top_k": DEFAULT_TOP_K,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _inject_ai_chat_styles() -> None:
    """Apply lightweight page-level styling for the AI Chat page."""

    st.markdown(
        """
        <style>
        /* =====================================================
           MEMORYNEST AI CHAT
           ===================================================== */

        .mn-chat-title {
            margin-bottom: 0.15rem;
        }

        .mn-chat-subtitle {
            color: #6b7280;
            margin-bottom: 1rem;
        }

        .mn-status-card {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 12px;
            padding: 0.75rem 0.9rem;
            margin-bottom: 0.75rem;
        }

        .mn-status-title {
            font-weight: 600;
            margin-bottom: 0.15rem;
        }

        .mn-status-text {
            color: #6b7280;
            font-size: 0.85rem;
        }

        .mn-empty-card {
            border: 1px dashed rgba(128, 128, 128, 0.35);
            border-radius: 16px;
            padding: 2rem 1.5rem;
            text-align: center;
            margin: 1rem 0;
        }

        .mn-empty-title {
            font-size: 1.25rem;
            font-weight: 650;
            margin-bottom: 0.35rem;
        }

        .mn-empty-text {
            color: #6b7280;
            margin-bottom: 0;
        }

        .mn-source-card {
            border: 1px solid rgba(128, 128, 128, 0.20);
            border-radius: 10px;
            padding: 0.65rem 0.8rem;
            margin: 0.4rem 0;
        }

        .mn-source-name {
            font-weight: 600;
            font-size: 0.92rem;
        }

        .mn-source-meta {
            color: #6b7280;
            font-size: 0.78rem;
            margin-top: 0.15rem;
        }

        .mn-passage-card {
            border-left: 3px solid rgba(128, 128, 128, 0.35);
            padding: 0.65rem 0.85rem;
            margin: 0.6rem 0;
        }

        .mn-conversation-title {
            font-weight: 600;
        }

        .mn-section-label {
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: #6b7280;
            margin-bottom: 0.45rem;
        }

        .mn-scope-card {
            border-radius: 10px;
            padding: 0.65rem 0.8rem;
            border: 1px solid rgba(128, 128, 128, 0.20);
            margin-bottom: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    """Render the AI Chat page header."""

    st.markdown(
        '<h1 class="mn-chat-title">AI Assistant</h1>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="mn-chat-subtitle">'
        "Ask questions and explore information stored in your "
        "MemoryNest knowledge base."
        "</div>",
        unsafe_allow_html=True,
    )


def _render_status() -> None:
    """Render local Ollama status."""

    available = is_ollama_available()

    if available:
        st.markdown(
            '<div class="mn-status-card">'
            '<div class="mn-status-title">Local AI is ready</div>'
            '<div class="mn-status-text">'
            f"Responses are generated locally using "
            f"{get_ollama_model()}."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="mn-status-card">'
            '<div class="mn-status-title">Local AI is unavailable</div>'
            '<div class="mn-status-text">'
            "MemoryNest can still retrieve relevant document "
            "passages, but Ollama generation is currently unavailable."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )


def _load_conversations() -> None:
    """Load the current user's conversations."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.session_state.ai_chat_conversations = []
        return

    conversations = get_conversations(
        user_id=int(user_id),
    )

    st.session_state.ai_chat_conversations = conversations

    conversation_id = st.session_state.ai_chat_conversation_id

    if conversation_id is None:
        return

    conversation_exists = any(
        int(conversation.get("id")) == int(conversation_id)
        for conversation in conversations
    )

    if not conversation_exists:
        st.session_state.ai_chat_conversation_id = None
        st.session_state.ai_chat_messages = []


def _load_conversation_messages(
    conversation_id: int,
) -> None:
    """Load persisted messages for one conversation."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        return

    conversation = get_conversation(
        conversation_id=int(conversation_id),
        user_id=int(user_id),
    )

    if conversation is None:
        st.session_state.ai_chat_messages = []
        return

    document_id = conversation.get("document_id")

    st.session_state.ai_chat_document_id = document_id

    messages: list[dict[str, Any]] = []

    for message in conversation.get("messages", []):
        item: dict[str, Any] = {
            "role": message.get("role"),
            "content": message.get("content", ""),
        }

        # Persisted messages contain source names but not the
        # original retrieval result. Therefore we only restore
        # the text and mode here.
        if message.get("role") == "assistant":
            item["result"] = {
                "answer": message.get("content", ""),
                "mode": message.get("mode"),
                "sources": message.get("sources") or [],
            }

        messages.append(item)

    st.session_state.ai_chat_messages = messages


def _select_conversation(conversation_id: int) -> None:
    """Switch to an existing conversation."""

    st.session_state.ai_chat_conversation_id = int(
        conversation_id
    )

    _load_conversation_messages(
        int(conversation_id)
    )


def _create_new_chat() -> None:
    """Create a fresh conversation."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.error(
            "Your session has expired. Please log in again."
        )
        return

    conversation = create_conversation(
        user_id=int(user_id),
        title="New Conversation",
        document_id=None,
    )

    st.session_state.ai_chat_conversation_id = int(
        conversation["id"]
    )

    st.session_state.ai_chat_document_id = None
    st.session_state.ai_chat_messages = []

    _load_conversations()


def _ensure_active_conversation() -> bool:
    """Ensure an active conversation exists."""

    conversation_id = (
        st.session_state.ai_chat_conversation_id
    )

    if conversation_id:
        return True

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.error(
            "Your session has expired. Please log in again."
        )
        return False

    conversation = create_conversation(
        user_id=int(user_id),
        title="New Conversation",
        document_id=(
            st.session_state.ai_chat_document_id
        ),
    )

    st.session_state.ai_chat_conversation_id = int(
        conversation["id"]
    )

    _load_conversations()

    return True


def _update_conversation_title(query: str) -> None:
    """Create a short title from the first user question."""

    user_id = st.session_state.get("user_id")
    conversation_id = (
        st.session_state.ai_chat_conversation_id
    )

    if not user_id or not conversation_id:
        return

    title = " ".join(query.strip().split())

    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 3] + "..."

    rename_conversation(
        conversation_id=int(conversation_id),
        user_id=int(user_id),
        title=title,
    )


def _render_conversation_list() -> None:
    """Render saved conversations."""

    conversations = (
        st.session_state.ai_chat_conversations
    )

    if not conversations:
        st.caption("No conversations yet.")
        return

    for conversation in conversations:
        conversation_id = int(
            conversation["id"]
        )

        title = conversation.get(
            "title",
            "New Conversation",
        )

        is_active = (
            conversation_id
            == st.session_state.ai_chat_conversation_id
        )

        button_label = (
            f"●  {title}"
            if is_active
            else f"○  {title}"
        )

        if st.button(
            button_label,
            key=f"conversation_{conversation_id}",
            use_container_width=True,
        ):
            _select_conversation(
                conversation_id
            )
            st.rerun()


def _render_document_scope() -> None:
    """Render document scope selection."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        return

    documents = get_chat_documents(
        user_id=int(user_id)
    )

    options: list[tuple[str, int | None]] = [
        ("All Documents", None)
    ]

    for document in documents:
        options.append(
            (
                str(
                    document.get(
                        "filename",
                        f"Document {document.get('id')}",
                    )
                ),
                int(document["id"]),
            )
        )

    current_document_id = (
        st.session_state.ai_chat_document_id
    )

    current_index = 0

    for index, (_, document_id) in enumerate(options):
        if document_id == current_document_id:
            current_index = index
            break

    selected_label = st.selectbox(
        "Knowledge scope",
        options=[
            label
            for label, _ in options
        ],
        index=current_index,
        key="ai_chat_scope_selector",
    )

    selected_document_id = next(
        document_id
        for label, document_id in options
        if label == selected_label
    )

    if selected_document_id == current_document_id:
        return

    st.session_state.ai_chat_document_id = (
        selected_document_id
    )

    conversation_id = (
        st.session_state.ai_chat_conversation_id
    )

    if conversation_id:
        update_conversation_scope(
            conversation_id=int(conversation_id),
            user_id=int(user_id),
            document_id=selected_document_id,
        )

        _load_conversations()


def _render_chat_controls() -> None:
    """Render the AI Chat control panel."""

    st.markdown(
        '<div class="mn-section-label">Conversation</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "New Chat",
        type="primary",
        use_container_width=True,
    ):
        _create_new_chat()
        st.rerun()

    st.write("")

    _render_conversation_list()

    st.divider()

    st.markdown(
        '<div class="mn-section-label">Knowledge Scope</div>',
        unsafe_allow_html=True,
    )

    _render_document_scope()

    st.slider(
        "Retrieved passages",
        min_value=1,
        max_value=10,
        value=int(
            st.session_state.ai_chat_top_k
        ),
        key="ai_chat_top_k",
        help=(
            "Controls how many relevant document "
            "passages are retrieved for each question."
        ),
    )

    st.caption(
        "Higher values provide more context but may "
        "make answers slower."
    )

    conversation_id = (
        st.session_state.ai_chat_conversation_id
    )

    if conversation_id:
        st.divider()

        if st.button(
            "Delete Current Chat",
            use_container_width=True,
        ):
            user_id = st.session_state.get("user_id")

            if user_id:
                deleted = delete_conversation(
                    conversation_id=int(
                        conversation_id
                    ),
                    user_id=int(user_id),
                )

                if deleted:
                    st.session_state.ai_chat_conversation_id = (
                        None
                    )
                    st.session_state.ai_chat_document_id = (
                        None
                    )
                    st.session_state.ai_chat_messages = []

                    _load_conversations()

                    st.rerun()


def _render_sources(
    result: dict[str, Any],
) -> None:
    """Render source documents and retrieved passages."""

    sources = get_source_details(result)

    if not sources:
        return

    st.markdown("#### Sources")

    displayed_sources: set[
        tuple[str, object]
    ] = set()

    for source in sources:
        filename = str(
            source.get(
                "filename",
                "Unknown source",
            )
        )

        page_number = source.get(
            "page_number"
        )

        key = (
            filename,
            page_number,
        )

        if key in displayed_sources:
            continue

        displayed_sources.add(key)

        metadata_parts = []

        if page_number is not None:
            metadata_parts.append(
                f"Page {page_number}"
            )

        chunk_index = source.get(
            "chunk_index"
        )

        if chunk_index is not None:
            metadata_parts.append(
                f"Chunk {chunk_index}"
            )

        metadata = (
            " · ".join(metadata_parts)
            if metadata_parts
            else "Retrieved from your knowledge base"
        )

        st.markdown(
            '<div class="mn-source-card">'
            f'<div class="mn-source-name">{filename}</div>'
            f'<div class="mn-source-meta">{metadata}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    passages = get_retrieved_passages(result)

    if not passages:
        return

    with st.expander(
        "View retrieved passages",
        expanded=False,
    ):
        for index, passage in enumerate(
            passages,
            start=1,
        ):
            metadata = (
                passage.get("metadata")
                or {}
            )

            filename = str(
                metadata.get(
                    "source_filename",
                    "Unknown source",
                )
            )

            page_number = metadata.get(
                "page_number"
            )

            chunk_index = metadata.get(
                "chunk_index",
                "Unknown",
            )

            distance = passage.get(
                "distance"
            )

            st.markdown(
                '<div class="mn-passage-card">'
                f"<strong>Passage {index}</strong><br>"
                f"{filename}"
                "</div>",
                unsafe_allow_html=True,
            )

            meta_parts = [
                f"Chunk {chunk_index}"
            ]

            if page_number is not None:
                meta_parts.append(
                    f"Page {page_number}"
                )

            if distance is not None:
                meta_parts.append(
                    f"Distance {float(distance):.4f}"
                )

            st.caption(
                " · ".join(meta_parts)
            )

            content = str(
                passage.get(
                    "content",
                    "",
                )
            ).strip()

            if content:
                st.write(content)


def _render_chat_history() -> None:
    """Render the active conversation."""

    messages = (
        st.session_state.ai_chat_messages
    )

    for message in messages:
        role = message.get("role")

        if role == "user":
            with st.chat_message("user"):
                st.write(
                    message.get(
                        "content",
                        "",
                    )
                )

        elif role == "assistant":
            with st.chat_message("assistant"):
                st.write(
                    message.get(
                        "content",
                        "",
                    )
                )

                result = message.get(
                    "result"
                )

                if not result:
                    continue

                mode = result.get("mode")

                if mode == "ollama":
                    st.caption(
                        "Generated locally with "
                        f"{get_ollama_model()}"
                    )
                else:
                    st.caption(
                        "Retrieval-only response"
                    )

                _render_sources(result)


def _render_empty_state() -> None:
    """Render the initial empty AI Chat state."""

    st.markdown(
        '<div class="mn-empty-card">'
        '<div class="mn-empty-title">'
        "Ask your knowledge base"
        "</div>"
        '<div class="mn-empty-text">'
        "Ask questions about the documents stored "
        "in MemoryNest."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Try asking")

    suggestions = [
        "What problem does MindSync aim to solve?",
        "What are the main objectives of MindSync?",
        "What technologies are mentioned in the document?",
    ]

    columns = st.columns(3)

    for index, suggestion in enumerate(
        suggestions
    ):
        with columns[index]:
            if st.button(
                suggestion,
                key=f"suggestion_{index}",
                use_container_width=True,
            ):
                _process_query(suggestion)
                st.rerun()


def _process_query(query: str) -> None:
    """Process, display, and persist a new question."""

    query = query.strip()

    if not query:
        return

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.error(
            "Your session has expired. Please log in again."
        )
        return

    if not _ensure_active_conversation():
        return

    conversation_id = (
        st.session_state.ai_chat_conversation_id
    )

    is_first_message = (
        len(
            st.session_state.ai_chat_messages
        )
        == 0
    )

    selected_document_id = (
        st.session_state.ai_chat_document_id
    )

    st.session_state.ai_chat_messages.append(
        {
            "role": "user",
            "content": query,
        }
    )

    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        with st.spinner(
            "Searching your knowledge base..."
        ):
            try:
                result = chat_with_memorynest(
                    user_id=int(user_id),
                    query=query,
                    top_k=int(
                        st.session_state.ai_chat_top_k
                    ),
                    document_id=selected_document_id,
                )

                answer = result.get(
                    "answer",
                    "I couldn't generate an answer.",
                )

                st.write(answer)

                mode = result.get("mode")

                if mode == "ollama":
                    st.caption(
                        "Generated locally with "
                        f"{get_ollama_model()}"
                    )
                else:
                    st.caption(
                        "Retrieval-only response"
                    )

                _render_sources(result)

                st.session_state.ai_chat_messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "result": result,
                    }
                )

                save_chat_exchange(
                    conversation_id=int(
                        conversation_id
                    ),
                    user_id=int(user_id),
                    query=query,
                    result=result,
                    top_k=int(
                        st.session_state.ai_chat_top_k
                    ),
                )

                if is_first_message:
                    _update_conversation_title(
                        query
                    )

                _load_conversations()

            except Exception as exc:
                error_message = (
                    "Something went wrong while "
                    "processing your question."
                )

                st.error(error_message)

                st.caption(
                    f"Technical detail: {exc}"
                )

                st.session_state.ai_chat_messages.append(
                    {
                        "role": "assistant",
                        "content": error_message,
                    }
                )


def ai_chat_page() -> None:
    """Render the complete MemoryNest AI Assistant page."""

    _initialize_chat_state()
    _inject_ai_chat_styles()

    _load_conversations()

    _render_header()
    _render_status()

    st.divider()

    chat_sidebar, chat_content = st.columns(
        [0.27, 0.73],
        gap="large",
        vertical_alignment="top",
    )

    with chat_sidebar:
        with st.container(border=True):
            _render_chat_controls()

    with chat_content:
        if st.session_state.ai_chat_messages:
            _render_chat_history()
        else:
            _render_empty_state()

        query = st.chat_input(
            "Ask MemoryNest about your documents..."
        )

        if query:
            _process_query(query)