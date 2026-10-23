from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
import streamlit as st

from app.db.session import SessionLocal
from app.services.chunk_service import process_document_chunks
from app.services.document_service import (
    EXTRACTED_DIR,
    UPLOAD_DIR,
    create_document,
    delete_document,
    get_user_documents,
)
from app.services.event_service import scan_document_for_events
from app.services.indexing_service import index_document

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = ["pdf", "docx", "txt", "jpg", "jpeg", "png"]


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _file_icon(file_type: str) -> str:
    return {
        "pdf": "📕",
        "docx": "📘",
        "txt": "📄",
        "jpg": "🖼️",
        "jpeg": "🖼️",
        "png": "🖼️",
    }.get(file_type.lower(), "📄")


def _safe_stored_path(
    path_value: str | None,
    root: Path,
) -> Path | None:
    """Return a stored path only if it stays inside its expected directory."""
    if not path_value:
        return None

    try:
        root_path = root.resolve()
        candidate = Path(path_value).resolve()

        if not candidate.is_relative_to(root_path):
            return None

        if not candidate.is_file():
            return None

        return candidate

    except (OSError, ValueError, RuntimeError):
        return None


def _read_extracted_text(document) -> str | None:
    path = _safe_stored_path(
        document.extracted_text_path,
        EXTRACTED_DIR,
    )

    if path is None:
        return None

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()

        return text or None

    except OSError:
        logger.exception(
            "Could not read extracted text for document %s",
            document.id,
        )
        return None


def _convert_docx_to_pdf(docx_path: Path) -> bytes | None:
    """
    Convert a DOCX file to PDF locally using LibreOffice.

    The generated PDF is temporary and is not stored in the document library.
    """
    candidates = [
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]

    soffice_path = next(
        (
            Path(candidate)
            for candidate in candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )

    if soffice_path is None:
        logger.error("LibreOffice executable was not found.")
        return None

    try:
        with tempfile.TemporaryDirectory(
            prefix="memorynest_preview_"
        ) as temp:
            temp_dir = Path(temp)
            profile_dir = temp_dir / "lo_profile"
            profile_dir.mkdir()

            command = [
                str(soffice_path),
                "--headless",
                f"-env:UserInstallation={profile_dir.as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(docx_path),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                shell=False,
            )

            pdf_path = temp_dir / f"{docx_path.stem}.pdf"

            if result.returncode != 0 or not pdf_path.is_file():
                logger.error(
                    "DOCX conversion failed. Exit code: %s; "
                    "stdout: %s; stderr: %s",
                    result.returncode,
                    result.stdout[-2000:],
                    result.stderr[-2000:],
                )
                return None

            return pdf_path.read_bytes()

    except subprocess.TimeoutExpired:
        logger.warning(
            "DOCX conversion timed out: %s",
            docx_path.name,
        )

    except OSError:
        logger.exception(
            "Could not convert DOCX: %s",
            docx_path.name,
        )

    return None


def _render_pdf_pages(
    pdf_bytes: bytes,
    document_id: int,
    label: str,
    scale: float = 1.25,
) -> None:
    """Render PDF pages as images while preserving their page layout."""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            page_count = len(pdf)

            st.caption(f"{label} · {page_count} page(s)")

            if page_count == 0:
                st.info("This document contains no pages.")
                return

            max_pages = min(page_count, 20)

            for page_index in range(max_pages):
                page = pdf.load_page(page_index)

                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    alpha=False,
                )

                with st.expander(
                    f"Page {page_index + 1} of {page_count}",
                    expanded=(page_index == 0),
                ):
                    st.image(
                        pixmap.tobytes("png"),
                        use_container_width=True,
                    )

            if page_count > max_pages:
                st.info(
                    f"Preview limited to the first {max_pages} pages. "
                    "Download the original to view the remaining pages."
                )

    except Exception:
        logger.exception(
            "Could not render PDF preview for document %s",
            document_id,
        )
        st.warning(
            "The page preview failed. You can still download the original."
        )


