from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.document_model import Document
from app.db.session import SessionLocal
from app.services.answer_service import answer_query
from app.services.conversation_service import add_message


DEFAULT_TOP_K = 5


def _validate_user_id(user_id: int) -> None:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(
            "user_id must be a positive integer."
        )


def get_chat_documents(
    *,
    user_id: int,
) -> list[dict[str, Any]]:
    _validate_user_id(user_id)

    db = SessionLocal()

    try:
        statement = (
            select(Document)
            .where(
                Document.user_id == user_id
            )
            .order_by(
                Document.original_filename.asc()
            )
        )

        documents = db.scalars(statement).all()

        return [
            {
                "id": document.id,
                "filename": document.original_filename,
                "title": document.title,
                "extraction_status": (
                    document.extraction_status
                ),
            }
            for document in documents
        ]

    finally:
        db.close()


def _validate_document_access(
    *,
    user_id: int,
    document_id: int,
) -> None:
    _validate_user_id(user_id)

    if not isinstance(document_id, int) or document_id < 1:
        raise ValueError(
            "Document ID must be positive."
        )

    db = SessionLocal()

    try:
        statement = (
            select(Document.id)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )

        document_exists = db.scalar(statement)

        if document_exists is None:
            raise ValueError(
                "The selected document is not available "
                "to this user."
            )

    finally:
        db.close()


def chat_with_memorynest(
    *,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    document_id: int | None = None,
) -> dict[str, Any]:
    _validate_user_id(user_id)

    if not isinstance(query, str) or not query.strip():
        raise ValueError(
            "Query cannot be empty."
        )

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError(
            "top_k must be at least 1."
        )

    if document_id is not None:
        _validate_document_access(
            user_id=user_id,
            document_id=document_id,
        )

    return answer_query(
        user_id=user_id,
        query=query.strip(),
        top_k=top_k,
        document_id=document_id,
        use_ollama=True,
    )


def save_chat_exchange(
    *,
    user_id: int,
    conversation_id: int,
    query: str,
    result: dict[str, Any],
    top_k: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = get_source_names(result)

    user_message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=query,
        top_k=top_k,
    )

    assistant_message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=str(
            result.get(
                "answer",
                "",
            )
        ),
        mode=result.get("mode"),
        sources=sources,
        top_k=top_k,
    )

    return (
        user_message,
        assistant_message,
    )


def get_source_names(
    result: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(result, dict):
        return []

    sources = result.get("sources")

    if isinstance(sources, list):
        names: list[str] = []

        for source in sources:
            if isinstance(source, dict):
                filename = source.get(
                    "filename"
                )
            else:
                filename = source

            if filename:
                filename = str(filename)

                if filename not in names:
                    names.append(filename)

        return names

    results = result.get("results")

    if not isinstance(results, list):
        return []

    names = []

    for item in results:
        if not isinstance(item, dict):
            continue

        metadata = item.get(
            "metadata",
            {},
        )

        if not isinstance(metadata, dict):
            continue

        filename = (
            metadata.get(
                "source_filename"
            )
            or metadata.get(
                "original_filename"
            )
        )

        if filename:
            filename = str(filename)

            if filename not in names:
                names.append(filename)

    return names


def get_source_details(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    sources = result.get("sources")

    if isinstance(sources, list):
        normalized: list[dict[str, Any]] = []

        for source in sources:
            if isinstance(source, dict):
                normalized.append(source)

        if normalized:
            return normalized

    results = result.get("results")

    if not isinstance(results, list):
        return []

    details: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        metadata = item.get(
            "metadata",
            {},
        )

        if not isinstance(metadata, dict):
            metadata = {}

        details.append(
            {
                "filename": str(
                    metadata.get(
                        "source_filename",
                        "Unknown source",
                    )
                ),
                "page_number": metadata.get(
                    "page_number"
                ),
                "chunk_index": metadata.get(
                    "chunk_index"
                ),
                "distance": item.get(
                    "distance"
                ),
                "content": item.get(
                    "content",
                    "",
                ),
            }
        )

    return details


def get_retrieved_passages(
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    passages = result.get("results")

    if isinstance(passages, list):
        return passages

    return []