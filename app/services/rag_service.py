
from __future__ import annotations

import os
from typing import Any

from app.services.retrieval_service import (
    get_max_distance,
    retrieve_chunks,
)


DEFAULT_TOP_K = 5
DEFAULT_MAX_CONTEXT_CHARS = 12000


def get_max_context_chars() -> int:
    """Return the maximum number of context characters."""

    raw_value = os.getenv(
        "MEMORYNEST_RAG_MAX_CONTEXT_CHARS"
    )

    if raw_value is None:
        return DEFAULT_MAX_CONTEXT_CHARS

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            "MEMORYNEST_RAG_MAX_CONTEXT_CHARS must be an integer."
        ) from exc

    if value < 1000:
        raise ValueError(
            "MEMORYNEST_RAG_MAX_CONTEXT_CHARS must be at least 1000."
        )

    return value


def retrieve_context(
    *,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    document_id: int | None = None,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve relevant document chunks for a user's query.
    """

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(
            "user_id must be a positive integer"
        )

    if not isinstance(query, str) or not query.strip():
        raise ValueError(
            "query must be a non-empty string"
        )

    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError(
            "top_k must be a positive integer"
        )

    if document_id is not None:
        if (
            not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise ValueError(
                "document_id must be a positive integer"
            )

    if max_distance is not None:
        if not isinstance(max_distance, (int, float)):
            raise ValueError(
                "max_distance must be a number"
            )

        if max_distance < 0:
            raise ValueError(
                "max_distance must be non-negative"
            )

    return retrieve_chunks(
        user_id=user_id,
        query=query.strip(),
        top_k=top_k,
        document_id=document_id,
        max_distance=max_distance,
    )


def build_context(
    results: list[dict[str, Any]],
    max_chars: int | None = None,
) -> str:
    """
    Convert retrieved chunks into a bounded context block.
    """

    if not results:
        return ""

    if max_chars is None:
        max_chars = get_max_context_chars()

    if not isinstance(max_chars, int):
        raise ValueError(
            "max_chars must be an integer."
        )

    if max_chars < 1000:
        raise ValueError(
            "max_chars must be at least 1000."
        )

    context_parts: list[str] = []
    current_length = 0

    for index, result in enumerate(
        results,
        start=1,
    ):
        metadata = result.get("metadata") or {}

        source = metadata.get(
            "source_filename",
            "Unknown source",
        )

        page_number = metadata.get(
            "page_number"
        )

        chunk_index = metadata.get(
            "chunk_index",
            "Unknown",
        )

        distance = result.get(
            "distance"
        )

        content = str(
            result.get(
                "content",
                "",
            )
        ).strip()

        if not content:
            continue

        distance_value = (
            f"{float(distance):.4f}"
            if isinstance(distance, (int, float))
            else "Unknown"
        )

        source_block = (
            f"[Source {index}]\n"
            f"File: {source}\n"
        )

        if page_number is not None:
            source_block += (
                f"Page: {page_number}\n"
            )

        source_block += (
            f"Chunk: {chunk_index}\n"
            f"Similarity distance: {distance_value}\n"
            f"Content:\n{content}"
        )

        separator = "\n\n"

        remaining = max_chars - current_length

        if remaining <= 0:
            break

        if context_parts:
            required_length = len(separator)

            if remaining <= required_length:
                break

            current_length += required_length
            remaining -= required_length

        if len(source_block) <= remaining:
            context_parts.append(source_block)
            current_length += len(source_block)
            continue

        truncated = source_block[:remaining].rstrip()

        if truncated:
            context_parts.append(truncated)

        break

    return "\n\n".join(context_parts)


def get_rag_context(
    *,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    document_id: int | None = None,
    max_distance: float | None = None,
) -> dict[str, Any]:
    """
    Complete retrieval step for RAG.

    Returns raw retrieval results, formatted context,
    and retrieval metadata.
    """

    results = retrieve_context(
        user_id=user_id,
        query=query,
        top_k=top_k,
        document_id=document_id,
        max_distance=max_distance,
    )

    context = build_context(results)

    effective_max_distance = (
        get_max_distance()
        if max_distance is None
        else float(max_distance)
    )

    return {
        "query": query.strip(),
        "results": results,
        "context": context,
        "has_context": bool(context),
        "user_id": user_id,
        "document_id": document_id,
        "top_k": top_k,
        "max_distance": effective_max_distance,
    }