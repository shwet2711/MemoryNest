
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase
from neo4j import Driver

from app.core.config import (
    NEO4J_DATABASE,
    NEO4J_ENABLED,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
)


_driver: Driver | None = None


def _require_text(value: str, field_name: str) -> str:
    """Validate a required, non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")

    return value.strip()


def _require_positive_integer(
    value: int,
    field_name: str,
) -> int:
    """Validate a positive integer, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")

    return value


def get_driver() -> Driver:
    """Return the lazily created Neo4j driver."""
    global _driver

    if not NEO4J_ENABLED:
        raise RuntimeError(
            "Neo4j is disabled. Set NEO4J_ENABLED=True in .env."
        )

    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        )

    return _driver


def close_driver() -> None:
    """Close the shared Neo4j driver, if one exists."""
    global _driver

    if _driver is not None:
        _driver.close()
        _driver = None


def check_neo4j_connection() -> dict[str, Any]:
    """Check whether the optional Neo4j service is available."""
    if not NEO4J_ENABLED:
        return {
            "enabled": False,
            "available": False,
            "message": "Neo4j is disabled.",
        }

    try:
        driver = get_driver()
        driver.verify_connectivity()

        return {
            "enabled": True,
            "available": True,
            "message": "Neo4j connection successful.",
        }

    except Exception:
        return {
            "enabled": True,
            "available": False,
            "message": "Neo4j is unavailable. Check its service and configuration.",
        }


def store_entity_relationship(
    *,
    user_id: int,
    document_id: int,
    chunk_index: int,
    subject: str,
    subject_type: str,
    relationship: str,
    object_name: str,
    object_type: str,
    source_filename: str,
) -> dict[str, Any]:
    """
    Store an entity pair and their relationship.

    The relationship and both entities retain source information
    so later graph retrieval can trace a fact to its document chunk.

    This function stores supplied, validated facts; it does not
    extract facts from documents itself.
    """
    user_id = _require_positive_integer(user_id, "user_id")
    document_id = _require_positive_integer(document_id, "document_id")

    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
        raise ValueError("chunk_index must be an integer.")

    if chunk_index < 0:
        raise ValueError("chunk_index must be non-negative.")

    subject = _require_text(subject, "subject")
    subject_type = _require_text(subject_type, "subject_type")
    relationship = _require_text(relationship, "relationship")
    object_name = _require_text(object_name, "object_name")
    object_type = _require_text(object_type, "object_type")
    source_filename = _require_text(source_filename, "source_filename")

    query = """
    MERGE (s:Entity {
        user_id: $user_id,
        normalized_name: toLower($subject),
        entity_type: $subject_type
    })
    ON CREATE SET s.name = $subject

    MERGE (o:Entity {
        user_id: $user_id,
        normalized_name: toLower($object_name),
        entity_type: $object_type
    })
    ON CREATE SET o.name = $object_name

    MERGE (s)-[r:RELATED_TO {
        user_id: $user_id,
        document_id: $document_id,
        chunk_index: $chunk_index,
        relationship: $relationship
    }]->(o)

    SET r.source_filename = $source_filename

    RETURN
        s.name AS subject,
        s.entity_type AS subject_type,
        r.relationship AS relationship,
        o.name AS object,
        o.entity_type AS object_type,
        r.source_filename AS source_filename,
        r.document_id AS document_id,
        r.chunk_index AS chunk_index
    """

    parameters = {
        "user_id": user_id,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "subject": subject,
        "subject_type": subject_type,
        "relationship": relationship,
        "object_name": object_name,
        "object_type": object_type,
        "source_filename": source_filename,
    }

    driver = get_driver()

    with driver.session(database=NEO4J_DATABASE) as session:
        record = session.run(query, parameters).single()

    if record is None:
        raise RuntimeError(
            "Neo4j did not return the stored relationship."
        )

    return dict(record)


def find_entity_relationships(
    *,
    user_id: int,
    entity_name: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find relationships connected to an entity owned by a user."""
    user_id = _require_positive_integer(user_id, "user_id")
    entity_name = _require_text(entity_name, "entity_name")

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer.")

    query = """
    MATCH (s:Entity {user_id: $user_id})-[r:RELATED_TO {user_id: $user_id}]->(o:Entity {user_id: $user_id})
    WHERE s.normalized_name = toLower($entity_name)
       OR o.normalized_name = toLower($entity_name)

    RETURN
        s.name AS subject,
        s.entity_type AS subject_type,
        r.relationship AS relationship,
        o.name AS object,
        o.entity_type AS object_type,
        r.source_filename AS source_filename,
        r.document_id AS document_id,
        r.chunk_index AS chunk_index

    ORDER BY r.document_id, r.chunk_index
    LIMIT $limit
    """

    driver = get_driver()

    with driver.session(database=NEO4J_DATABASE) as session:
        records = session.run(
            query,
            user_id=user_id,
            entity_name=entity_name,
            limit=limit,
        )

        return [dict(record) for record in records]
