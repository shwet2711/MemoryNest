
from __future__ import annotations

import logging

import streamlit as st

from app.db.session import SessionLocal
from app.services.document_service import get_document
from app.services.search_service import semantic_search

logger = logging.getLogger(__name__)


def _navigate_to_memory(user_id: int, document_id: int) -> None:
    """Select a source document and navigate to Memories."""

    db = SessionLocal()

    try:
        document = get_document(
            db=db,
            user_id=user_id,
            document_id=document_id,
        )
    except Exception:
        logger.exception(
            "Could not retrieve document %s for user %s",
            document_id,
            user_id,
        )
        st.session_state["memory_navigation_error"] = (
            "Unable to open this source. Please try again."
        )
        return
    finally:
        db.close()

    if document is None:
        st.session_state["memory_navigation_error"] = (
            "This source is no longer available in your account."
        )
        return

    st.session_state["memories_selected_document_id"] = document.id
    st.session_state["navigation_radio"] = "Memories"
    st.query_params["page"] = "Memories"


def search_page() -> None:
    """Search the signed-in user's indexed document content."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.error("Please sign in again.")
        return

    st.title("🔎 Search")
    st.caption(
        "Search the meaning of your documents and review the matching "
        "passages with their source information."
    )

    with st.form("memory_semantic_search_form"):
        query = st.text_input(
            "What are you looking for?",
            placeholder=(
                "e.g. exam fee deadline, project objectives, "
                "internship details"
            ),
        ).strip()

        top_k = st.slider(
            "Maximum results",
            min_value=3,
            max_value=15,
            value=5,
        )

        submitted = st.form_submit_button(
            "Search my documents",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not query:
            st.warning("Enter a search question or topic first.")
            return

        try:
            with st.spinner(
                "Searching your personal knowledge library..."
            ):
                results = semantic_search(
                    query=query,
                    user_id=user_id,
                    top_k=top_k,
                )

            # Store results so button clicks and other reruns
            # do not immediately clear the search page.
            st.session_state["memory_search_results"] = results
            st.session_state["memory_search_query"] = query

        except Exception:
            logger.exception(
                "Semantic search failed for user %s",
                user_id,
            )
            st.error(
                "Search could not be completed. Check that the embedding "
                "service and vector store are available, then try again."
            )
            return

    navigation_error = st.session_state.pop(
        "memory_navigation_error",
        None,
    )

    if navigation_error:
        st.warning(navigation_error)

    results = st.session_state.get("memory_search_results")
    saved_query = st.session_state.get("memory_search_query", "")

    if results is None:
        st.info(
            "Enter a question or topic to search the extracted content "
            "of your indexed documents."
        )
        return

    if not results:
        st.info(
            "No sufficiently relevant passages were found. Try different "
            "keywords, a more specific question, or check that the document "
            "has finished indexing."
        )
        return

    st.caption(f"Search query: {saved_query}")
    st.success(f"Found {len(results)} relevant passage(s).")

    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata") or {}
        content = result.get("content", "").strip()

        source_name = (
            metadata.get("source_filename")
            or metadata.get("filename")
            or "Uploaded document"
        )

        page_number = metadata.get("page_number")
        document_id = metadata.get("document_id")
        distance = result.get("distance")

        with st.container(border=True):
            st.markdown(f"**Result {index}: {source_name}**")

            details = []

            if page_number is not None:
                details.append(f"Page {page_number}")

            if metadata.get("chunk_index") is not None:
                details.append(
                    f"Passage {int(metadata['chunk_index']) + 1}"
                )

            if distance is not None:
                details.append(
                    f"Semantic distance: {float(distance):.3f}"
                )

            if details:
                st.caption(" · ".join(details))

            st.write(content or "No passage text was returned.")

            try:
                parsed_document_id = (
                    int(document_id)
                    if document_id is not None
                    else None
                )
            except (TypeError, ValueError):
                parsed_document_id = None

            if parsed_document_id is not None:
                st.button(
                    "Review this source in Memories",
                    key=(
                        f"search_review_source_{index}_"
                        f"{parsed_document_id}"
                    ),
                    on_click=_navigate_to_memory,
                    args=(user_id, parsed_document_id),
                )
