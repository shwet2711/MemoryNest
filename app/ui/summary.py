from __future__ import annotations

from typing import Any

import streamlit as st

from app.services.chat_service import get_chat_documents
from app.services.summary_service import summarize_document
from app.services.tts_service import generate_speech_audio


def _initialize_summary_state() -> None:
    if "summary_document_id" not in st.session_state:
        st.session_state.summary_document_id = None

    if "summary_result" not in st.session_state:
        st.session_state.summary_result = None

    if "summary_audio" not in st.session_state:
        st.session_state.summary_audio = None

    if "summary_audio_document_id" not in st.session_state:
        st.session_state.summary_audio_document_id = None


def _render_header() -> None:
    st.title("Document Summary")

    st.caption(
        "Generate a concise AI summary from a document "
        "stored in your MemoryNest knowledge base."
    )


def _render_empty_state() -> None:
    st.info(
        "No documents are available yet. "
        "Upload and process a document first."
    )


def _generate_summary_audio(
    *,
    summary: str,
    document_id: int,
) -> None:
    if not summary.strip():
        st.warning(
            "There is no summary available to read aloud."
        )
        return

    with st.spinner(
        "Generating audio from the summary..."
    ):
        try:
            audio = generate_speech_audio(
                text=summary,
            )

            st.session_state.summary_audio = audio

            st.session_state.summary_audio_document_id = (
                document_id
            )

            st.success(
                "Audio generated successfully."
            )

        except Exception as exc:
            st.session_state.summary_audio = None

            st.session_state.summary_audio_document_id = (
                None
            )

            st.error(
                "Unable to generate speech audio."
            )

            st.caption(
                f"Technical detail: {exc}"
            )


def _render_summary_audio(
    *,
    document_id: int,
) -> None:
    audio = st.session_state.get(
        "summary_audio"
    )

    audio_document_id = (
        st.session_state.get(
            "summary_audio_document_id"
        )
    )

    if (
        audio is not None
        and audio_document_id == document_id
    ):
        st.markdown("#### Listen to Summary")

        st.audio(
            audio,
            format="audio/wav",
        )


def _render_summary_result(
    result: dict[str, Any],
) -> None:
    filename = result.get(
        "filename",
        "Document",
    )

    st.markdown(
        f"### {filename}"
    )

    mode = result.get("mode")

    if mode == "ollama":
        model = result.get(
            "model",
            "local Ollama model",
        )

        st.success(
            f"Summary generated locally using {model}."
        )

    elif mode == "unavailable":
        st.warning(
            result.get(
                "summary",
                "Ollama is unavailable.",
            )
        )
        return

    st.markdown("#### AI Summary")

    summary_text = result.get(
        "summary",
        "No summary was generated.",
    )

    st.markdown(summary_text)

    # ---------------------------------------------------------
    # Text-to-Speech
    # ---------------------------------------------------------

    document_id = int(
        result.get("document_id")
    )

    st.markdown(
        "#### Listen to Summary"
    )

    st.caption(
        "Generate a local audio version of this summary."
    )

    audio_col, info_col = st.columns(
        [1, 3]
    )

    with audio_col:
        generate_audio_clicked = st.button(
            "Listen to Summary",
            use_container_width=True,
        )

    with info_col:
        st.caption(
            "Audio is generated locally using your "
            "computer's speech engine."
        )

    if generate_audio_clicked:
        _generate_summary_audio(
            summary=summary_text,
            document_id=document_id,
        )

    _render_summary_audio(
        document_id=document_id,
    )

    # ---------------------------------------------------------
    # Summary statistics
    # ---------------------------------------------------------

    text_length = result.get(
        "text_length"
    )

    summarized_text_length = result.get(
        "summarized_text_length"
    )

    if text_length is not None:
        if result.get("truncated"):
            st.caption(
                f"The document contains approximately "
                f"{text_length:,} characters. "
                f"The first {summarized_text_length:,} "
                f"characters were used for this summary."
            )
        else:
            st.caption(
                f"Summary generated from "
                f"{text_length:,} characters "
                f"of extracted text."
            )


