
import streamlit as st

from app.db.session import SessionLocal
from app.services.chunk_service import (
    get_document_chunks,
    process_document_chunks,
)
from app.services.indexing_service import index_document
from app.services.document_service import (
    create_document,
    delete_document,
    get_user_documents,
)
from app.ui.components import (
    render_footer,
    render_section_header,
)


def format_file_size(size: int) -> str:
    """Convert file size from bytes to a readable format."""

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def file_icon(file_type: str) -> str:
    """Return an appropriate icon for the document type."""

    icons = {
        "pdf": "📕",
        "docx": "📘",
        "txt": "📄",
        "jpg": "🖼️",
        "jpeg": "🖼️",
        "png": "🖼️",
    }

    return icons.get(
        file_type.lower(),
        "📄",
    )


def status_message(status: str) -> None:
    """Display a document extraction status."""

    if status == "completed":

        st.success(
            "Text extracted",
            icon="✅",
        )

    elif status == "ocr_required":

        st.info(
            "OCR required",
            icon="ℹ️",
        )

    elif status == "processing":

        st.warning(
            "Processing",
            icon="⏳",
        )

    else:

        st.error(
            "Extraction failed",
            icon="❌",
        )


def render_text_preview(document) -> None:
    """Display extracted text for a document."""

    if not document.extracted_text_path:

        st.info(
            "No extracted text is available yet.",
            icon="ℹ️",
        )

        return

    try:

        with open(
            document.extracted_text_path,
            "r",
            encoding="utf-8",
        ) as file:

            text = file.read()

        if not text.strip():

            st.info(
                "The extracted text is empty.",
                icon="ℹ️",
            )

            return

        st.text_area(
            "Extracted text",
            value=text,
            height=350,
            disabled=True,
            key=f"text_preview_{document.id}",
        )

        st.caption(
            f"{len(text):,} characters extracted"
        )

    except FileNotFoundError:

        st.error(
            "The extracted text file could not be found.",
            icon="❌",
        )

    except Exception as error:

        st.error(
            f"Unable to read extracted text: {error}",
            icon="❌",
        )


def render_chunk_preview(
    db,
    document,
    user_id: int,
) -> None:
    """Display chunks generated for a document."""

    chunks = get_document_chunks(
        db=db,
        document_id=document.id,
        user_id=user_id,
    )

    if not chunks:

        st.info(
            "No chunks have been created for this document yet.",
            icon="ℹ️",
        )

        return

    # ---------------------------------------------------------
    # CHUNK STATISTICS
    # ---------------------------------------------------------

    lengths = [
        chunk.character_count
        for chunk in chunks
    ]

    average_length = sum(lengths) / len(lengths)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Chunks",
            len(chunks),
        )

    with col2:
        st.metric(
            "Average",
            f"{average_length:.0f}",
        )

    with col3:
        st.metric(
            "Minimum",
            min(lengths),
        )

    with col4:
        st.metric(
            "Maximum",
            max(lengths),
        )

    st.write("")

    # ---------------------------------------------------------
    # CHUNK LIST
    # ---------------------------------------------------------

    for chunk in chunks:

        with st.expander(
            f"Chunk {chunk.chunk_index + 1} · "
            f"{chunk.character_count:,} characters"
        ):

            st.caption(
                f"Source: {chunk.source_filename}"
            )

            st.text_area(
                "Chunk content",
                value=chunk.content,
                height=220,
                disabled=True,
                key=f"chunk_preview_{chunk.id}",
            )


