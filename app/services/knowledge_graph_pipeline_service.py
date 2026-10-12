
from __future__ import annotations

from typing import Any

from app.services.entity_extraction_service import extract_relationships
from app.services.knowledge_graph_service import store_entity_relationship


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
    """Extract relationships from one chunk and store them in Neo4j."""

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

    # Extraction happens first. No graph writes occur if extraction fails.
    relationships = extract_relationships(text)

    stored: list[dict[str, Any]] = []

    for relationship in relationships:
        record = store_entity_relationship(
            user_id=user_id,
            document_id=document_id,
            chunk_index=chunk_index,
            subject=relationship["subject"],
            subject_type=relationship["subject_type"],
            relationship=relationship["relationship"],
            object_name=relationship["object"],
            object_type=relationship["object_type"],
            source_filename=source_filename,
        )
        stored.append(record)

    return {
        "user_id": user_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_filename": source_filename,
        "extracted_count": len(relationships),
        "stored_count": len(stored),
        "relationships": stored,
    }