def _render_original_file(document) -> None:
    """Preview supported original files inside MemoryNest."""
    path = _safe_stored_path(
        document.file_path,
        UPLOAD_DIR,
    )

    if path is None:
        st.error(
            "The original file is missing or its storage path is invalid."
        )
        return

    try:
        file_bytes = path.read_bytes()

    except OSError:
        logger.exception(
            "Could not read original document %s",
            document.id,
        )
        st.error("Unable to read the original file.")
        return

    file_type = document.file_type.lower().lstrip(".")

    mime_types = {
        "pdf": "application/pdf",
        "docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        "txt": "text/plain",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }

    st.download_button(
        "⬇️ Download original file",
        data=file_bytes,
        file_name=document.original_filename,
        mime=mime_types.get(
            file_type,
            "application/octet-stream",
        ),
        key=f"memory_download_{document.id}",
        use_container_width=True,
    )

    st.divider()

    # IMAGE PREVIEW
    if file_type in {"jpg", "jpeg", "png"}:
        try:
            st.image(
                file_bytes,
                caption=document.original_filename,
                use_container_width=True,
            )
        except Exception:
            logger.exception(
                "Could not preview image document %s",
                document.id,
            )
            st.warning(
                "The image preview failed. "
                "You can still download the original."
            )

        return

    # PDF PREVIEW
    if file_type == "pdf":
        _render_pdf_pages(
            pdf_bytes=file_bytes,
            document_id=document.id,
            label="PDF document",
            scale=1.25,
        )
        return

    # TEXT FILE PREVIEW
    if file_type == "txt":
        text = file_bytes.decode(
            "utf-8-sig",
            errors="replace",
        )

        st.caption("Text file · Original file content")

        st.text_area(
            "File content",
            value=text,
            height=500,
            disabled=True,
            key=f"memory_original_txt_{document.id}",
        )
        return

    # WORD DOCUMENT PREVIEW
    # Convert DOCX to PDF locally to preserve its page layout.
    if file_type == "docx":
        st.caption(
            "Word document · Original-layout preview"
        )

        with st.spinner(
            "Preparing the Word document preview..."
        ):
            pdf_bytes = _convert_docx_to_pdf(path)

        if pdf_bytes is None:
            st.warning(
                "The Word layout preview could not be generated. "
                "Check that LibreOffice is installed and available. "
                "You can still download the original DOCX file."
            )
            return

        _render_pdf_pages(
            pdf_bytes=pdf_bytes,
            document_id=document.id,
            label="Word document layout preview",
            scale=1.5,
        )
        return

    st.info("Preview is not available for this file type.")


def _upload_documents(user_id: int, uploaded_files) -> None:
    db = SessionLocal()
    successful = 0
    failed = 0

    progress = st.progress(
        0,
        text="Preparing documents...",
    )

    try:
        total = len(uploaded_files)

        for index, uploaded_file in enumerate(
            uploaded_files,
            start=1,
        ):
            progress.progress(
                int((index - 1) / total * 100),
                text=f"Processing {uploaded_file.name}...",
            )

            try:
                document = create_document(
                    db=db,
                    user_id=user_id,
                    filename=uploaded_file.name,
                    file_bytes=uploaded_file.getvalue(),
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

                if (
                    document.extraction_status == "completed"
                    and document.extracted_text_path
                    and Path(document.extracted_text_path).is_file()
                ):
                    try:
                        events = scan_document_for_events(
                            db=db,
                            user_id=user_id,
                            document_id=document.id,
                        )

                        if events:
                            st.info(
                                f"{uploaded_file.name}: "
                                f"{len(events)} event(s) detected. "
                                "Review them on the Events page."
                            )

                    except Exception:
                        logger.exception(
                            "Event detection failed for document %s",
                            document.id,
                        )
                        st.warning(
                            f"{uploaded_file.name} was uploaded, "
                            "but automatic event detection failed."
                        )

                successful += 1
                st.success(
                    f"Uploaded and processed: {uploaded_file.name}"
                )

            except Exception as exc:
                failed += 1

                logger.exception(
                    "Failed to process %s for user %s",
                    uploaded_file.name,
                    user_id,
                )

                st.error(f"{uploaded_file.name}: {exc}")

        progress.progress(
            100,
            text="Upload processing finished.",
        )

    finally:
        db.close()

    if successful:
        st.session_state["knowledge_graph_refresh_requested"] = True

    if successful and not failed:
        st.session_state["memory_uploader_generation"] = (
            st.session_state.get(
                "memory_uploader_generation",
                0,
            )
            + 1
        )
        st.rerun()

    if successful:
        st.success(
            f"{successful} document(s) processed successfully."
        )

    if failed:
        st.warning(
            f"{failed} document(s) could not be processed."
        )


def memories_page() -> None:
    """Render a file-manager-style library for the signed-in user."""
    user_id = st.session_state.get("user_id")

    if not user_id:
        st.error("Please sign in again.")
        return

    st.title("🧠 Memories")

    st.caption(
        "Browse your uploaded files, review their original content, "
        "read extracted text, and manage your personal knowledge library."
    )

    with st.expander(
        "➕ Add documents",
        expanded=False,
    ):
        st.caption(
            "Supported formats: PDF, DOCX, TXT, JPG, JPEG, PNG. "
            "Maximum size: 20 MB per file."
        )

        if "memory_uploader_generation" not in st.session_state:
            st.session_state["memory_uploader_generation"] = 0

        uploaded_files = st.file_uploader(
            "Choose files to add",
            type=SUPPORTED_TYPES,
            accept_multiple_files=True,
            max_upload_size=20,
            key=(
                "memory_uploader_"
                f"{st.session_state['memory_uploader_generation']}"
            ),
        )

        if uploaded_files and st.button(
            "Upload and process selected files",
            type="primary",
            use_container_width=True,
            key="memory_process_uploads",
        ):
            _upload_documents(
                user_id,
                uploaded_files,
            )

    st.divider()
    st.subheader("Your file library")

    db = SessionLocal()

    try:
        documents = get_user_documents(
            db=db,
            user_id=user_id,
        )

        if not documents:
            st.info(
                "Your library is empty. Use Add documents to upload "
                "your first PDF, Word document, text file, or image."
            )
            return

        st.caption(
            f"{len(documents)} file(s) in your personal library"
        )

        query = st.text_input(
            "Find a file by name or type",
            placeholder="Search filenames, e.g. resume or pdf",
            key="memory_library_filter",
        ).strip().casefold()

        filtered = [
            doc
            for doc in documents
            if query in doc.original_filename.casefold()
            or query in doc.file_type.casefold()
        ]

        if not filtered:
            st.info("No files match that search.")
            return

        preferred_id = st.session_state.get(
            "memories_selected_document_id"
        )

        available_ids = [
            doc.id
            for doc in filtered
        ]

        default_index = (
            available_ids.index(preferred_id)
            if preferred_id in available_ids
            else 0
        )
                # Synchronize the selectbox with a document requested by another page.
        if preferred_id in available_ids:
            st.session_state["memory_selected_document"] = preferred_id
        elif (
            st.session_state.get("memory_selected_document")
            not in available_ids
        ):
            st.session_state.pop("memory_selected_document", None)

        selected_id = st.selectbox(
            "Select a file to review",
            options=available_ids,
            index=default_index,
            format_func=lambda doc_id: next(
                (
                    f"{_file_icon(doc.file_type)} "
                    f"{doc.original_filename}"
                    for doc in filtered
                    if doc.id == doc_id
                ),
                f"Document {doc_id}",
            ),
            key="memory_selected_document",
        )

        st.session_state[
            "memories_selected_document_id"
        ] = selected_id

        selected = next(
            doc
            for doc in filtered
            if doc.id == selected_id
        )

        st.divider()

        left, right = st.columns([2, 1])

        with left:
            st.subheader(
                f"{_file_icon(selected.file_type)} "
                f"{selected.original_filename}"
            )

            st.caption(
                f"{selected.file_type.upper()} · "
                f"{_format_size(selected.file_size)} · "
                f"Uploaded "
                f"{selected.created_at:%d %b %Y, %I:%M %p}"
            )

        with right:
            st.metric(
                "Extraction status",
                selected.extraction_status,
            )

            if selected.extraction_method:
                st.caption(
                    f"Extraction method: "
                    f"{selected.extraction_method}"
                )

            if selected.ocr_confidence is not None:
                st.caption(
                    f"OCR confidence: "
                    f"{selected.ocr_confidence:.1f}%"
                )

        tab_original, tab_text, tab_manage = st.tabs(
            [
                "Original file",
                "Readable content",
                "Manage file",
            ]
        )

        with tab_original:
            _render_original_file(selected)

        with tab_text:
            extracted_text = _read_extracted_text(selected)

            if extracted_text:
                st.caption(
                    "This is text extracted from the original file. "
                    "For scanned documents and images, the text comes from OCR."
                )

                st.text_area(
                    "Extracted document content",
                    value=extracted_text,
                    height=450,
                    disabled=True,
                    key=f"memory_text_{selected.id}",
                )

                st.caption(
                    f"{len(extracted_text):,} characters extracted"
                )

            else:
                st.info(
                    "Readable text is not available for this file yet. "
                    "The original file may still be downloaded above."
                )

        with tab_manage:
            st.write(
                "Delete this file and its associated MemoryNest records."
            )

            st.warning(
                "Deletion removes the stored file, extracted text, chunks, "
                "events, vector embeddings, and queues Knowledge Graph cleanup."
            )

            confirm_key = f"confirm_memory_delete_{selected.id}"

            if not st.session_state.get(confirm_key, False):
                if st.button(
                    "🗑️ Delete file",
                    key=f"memory_delete_start_{selected.id}",
                    type="secondary",
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()

            else:
                st.error(
                    f"Are you sure you want to permanently delete "
                    f"{selected.original_filename}?"
                )

                confirm_col, cancel_col = st.columns(2)

                with confirm_col:
                    if st.button(
                        "Confirm delete",
                        key=f"memory_delete_confirm_{selected.id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            deleted = delete_document(
                                db=db,
                                user_id=user_id,
                                document_id=selected.id,
                            )

                            if deleted:
                                st.session_state.pop(
                                    confirm_key,
                                    None,
                                )

                                st.session_state.pop(
                                    "memories_selected_document_id",
                                    None,
                                )

                                st.session_state[
                                    "knowledge_graph_refresh_requested"
                                ] = True

                                st.success("File deleted.")
                                st.rerun()

                            else:
                                st.error(
                                    "The file was not found in your account."
                                )

                        except Exception:
                            logger.exception(
                                "Failed to delete document %s for user %s",
                                selected.id,
                                user_id,
                            )

                            st.error(
                                "Deletion failed. The file has been preserved "
                                "where possible; check the application logs."
                            )

                with cancel_col:
                    if st.button(
                        "Cancel",
                        key=f"memory_delete_cancel_{selected.id}",
                        use_container_width=True,
                    ):
                        st.session_state.pop(
                            confirm_key,
                            None,
                        )
                        st.rerun()

    finally:
        db.close()