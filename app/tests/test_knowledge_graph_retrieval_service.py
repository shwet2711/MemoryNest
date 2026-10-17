from unittest.mock import patch

from app.services.knowledge_graph_retrieval_service import (
    retrieve_graph_context,
)


GRAPH_FACTS = [
    {
        "subject": "Python",
        "subject_type": "technology",
        "relationship": "used for",
        "object": "Data Science",
        "object_type": "field",
        "source_filename": "Python.docx",
        "document_id": 6,
        "chunk_index": 2,
    },
    {
        "subject": "SQL",
        "subject_type": "technology",
        "relationship": "queries",
        "object": "Databases",
        "object_type": "technology",
        "source_filename": "SQL.docx",
        "document_id": 7,
        "chunk_index": 1,
    },
]


def test_retrieves_relationship_for_entity_in_query():
    with patch(
        "app.services.knowledge_graph_retrieval_service."
        "get_user_knowledge_graph",
        return_value=GRAPH_FACTS,
    ):
        result = retrieve_graph_context(
            user_id=1,
            query="What is Python used for?",
        )

    assert result["available"] is True
    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["subject"] == "Python"
    assert "Python --used for--> Data Science" in result["context"]
    assert result["sources"][0]["filename"] == "Python.docx"


def test_document_filter_limits_graph_evidence():
    with patch(
        "app.services.knowledge_graph_retrieval_service."
        "get_user_knowledge_graph",
        return_value=GRAPH_FACTS,
    ):
        result = retrieve_graph_context(
            user_id=1,
            query="Explain Python and SQL",
            document_id=6,
        )

    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["document_id"] == 6


def test_unmentioned_entities_do_not_match():
    with patch(
        "app.services.knowledge_graph_retrieval_service."
        "get_user_knowledge_graph",
        return_value=GRAPH_FACTS,
    ):
        result = retrieve_graph_context(
            user_id=1,
            query="Tell me about statistics",
        )

    assert result["relationships"] == []
    assert result["context"] == ""


def test_unavailable_graph_does_not_break_retrieval():
    with patch(
        "app.services.knowledge_graph_retrieval_service."
        "get_user_knowledge_graph",
        side_effect=RuntimeError("Neo4j unavailable"),
    ):
        result = retrieve_graph_context(
            user_id=1,
            query="What is Python?",
        )

    assert result["available"] is False
    assert result["relationships"] == []
    assert result["context"] == ""


def test_rejects_invalid_user_id():
    try:
        retrieve_graph_context(user_id=0, query="Python")
    except ValueError as exc:
        assert "user_id" in str(exc)
    else:
        raise AssertionError("Expected invalid user_id to be rejected.")
