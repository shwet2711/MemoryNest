
from __future__ import annotations

from typing import Any

from app.services.retrieval_service import retrieve_chunks


DEFAULT_TOP_K = 5


def retrieve_context(
    *,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    document_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve relevant document chunks for a user's query.

    This function is intentionally LLM-independent.
    It can be used whether Ollama is available or not.
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

    results = retrieve_chunks(
        user_id=user_id,
        query=query.strip(),
        top_k=top_k,
        document_id=document_id,
    )

    return results


def build_context(
    results: list[dict[str, Any]],
) -> str:
    """
    Convert retrieved chunks into a context block for an LLM.
    """

    if not results:
        return ""

    context_parts: list[str] = []

    for index, result in enumerate(
        results,
        start=1,
    ):
        metadata = result.get("metadata") or {}

        source = metadata.get(
            "source_filename",
            "Unknown source",
        )

        chunk_index = metadata.get(
            "chunk_index",
            "Unknown",
        )

        content = str(
            result.get(
                "content",
                "",
            )
        ).strip()

        if not content:
            continue

        context_parts.append(
            f"[Source {index}]\n"
            f"File: {source}\n"
            f"Chunk: {chunk_index}\n"
            f"Content:\n{content}"
        )

    return "\n\n".join(context_parts)


def get_rag_context(
    *,
    user_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    document_id: int | None = None,
) -> dict[str, Any]:
    """
    Complete retrieval step for RAG.

    Returns both the raw results and the formatted context.
    """

    results = retrieve_context(
        user_id=user_id,
        query=query,
        top_k=top_k,
        document_id=document_id,
    )

    context = build_context(results)

    return {
        "query": query.strip(),
        "results": results,
        "context": context,
        "has_context": bool(context),
    }
