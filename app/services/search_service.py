
from __future__ import annotations

from app.services.retrieval_service import retrieve_chunks


def semantic_search(
    query: str,
    user_id: int,
    top_k: int = 5,
    document_id: int | None = None,
) -> list[dict]:
    """Backward-compatible semantic search interface."""

    return retrieve_chunks(
        query=query,
        user_id=user_id,
        top_k=top_k,
        document_id=document_id,
    )