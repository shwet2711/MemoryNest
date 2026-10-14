from __future__ import annotations

from typing import Any

from app.services.entity_extraction_service import extract_relationships
from app.services.knowledge_graph_service import store_entity_relationships


def _validate_positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def process_chunk_for_knowledge_graph(
    *,
    user_id: int,
    document_id: int,
    chunk_index: int,
    text: str,
    source_filename: str,
) -> dict[str, Any]:
    """Extract relationships from one chunk and store them atomically."""

    user_id = _validate_positive_integer(user_id, "user_id")
    document_id = _validate_positive_integer(document_id, "document_id")

    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
        raise ValueError("chunk_index must be an integer.")
    if chunk_index < 0:
        raise ValueError("chunk_index must be non-negative.")

    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string.")

    if not isinstance(source_filename, str) or not source_filename.strip():
        raise ValueError("source_filename must be a non-empty string.")

    source_filename = source_filename.strip()

    # Extract first. If extraction fails, no graph writes occur.
    relationships = extract_relationships(text)

    # Store all relationships from this chunk in one Neo4j transaction.
    if relationships:
        stored = store_entity_relationships(
            relationships=relationships,
            user_id=user_id,
            document_id=document_id,
            chunk_index=chunk_index,
            source_filename=source_filename,
        )
    else:
        stored = []

    return {
        "user_id": user_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_filename": source_filename,
        "extracted_count": len(relationships),
        "stored_count": len(stored),
        "relationships": stored,
    }
