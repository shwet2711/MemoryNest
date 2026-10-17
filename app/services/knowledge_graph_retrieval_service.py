
from __future__ import annotations

import re
from typing import Any

from app.services.knowledge_graph_service import (
    get_user_knowledge_graph,
)


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by",
    "can", "could", "did", "do", "does", "for", "from",
    "how", "i", "in", "into", "is", "it", "me", "of",
    "on", "or", "please", "show", "tell", "that", "the",
    "their", "this", "to", "use", "used", "using", "was",
    "what", "when", "where", "which", "who", "why", "with",
    "would",
}


def _entity_is_mentioned(entity_name: str, query: str) -> bool:
    """Check whether an entity name occurs as a whole phrase."""
    name = entity_name.strip()

    if not name:
        return False

    pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"

    return (
        re.search(pattern, query, flags=re.IGNORECASE)
        is not None
    )


def _query_terms(query: str) -> set[str]:
    """Extract meaningful query terms for relevance ranking."""
    terms = re.findall(r"\b[\w-]+\b", query.casefold())

    return {
        term
        for term in terms
        if len(term) > 2 and term not in STOP_WORDS
    }


def _relationship_relevance_score(
    relationship: dict[str, Any],
    query: str,
    query_terms: set[str],
) -> int:
    """
    Rank a graph fact using explicit entity mentions and term overlap.

    This score orders supplementary graph facts. It is not a
    confidence score and must not replace vector-grounding checks.
    """
    subject = str(relationship.get("subject") or "").strip()
    relation = str(relationship.get("relationship") or "").strip()
    obj = str(relationship.get("object") or "").strip()

    score = 0

    # Explicit entity mentions are the main relevance signal.
    if _entity_is_mentioned(subject, query):
        score += 5

    if _entity_is_mentioned(obj, query):
        score += 5

    # Give additional weight to meaningful terms in the fact.
    fact_terms = set(
        re.findall(
            r"\b[\w-]+\b",
            f"{subject} {relation} {obj}".casefold(),
        )
    )

    score += 2 * len(query_terms.intersection(fact_terms))

    return score


def retrieve_graph_context(
    *,
    user_id: int,
    query: str,
    document_id: int | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """
    Retrieve and rank graph relationships relevant to explicit
    entity mentions.

    Graph results are supplementary evidence. This function does
    not decide whether an answer is sufficiently grounded.
    """
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise ValueError("user_id must be a positive integer.")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    if document_id is not None:
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise ValueError(
                "document_id must be a positive integer."
            )

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit <= 0
    ):
        raise ValueError("limit must be a positive integer.")

    clean_query = query.strip()
    query_terms = _query_terms(clean_query)

    try:
        relationships = get_user_knowledge_graph(
            user_id=user_id
        )
    except Exception:
        # Neo4j must remain optional; vector retrieval can still work.
        return {
            "available": False,
            "relationships": [],
            "context": "",
            "sources": [],
        }

    # Keep the original position as a stable tie-breaker.
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()

    for position, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            continue

        if (
            document_id is not None
            and relationship.get("document_id") != document_id
        ):
            continue

        subject = str(
            relationship.get("subject") or ""
        ).strip()

        obj = str(
            relationship.get("object") or ""
        ).strip()

        # Preserve conservative matching: at least one entity must
        # be explicitly mentioned in the user's query.
        if not (
            _entity_is_mentioned(subject, clean_query)
            or _entity_is_mentioned(obj, clean_query)
        ):
            continue

        key = (
            subject.casefold(),
            str(
                relationship.get("relationship") or ""
            ).casefold(),
            obj.casefold(),
            relationship.get("document_id"),
            relationship.get("chunk_index"),
            relationship.get("source_filename"),
        )

        if key in seen:
            continue

        seen.add(key)

        score = _relationship_relevance_score(
            relationship,
            clean_query,
            query_terms,
        )

        candidates.append((score, position, relationship))

    # Higher relevance first; preserve original order for equal scores.
    candidates.sort(key=lambda item: (-item[0], item[1]))

    relevant = [
        relationship
        for _, _, relationship in candidates[:limit]
    ]

    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[Any, ...]] = set()

    for index, item in enumerate(relevant, start=1):
        subject = str(
            item.get("subject") or "Unknown entity"
        )
        relation = str(
            item.get("relationship") or "related to"
        )
        obj = str(
            item.get("object") or "Unknown entity"
        )
        filename = str(
            item.get("source_filename") or "Unknown source"
        )
        chunk_index = item.get("chunk_index")
        source_document_id = item.get("document_id")

        context_parts.append(
            f"[Graph fact {index}]\n"
            f"Fact: {subject} --{relation}--> {obj}\n"
            f"Source file: {filename}\n"
            f"Document ID: {source_document_id}\n"
            f"Chunk: {chunk_index}"
        )

        source_key = (
            filename,
            source_document_id,
            chunk_index,
        )

        if source_key not in seen_sources:
            seen_sources.add(source_key)

            sources.append(
                {
                    "filename": filename,
                    "document_id": source_document_id,
                    "chunk_index": chunk_index,
                    "evidence_type": "knowledge_graph",
                }
            )

    return {
        "available": True,
        "relationships": relevant,
        "context": "\n\n".join(context_parts),
        "sources": sources,
    }
