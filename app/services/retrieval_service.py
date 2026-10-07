from __future__ import annotations

import os
from typing import Any

from app.services.embedding_service import generate_embedding
from app.services.vector_store import get_collection


DEFAULT_MAX_DISTANCE = 0.70

GENERIC_ABOUT_QUERY = (
    "Describe the main topic, subject, course, document, "
    "or information shown in the uploaded image or document."
)


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


def build_retrieval_query(query: str) -> str:
    """
    Convert generic image, screenshot, and document description
    questions into a retrieval-friendly semantic query.

    The original user query is still used for the final answer.
    This transformation is only used when generating the
    retrieval embedding.
    """

    if not isinstance(query, str):
        raise TypeError("Query must be a string.")

    normalized = " ".join(
        query.strip().lower().split()
    )

    if not normalized:
        raise ValueError("Query cannot be empty.")

    generic_queries = {
        # Image questions
        "what is this image about",
        "what is this image about?",
        "what does this image show",
        "what does this image show?",
        "what information is shown in this image",
        "what information is shown in this image?",
        "what information does this image contain",
        "what information does this image contain?",
        "what is shown in this image",
        "what is shown in this image?",
        "what can you tell me about this image",
        "what can you tell me about this image?",
        "tell me about this image",
        "tell me about this image.",
        "describe this image",
        "describe this image.",
        "describe the image",
        "describe the image.",

        # Screenshot questions
        "what is this screenshot about",
        "what is this screenshot about?",
        "what does this screenshot show",
        "what does this screenshot show?",
        "what information is shown in this screenshot",
        "what information is shown in this screenshot?",
        "what information does this screenshot contain",
        "what information does this screenshot contain?",
        "what is shown in this screenshot",
        "what is shown in this screenshot?",
        "what can you tell me about this screenshot",
        "what can you tell me about this screenshot?",
        "tell me about this screenshot",
        "tell me about this screenshot.",
        "describe this screenshot",
        "describe this screenshot.",

        # Document questions
        "what is this document about",
        "what is this document about?",
        "what does this document show",
        "what does this document show?",
        "what information is shown in this document",
        "what information is shown in this document?",
        "what information does this document contain",
        "what information does this document contain?",
        "what is shown in this document",
        "what is shown in this document?",
        "what can you tell me about this document",
        "what can you tell me about this document?",
        "tell me about this document",
        "tell me about this document.",
        "describe this document",
        "describe this document.",
    }

    if normalized in generic_queries:
        return GENERIC_ABOUT_QUERY

    return query.strip()


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

    retrieval_query = build_retrieval_query(query)

    query_embedding = generate_embedding(
        retrieval_query
    )

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