def documents_page() -> None:
    """Render the MemoryNest document management page."""

    user_id = st.session_state.get("user_id")

    if not user_id:

        st.error(
            "Please sign in again.",
            icon="❌",
        )

        return

    # ---------------------------------------------------------
    # PAGE HEADER
    # ---------------------------------------------------------

    st.title("📄 Documents")

    st.caption(
        "Upload and manage the documents that form "
        "your MemoryNest knowledge base."
    )

    st.write("")

    # ---------------------------------------------------------
    # UPLOAD SECTION
    # ---------------------------------------------------------

    render_section_header(
        "Upload Documents",
        (
            "Supported formats: PDF, DOCX, TXT, JPG, JPEG and PNG. "
            "Maximum size: 20 MB."
        ),
    )

    uploaded_files = st.file_uploader(
        "Choose documents",
        type=[
            "pdf",
            "docx",
            "txt",
            "jpg",
            "jpeg",
            "png",
        ],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:

        st.write("")

        st.caption(
            f"{len(uploaded_files)} document(s) selected"
        )

        if st.button(
            "⬆️  Process Selected Documents",
            type="primary",
            use_container_width=True,
        ):

            db = SessionLocal()

            successful = 0
            failed = 0

            try:

                progress = st.progress(
                    0,
                    text="Preparing documents...",
                )

                total = len(uploaded_files)

                for index, uploaded_file in enumerate(
                    uploaded_files,
                    start=1,
                ):

                    try:

                        file_bytes = uploaded_file.getvalue()

                        document = create_document(
                            db=db,
                            user_id=user_id,
                            filename=uploaded_file.name,
                            file_bytes=file_bytes,
                        )

                        process_document_chunks(
                            db=db,
                            document=document,
                            user_id=user_id,
                        )

                        index_document(
                            db=db,
                            document_id=document.id,
                            user_id=user_id,
                        )

                        successful += 1

                        progress.progress(
                            index / total,
                            text=(
                                f"Processed "
                                f"{uploaded_file.name}"
                            ),
                        )

                    except Exception as error:

                        failed += 1

                        st.error(
                            f"{uploaded_file.name}: {error}",
                            icon="❌",
                        )

                progress.empty()

                if successful:

                    st.success(
                        f"{successful} document(s) "
                        "processed successfully.",
                        icon="✅",
                    )

                if failed:

                    st.warning(
                        f"{failed} document(s) "
                        "could not be processed.",
                        icon="⚠️",
                    )

                if successful:
                    st.rerun()

            finally:

                db.close()

    st.divider()

    # ---------------------------------------------------------
    # DOCUMENT LIST
    # ---------------------------------------------------------

    render_section_header(
        "Your Documents",
        "Documents stored in your personal workspace.",
    )

    db = SessionLocal()

    try:

        documents = get_user_documents(
            db=db,
            user_id=user_id,
        )

        # -----------------------------------------------------
        # EMPTY STATE
        # -----------------------------------------------------

        if not documents:

            with st.container(border=True):

                st.markdown(
                    "### 📚 Your knowledge base is empty"
                )

                st.caption(
                    "Upload your first document above. "
                    "MemoryNest will extract its content "
                    "and prepare it for semantic search."
                )

            render_footer()

            return

        st.caption(
            f"{len(documents)} document(s) stored"
        )

        st.write("")

        # -----------------------------------------------------
        # DOCUMENT CARDS
        # -----------------------------------------------------

        for document in documents:

            with st.container(border=True):

                col1, col2, col3 = st.columns(
                    [0.10, 0.65, 0.25]
                )

                # ---------------------------------------------
                # FILE ICON
                # ---------------------------------------------

                with col1:

                    st.markdown(
                        f"## {file_icon(document.file_type)}"
                    )

                # ---------------------------------------------
                # DOCUMENT INFORMATION
                # ---------------------------------------------

                with col2:

                    st.markdown(
                        f"### {document.original_filename}"
                    )

                    st.caption(
                        f"{document.file_type.upper()} · "
                        f"{format_file_size(document.file_size)}"
                    )

                    status_message(
                        document.extraction_status
                    )

                # ---------------------------------------------
                # ACTIONS
                # ---------------------------------------------

                with col3:

                    if st.button(
                        "👁️ Preview Text",
                        key=f"preview_{document.id}",
                        use_container_width=True,
                    ):

                        st.session_state[
                            f"show_text_{document.id}"
                        ] = not st.session_state.get(
                            f"show_text_{document.id}",
                            False,
                        )

                    if document.extraction_status == "completed":

                        if st.button(
                            "🧩 Create Chunks",
                            key=f"chunk_{document.id}",
                            use_container_width=True,
                        ):

                            try:

                                with st.spinner(
                                    "Creating chunks..."
                                ):

                                    chunks = process_document_chunks(
                                        db=db,
                                        document=document,
                                        user_id=user_id,
                                    )

                                st.success(
                                    f"{len(chunks)} chunks created.",
                                    icon="✅",
                                )

                                st.session_state[
                                    f"show_chunks_{document.id}"
                                ] = True

                            except Exception as error:

                                st.error(
                                    f"Chunking failed: {error}",
                                    icon="❌",
                                )

                    if st.button(
                        "🗑️ Delete",
                        key=f"delete_{document.id}",
                        use_container_width=True,
                    ):

                        deleted = delete_document(
                            db=db,
                            user_id=user_id,
                            document_id=document.id,
                        )

                        if deleted:

                            st.success(
                                "Document deleted.",
                                icon="✅",
                            )

                            st.rerun()

                        else:

                            st.error(
                                "Document could not be deleted.",
                                icon="❌",
                            )

                # ---------------------------------------------
                # EXTRACTED TEXT PREVIEW
                # ---------------------------------------------

                if st.session_state.get(
                    f"show_text_{document.id}",
                    False,
                ):

                    st.divider()

                    st.markdown(
                        "#### Extracted Text"
                    )

                    render_text_preview(
                        document
                    )

                # ---------------------------------------------
                # CHUNK PREVIEW
                # ---------------------------------------------

                if st.session_state.get(
                    f"show_chunks_{document.id}",
                    False,
                ):

                    st.divider()

                    st.markdown(
                        "#### Document Chunks"
                    )

                    render_chunk_preview(
                        db=db,
                        document=document,
                        user_id=user_id,
                    )

        render_footer()

    finally:

        db.close()
