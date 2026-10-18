
from __future__ import annotations

from typing import Any

from app.services.knowledge_graph_retrieval_service import (
    retrieve_graph_context,
)
from app.services.retrieval_service import retrieve_chunks


RRF_CONSTANT = 60


def _reciprocal_rank(rank: int) -> float:
    """Convert a one-based result rank into an RRF score."""
    return 1.0 / (RRF_CONSTANT + rank)


def _clean_text(value: Any) -> str:
    """Convert a value to stripped text safely."""
    return str(value or "").strip()


def _vector_key(result: dict[str, Any]) -> tuple[str, Any, Any]:
    """Build a deduplication key for a vector result."""
    metadata = result.get("metadata") or {}

    return (
        _clean_text(result.get("content")).casefold(),
        metadata.get("document_id"),
        metadata.get("chunk_index"),
    )


def _graph_key(result: dict[str, Any]) -> tuple[str, str, str, Any]:
    """Build a deduplication key for a Knowledge Graph fact."""
    return (
        _clean_text(result.get("subject")).casefold(),
        _clean_text(result.get("relationship")).casefold(),
        _clean_text(result.get("object")).casefold(),
        result.get("document_id"),
    )


def retrieve_hybrid_context(
    *,
    user_id: int,
    query: str,
    top_k: int = 5,
    document_id: int | None = None,
    graph_limit: int = 8,
    vector_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Retrieve and fuse vector passages with Knowledge Graph facts.

    Vector retrieval remains the source of semantic passage evidence.
    Graph facts are supplementary evidence and must not bypass existing
    RAG grounding checks.

    Reciprocal Rank Fusion (RRF) combines rankings without comparing
    graph scores directly with Chroma vector distances.

    If the Knowledge Graph is unavailable, vector results can still
    be returned.

    Args:
        user_id: ID of the authenticated user.
        query: User's search query.
        top_k: Maximum number of vector results to retrieve when needed.
        document_id: Optional document scope.
        graph_limit: Maximum number of graph facts to retrieve.
        vector_results: Previously retrieved vector results to reuse.
            When None, vector retrieval is performed by this function.

    Returns:
        A dictionary containing fused results, context, sources,
        retrieval counts, and Knowledge Graph availability.
    """
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k <= 0
    ):
        raise ValueError("top_k must be a positive integer.")

    if document_id is not None:
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise ValueError("document_id must be a positive integer.")

    if (
        isinstance(graph_limit, bool)
        or not isinstance(graph_limit, int)
        or graph_limit <= 0
    ):
        raise ValueError("graph_limit must be a positive integer.")

    clean_query = query.strip()

    # Reuse vector results when the caller has already retrieved them.
    # Otherwise, perform normal vector retrieval.
    if vector_results is None:
        vector_results = retrieve_chunks(
            query=clean_query,
            user_id=user_id,
            top_k=top_k,
            document_id=document_id,
        )

    # Knowledge Graph retrieval is supplementary and optional.
    # An unexpected graph error must not break vector retrieval.
    try:
        graph_data = retrieve_graph_context(
            user_id=user_id,
            query=clean_query,
            document_id=document_id,
            limit=graph_limit,
        )
    except Exception:
        graph_data = {
            "available": False,
            "relationships": [],
            "context": "",
            "sources": [],
        }

    if not isinstance(vector_results, list):
        vector_results = []

    if not isinstance(graph_data, dict):
        graph_data = {
            "available": False,
            "relationships": [],
            "context": "",
            "sources": [],
        }

    relationships = graph_data.get("relationships", [])

    if not isinstance(relationships, list):
        relationships = []

    # Build ranked candidates from both retrieval channels.
    # RRF combines channel ranks instead of comparing unlike scores.
    candidates: list[dict[str, Any]] = []

    seen_vectors: set[tuple[str, Any, Any]] = set()
    seen_graph_facts: set[tuple[str, str, str, Any]] = set()

    # Add vector evidence.
    for rank, item in enumerate(vector_results, start=1):
        if not isinstance(item, dict):
            continue

        content = _clean_text(item.get("content"))

        if not content:
            continue

        metadata = item.get("metadata") or {}

        if not isinstance(metadata, dict):
            metadata = {}

        result_document_id = metadata.get("document_id")

        # Enforce document scope when one is requested.
        if (
            document_id is not None
            and result_document_id != document_id
        ):
            continue

        key = _vector_key(item)

        if key in seen_vectors:
            continue

        seen_vectors.add(key)

        candidates.append(
            {
                "evidence_type": "vector",
                "content": content,
                "metadata": metadata,
                "distance": item.get("distance"),
                "vector_id": item.get("vector_id"),
                "rrf_score": _reciprocal_rank(rank),
                "channel_rank": rank,
                "channel_order": 0,
            }
        )

    # Add Knowledge Graph evidence.
    for rank, relationship in enumerate(relationships, start=1):
        if not isinstance(relationship, dict):
            continue

        result_document_id = relationship.get("document_id")

        # Enforce document scope for graph facts as well.
        if (
            document_id is not None
            and result_document_id != document_id
        ):
            continue

        subject = _clean_text(relationship.get("subject"))
        relation = _clean_text(relationship.get("relationship"))
        obj = _clean_text(relationship.get("object"))

        if not subject or not relation or not obj:
            continue

        key = _graph_key(relationship)

        if key in seen_graph_facts:
            continue

        seen_graph_facts.add(key)

        metadata = {
            "source_filename": relationship.get("source_filename"),
            "document_id": result_document_id,
            "chunk_index": relationship.get("chunk_index"),
            "evidence_type": "knowledge_graph",
        }

        candidates.append(
            {
                "evidence_type": "knowledge_graph",
                "content": f"{subject} --{relation}--> {obj}",
                "metadata": metadata,
                "distance": None,
                "vector_id": None,
                "subject": subject,
                "relationship": relation,
                "object": obj,
                "rrf_score": _reciprocal_rank(rank),
                "channel_rank": rank,
                "channel_order": 1,
            }
        )

    # Highest RRF score first.
    # Prefer vector evidence when scores are exactly tied.
    candidates.sort(
        key=lambda item: (
            -item["rrf_score"],
            item["channel_order"],
            item["channel_rank"],
        )
    )

    # Retain the requested vector capacity plus graph capacity.
    fused_results = candidates[: top_k + graph_limit]

    # Build source-aware context and source metadata.
    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[Any, ...]] = set()

    for index, item in enumerate(fused_results, start=1):
        metadata = item["metadata"]

        filename = (
            metadata.get("source_filename")
            or "Unknown source"
        )
        source_document_id = metadata.get("document_id")
        chunk_index = metadata.get("chunk_index")

        context_parts.append(
            f"[Evidence {index} — {item['evidence_type']}]\n"
            f"File: {filename}\n"
            f"Document ID: {source_document_id}\n"
            f"Chunk: {chunk_index}\n"
            f"Content:\n{item['content']}"
        )

        source_key = (
            filename,
            source_document_id,
            chunk_index,
            item["evidence_type"],
        )

        if source_key not in seen_sources:
            seen_sources.add(source_key)

            sources.append(
                {
                    "filename": filename,
                    "document_id": source_document_id,
                    "chunk_index": chunk_index,
                    "evidence_type": item["evidence_type"],
                }
            )

    return {
        "query": clean_query,
        "document_id": document_id,
        "top_k": top_k,
        "results": fused_results,
        "context": "\n\n".join(context_parts),
        "sources": sources,
        "vector_count": sum(
            item["evidence_type"] == "vector"
            for item in fused_results
        ),
        "graph_count": sum(
            item["evidence_type"] == "knowledge_graph"
            for item in fused_results
        ),
        "graph_available": bool(
            graph_data.get("available", False)
        ),
        "has_context": bool(context_parts),
    }
