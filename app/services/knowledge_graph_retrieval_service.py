from __future__ import annotations

import re
from typing import Any

from app.services.knowledge_graph_service import (
    get_user_knowledge_graph,
)


def _entity_is_mentioned(entity_name: str, query: str) -> bool:
    """Check whether an entity name occurs as a whole phrase in a query."""
    name = entity_name.strip()
    if not name:
        return False

    pattern = (
        r"(?<!\w)"
        + re.escape(name)
        + r"(?!\w)"
    )
    return re.search(pattern, query, flags=re.IGNORECASE) is not None


def retrieve_graph_context(
    *,
    user_id: int,
    query: str,
    document_id: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """
    Retrieve graph relationships relevant to an explicit entity mention.

    Graph results are supplementary evidence. This function does not
    decide whether an answer is sufficiently grounded.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    if document_id is not None:
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise ValueError("document_id must be a positive integer.")

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer.")

    clean_query = query.strip()

    try:
        relationships = get_user_knowledge_graph(user_id=user_id)
    except Exception:
        # The optional graph must not break ordinary vector-based chat.
        return {
            "available": False,
            "relationships": [],
            "context": "",
            "sources": [],
        }

    relevant: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        if document_id is not None:
            if relationship.get("document_id") != document_id:
                continue

        subject = str(relationship.get("subject") or "").strip()
        obj = str(relationship.get("object") or "").strip()

        if not (
            _entity_is_mentioned(subject, clean_query)
            or _entity_is_mentioned(obj, clean_query)
        ):
            continue

        key = (
            subject.casefold(),
            str(relationship.get("relationship") or "").casefold(),
            obj.casefold(),
            relationship.get("document_id"),
            relationship.get("chunk_index"),
            relationship.get("source_filename"),
        )

        if key in seen:
            continue

        seen.add(key)
        relevant.append(relationship)

        if len(relevant) >= limit:
            break

    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []

    for index, item in enumerate(relevant, start=1):
        subject = str(item.get("subject") or "Unknown entity")
        relation = str(item.get("relationship") or "related to")
        obj = str(item.get("object") or "Unknown entity")
        filename = str(item.get("source_filename") or "Unknown source")
        chunk_index = item.get("chunk_index")
        source_document_id = item.get("document_id")

        context_parts.append(
            f"[Graph fact {index}]\n"
            f"Fact: {subject} --{relation}--> {obj}\n"
            f"Source file: {filename}\n"
            f"Document ID: {source_document_id}\n"
            f"Chunk: {chunk_index}"
        )

        source = {
            "filename": filename,
            "document_id": source_document_id,
            "chunk_index": chunk_index,
            "evidence_type": "knowledge_graph",
        }

        if source not in sources:
            sources.append(source)

    return {
        "available": True,
        "relationships": relevant,
        "context": "\n\n".join(context_parts),
        "sources": sources,
    }