def summary_page() -> None:
    _initialize_summary_state()

    _render_header()

    user_id = st.session_state.get(
        "user_id"
    )

    if not user_id:
        st.error(
            "Your session has expired. "
            "Please log in again."
        )
        return

    documents = get_chat_documents(
        user_id=int(user_id)
    )

    if not documents:
        _render_empty_state()
        return

    completed_documents = [
        document
        for document in documents
        if document.get(
            "extraction_status"
        ) == "completed"
    ]

    if not completed_documents:
        st.warning(
            "No document has completed "
            "text extraction yet."
        )
        return

    # ---------------------------------------------------------
    # Document selection
    # ---------------------------------------------------------

    document_options = {
        str(
            document.get(
                "filename",
                f"Document {document['id']}",
            )
        ): int(document["id"])
        for document in completed_documents
    }

    labels = list(
        document_options.keys()
    )

    current_document_id = (
        st.session_state.summary_document_id
    )

    default_index = 0

    if current_document_id is not None:
        for index, label in enumerate(labels):
            if (
                document_options[label]
                == current_document_id
            ):
                default_index = index
                break

    selected_filename = st.selectbox(
        "Select a document",
        options=labels,
        index=default_index,
    )

    selected_document_id = (
        document_options[selected_filename]
    )

    st.session_state.summary_document_id = (
        selected_document_id
    )

    # ---------------------------------------------------------
    # Search documents
    # ---------------------------------------------------------

    search_query = st.text_input(
        "Search documents",
        placeholder="Search by document name...",
        help=(
            "Type part of a document name "
            "or title to quickly find it."
        ),
    )

    filtered_documents = completed_documents

    if search_query.strip():
        query = search_query.strip().lower()

        filtered_documents = [
            document
            for document in completed_documents
            if query
            in str(
                document.get(
                    "filename",
                    "",
                )
            ).lower()
            or query
            in str(
                document.get(
                    "title"
                )
                or ""
            ).lower()
        ]

    if search_query.strip():

        if not filtered_documents:
            st.warning(
                "No matching documents found."
            )
            return

        filtered_options = {
            str(
                document.get(
                    "filename",
                    f"Document {document['id']}",
                )
            ): int(document["id"])
            for document in filtered_documents
        }

        filtered_labels = list(
            filtered_options.keys()
        )

        current_filtered_index = 0

        if selected_document_id in (
            filtered_options.values()
        ):
            current_filtered_index = list(
                filtered_options.values()
            ).index(
                selected_document_id
            )

        searched_filename = st.selectbox(
            "Matching documents",
            options=filtered_labels,
            index=current_filtered_index,
        )

        selected_document_id = (
            filtered_options[
                searched_filename
            ]
        )

        st.session_state.summary_document_id = (
            selected_document_id
        )

    # ---------------------------------------------------------
    # Generate summary
    # ---------------------------------------------------------

    st.divider()

    left, right = st.columns(
        [3, 1]
    )

    with left:
        st.markdown(
            "### Generate an AI summary"
        )

        st.caption(
            "MemoryNest will use the extracted text "
            "from the selected document and the local "
            "Ollama model to create the summary."
        )

    with right:
        generate_clicked = st.button(
            "Generate Summary",
            type="primary",
            use_container_width=True,
        )

    if generate_clicked:

        # Clear audio from the previous summary.
        st.session_state.summary_audio = None
        st.session_state.summary_audio_document_id = (
            None
        )

        with st.spinner(
            "Reading the document and generating summary..."
        ):
            try:
                result = summarize_document(
                    user_id=int(user_id),
                    document_id=selected_document_id,
                )

                st.session_state.summary_result = (
                    result
                )

            except Exception as exc:
                st.session_state.summary_result = None

                st.error(
                    "Unable to generate the "
                    "document summary."
                )

                st.caption(
                    f"Technical detail: {exc}"
                )

    # ---------------------------------------------------------
    # Display summary result
    # ---------------------------------------------------------

    result = st.session_state.summary_result

    if result is not None:

        st.divider()

        if (
            result.get("document_id")
            != selected_document_id
        ):
            st.session_state.summary_result = None
            st.session_state.summary_audio = None
            st.session_state.summary_audio_document_id = (
                None
            )

        else:
            _render_summary_result(
                result
            )