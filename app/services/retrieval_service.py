from __future__ import annotations

import os
from typing import Any

from app.services.embedding_service import generate_embedding
from app.services.vector_store import get_collection


DEFAULT_MAX_DISTANCE = 0.70


def get_max_distance() -> float:
    """
    Return the maximum accepted Chroma cosine distance.

    Lower cosine distance means stronger semantic similarity.
    """
    raw_value = os.getenv(
        "MEMORYNEST_RAG_MAX_DISTANCE",
        str(DEFAULT_MAX_DISTANCE),
    ).strip()

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(
            "MEMORYNEST_RAG_MAX_DISTANCE must be a valid number."
        ) from exc

    if value < 0:
        raise ValueError(
            "MEMORYNEST_RAG_MAX_DISTANCE cannot be negative."
        )

    return value


def _build_where(
    *,
    user_id: int,
    document_id: int | None,
) -> dict[str, Any]:
    """Build a user/document scoped Chroma filter."""
    filters: list[dict[str, Any]] = [
        {"user_id": user_id},
    ]

    if document_id is not None:
        filters.append({"document_id": document_id})

    if len(filters) == 1:
        return filters[0]

    return {"$and": filters}


def retrieve_chunks(
    query: str,
    user_id: int,
    top_k: int = 5,
    document_id: int | None = None,
    max_distance: float | None = None,
) -> list[dict]:
    """
    Retrieve relevant chunks from the current user's knowledge base.

    Results are filtered by semantic distance so weakly related
    chunks are not automatically treated as supporting evidence.
    """
    if not isinstance(query, str):
        raise TypeError("Query must be a string.")

    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty.")

    if user_id < 1:
        raise ValueError("User ID must be positive.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    if document_id is not None and document_id < 1:
        raise ValueError("Document ID must be positive.")

    if max_distance is None:
        max_distance = get_max_distance()

    if max_distance < 0:
        raise ValueError("max_distance cannot be negative.")

    collection = get_collection()

    total = collection.count()

    if total == 0:
        return []

    where = _build_where(
        user_id=user_id,
        document_id=document_id,
    )

    matching = collection.get(
        where=where,
        include=[],
    )

    matching_count = len(matching.get("ids", []))

    if matching_count == 0:
        return []

    query_embedding = generate_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, matching_count),
        where=where,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []
    distances = results.get("distances", [[]])[0] or []
    ids = results.get("ids", [[]])[0] or []

    output: list[dict] = []
    seen_content: set[str] = set()

    for vector_id, content, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):
        numeric_distance = float(distance)

        if numeric_distance > max_distance:
            continue

        clean_content = str(content or "").strip()

        if not clean_content:
            continue

        # Avoid returning the same passage multiple times.
        content_key = clean_content.casefold()

        if content_key in seen_content:
            continue

        seen_content.add(content_key)

        output.append(
            {
                "vector_id": vector_id,
                "content": clean_content,
                "metadata": metadata or {},
                "distance": numeric_distance,
            }
        )

    return output