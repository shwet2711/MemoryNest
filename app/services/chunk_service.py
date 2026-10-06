
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.services.text_processor import create_chunks


CHUNK_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "chunks"
)

CHUNK_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def read_extracted_text(
    document: Document,
) -> str:
    """Read the extracted text associated with a document."""

    if not document.extracted_text_path:
        return ""

    text_path = Path(
        document.extracted_text_path
    )

    if not text_path.exists():
        return ""

    return text_path.read_text(
        encoding="utf-8"
    )


def save_chunks_to_file(
    document: Document,
    chunks: list[str],
) -> Path:
    """Save generated chunks for debugging and inspection."""

    output_path = (
        CHUNK_OUTPUT_DIR
        / f"document_{document.id}_chunks.txt"
    )

    sections = []

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        sections.append(
            f"===== CHUNK {index} =====\n\n"
            f"{chunk}\n"
        )

    output_path.write_text(
        "\n".join(sections),
        encoding="utf-8",
    )

    return output_path


def delete_existing_chunks(
    db: Session,
    document_id: int,
    user_id: int,
) -> None:
    """Delete existing chunks for a document."""

    existing_chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id
            == document_id,
            DocumentChunk.user_id
            == user_id,
        )
        .all()
    )

    for chunk in existing_chunks:
        db.delete(chunk)

    db.flush()


def process_document_chunks(
    db: Session,
    document: Document,
    user_id: int,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[DocumentChunk]:
    """
    Process extracted text into chunks.

    Page number is currently unavailable for DOCX/TXT
    documents and is therefore stored as None.

    PDF page-aware chunking will be introduced with
    the next retrieval-oriented processing stage.
    """

    if document.user_id != user_id:

        raise ValueError(
            "You do not have access to this document."
        )

    text = read_extracted_text(
        document
    )

    if not text.strip():

        raise ValueError(
            "No extracted text is available "
            "for this document."
        )

    chunks = create_chunks(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not chunks:

        raise ValueError(
            "No usable chunks could be created."
        )

    delete_existing_chunks(
        db=db,
        document_id=document.id,
        user_id=user_id,
    )

    chunk_records = []

    for index, content in enumerate(
        chunks,
        start=0,
    ):

        record = DocumentChunk(
            document_id=document.id,
            user_id=user_id,
            chunk_index=index,
            source_filename=document.original_filename,
            file_type=document.file_type,
            page_number=None,
            extraction_method="text",
            content=content,
            character_count=len(content),
        )

        db.add(record)

        chunk_records.append(
            record
        )

    save_chunks_to_file(
        document=document,
        chunks=chunks,
    )

    db.commit()

    for record in chunk_records:
        db.refresh(record)

    return chunk_records


def get_document_chunks(
    db: Session,
    document_id: int,
    user_id: int,
) -> list[DocumentChunk]:
    """Return all chunks for a user's document."""

    return (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id
            == document_id,
            DocumentChunk.user_id
            == user_id,
        )
        .order_by(
            DocumentChunk.chunk_index.asc()
        )
        .all()
    )


def delete_document_chunks(
    db: Session,
    document_id: int,
    user_id: int,
) -> int:
    """Delete all chunks belonging to a document."""

    chunks = get_document_chunks(
        db=db,
        document_id=document_id,
        user_id=user_id,
    )

    count = len(chunks)

    for chunk in chunks:
        db.delete(chunk)

    db.commit()

    return count
