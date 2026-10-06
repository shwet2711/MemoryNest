from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.document_model import Document
from app.db.session import SessionLocal
from app.services.answer_service import (
    generate_with_ollama,
    get_ollama_model,
    is_ollama_available,
)


DEFAULT_MAX_TEXT_LENGTH = 8000
DEFAULT_SUMMARY_MAX_TOKENS = 256

SUMMARY_SYSTEM_PROMPT = """
You are MemoryNest, a personal knowledge assistant.

Your task is to summarize a user's stored document accurately.

Rules:
1. Use only the supplied document text.
2. Do not invent information.
3. Do not add facts that are not present in the document.
4. Keep the summary clear and easy to understand.
5. Highlight the main purpose, important ideas, objectives,
   technologies, findings, or conclusions when they are present.
6. Use short sections and bullet points where useful.
7. If some information is unclear, do not guess.
"""


def _validate_user_id(user_id: int) -> None:
    """Validate a MemoryNest user ID."""

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(
            "user_id must be a positive integer."
        )


def _validate_document_id(document_id: int) -> None:
    """Validate a document ID."""

    if (
        not isinstance(document_id, int)
        or document_id <= 0
    ):
        raise ValueError(
            "document_id must be a positive integer."
        )


def get_user_document(
    *,
    user_id: int,
    document_id: int,
) -> dict[str, Any]:
    """
    Get a document only when it belongs to the current user.
    """

    _validate_user_id(user_id)
    _validate_document_id(document_id)

    db = SessionLocal()

    try:
        statement = (
            select(Document)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )

        document = db.scalar(statement)

        if document is None:
            raise ValueError(
                "The selected document is not available "
                "to this user."
            )

        return {
            "id": document.id,
            "filename": document.original_filename,
            "file_path": document.file_path,
            "extracted_text_path": (
                document.extracted_text_path
            ),
            "extraction_status": (
                document.extraction_status
            ),
            "title": document.title,
        }

    finally:
        db.close()


def read_extracted_text(
    extracted_text_path: str,
) -> str:
    """
    Read text previously extracted from a document.
    """

    if not isinstance(
        extracted_text_path,
        str,
    ):
        raise ValueError(
            "extracted_text_path must be a string."
        )

    path = Path(
        extracted_text_path
    )

    if not path.exists():
        raise FileNotFoundError(
            "The extracted text file was not found."
        )

    if not path.is_file():
        raise ValueError(
            "The extracted text path is not a file."
        )

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    ).strip()

    if not text:
        raise ValueError(
            "The extracted document text is empty."
        )

    return text


def build_summary_prompt(
    *,
    filename: str,
    document_text: str,
) -> str:
    """
    Build the prompt used by Ollama for document summarization.
    """

    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(
            "filename must be a non-empty string."
        )

    if not isinstance(document_text, str):
        raise ValueError(
            "document_text must be a string."
        )

    if not document_text.strip():
        raise ValueError(
            "document_text cannot be empty."
        )

    return (
        "Summarize the following document.\n\n"
        f"Document name: {filename.strip()}\n\n"
        "DOCUMENT CONTENT:\n"
        "-----------------\n"
        f"{document_text.strip()}\n"
        "-----------------\n\n"
        "Create a concise but useful summary for the "
        "document owner."
    )


def summarize_document(
    *,
    user_id: int,
    document_id: int,
    max_text_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> dict[str, Any]:
    """
    Generate an AI summary for one user's document.

    Flow:

        user_id + document_id
                ↓
        ownership validation
                ↓
        extracted text
                ↓
        Ollama
                ↓
        summary
    """

    _validate_user_id(user_id)
    _validate_document_id(document_id)

    if (
        not isinstance(max_text_length, int)
        or max_text_length < 1000
    ):
        raise ValueError(
            "max_text_length must be at least 1000."
        )

    document = get_user_document(
        user_id=user_id,
        document_id=document_id,
    )

    extraction_status = (
        document["extraction_status"]
    )

    if extraction_status != "completed":
        raise ValueError(
            "This document has not finished text extraction."
        )

    extracted_text_path = (
        document["extracted_text_path"]
    )

    if not extracted_text_path:
        raise ValueError(
            "No extracted text is available for this document."
        )

    document_text = read_extracted_text(
        extracted_text_path
    )

    original_text_length = len(
        document_text
    )

    # Keep the prompt within a reasonable context size
    # for the local 3B model currently used by MemoryNest.
    truncated = False

    if len(document_text) > max_text_length:
        document_text = document_text[
            :max_text_length
        ]
        truncated = True

    if not is_ollama_available():
        return {
            "document_id": document["id"],
            "filename": document["filename"],
            "summary": (
                "The document was successfully processed, "
                "but the local Ollama service is currently "
                "unavailable. Start Ollama and try again."
            ),
            "mode": "unavailable",
            "ollama_available": False,
            "text_length": original_text_length,
            "summarized_text_length": len(
                document_text
            ),
            "truncated": truncated,
            "model": get_ollama_model(),
        }

    prompt = build_summary_prompt(
        filename=document["filename"],
        document_text=document_text,
    )

    summary = generate_with_ollama(
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        user_prompt=prompt,
        timeout=180,
        num_predict=DEFAULT_SUMMARY_MAX_TOKENS,
    )

    return {
        "document_id": document["id"],
        "filename": document["filename"],
        "summary": summary,
        "mode": "ollama",
        "ollama_available": True,
        "text_length": original_text_length,
        "summarized_text_length": len(
            document_text
        ),
        "truncated": truncated,
        "model": get_ollama_model(),
    }