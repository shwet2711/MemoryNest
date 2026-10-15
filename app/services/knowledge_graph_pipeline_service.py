from __future__ import annotations

from typing import Any

from app.services.entity_extraction_service import extract_relationships
from app.services.knowledge_graph_service import replace_chunk_relationships


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
    """Extract and atomically replace relationships for one document chunk."""
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

    # Extract first. If extraction fails, existing graph data stays untouched.
    relationships = extract_relationships(text)

    # An empty list is intentional: it clears obsolete relationships for
    # this chunk when the updated text no longer contains known relationships.
    stored = replace_chunk_relationships(
        relationships=relationships,
        user_id=user_id,
        document_id=document_id,
        chunk_index=chunk_index,
        source_filename=source_filename,
    )

    return {
        "user_id": user_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_filename": source_filename,
        "extracted_count": len(relationships),
        "stored_count": len(stored),
        "relationships": stored,
    }
