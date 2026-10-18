from unittest.mock import patch

import pytest

from app.services.hybrid_retrieval_service import (
    retrieve_hybrid_context,
)


def _vector_result(
    content="MemoryNest stores personal knowledge.",
    *,
    document_id=10,
    chunk_index=0,
    distance=0.2,
    filename="notes.txt",
):
    return {
        "vector_id": f"vector-{document_id}-{chunk_index}",
        "content": content,
        "metadata": {
            "source_filename": filename,
            "document_id": document_id,
            "chunk_index": chunk_index,
        },
        "distance": distance,
    }


def _graph_relationship(
    subject="MemoryNest",
    relationship="stores",
    obj="personal knowledge",
    *,
    document_id=10,
    chunk_index=0,
    filename="notes.txt",
):
    return {
        "subject": subject,
        "relationship": relationship,
        "object": obj,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_filename": filename,
    }


def _graph_data(relationships=None, *, available=True):
    return {
        "available": available,
        "relationships": relationships or [],
        "context": "",
        "sources": [],
    }


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_combines_vector_and_graph_evidence(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = [_vector_result()]
    mock_graph.return_value = _graph_data(
        [_graph_relationship()]
    )

    result = retrieve_hybrid_context(
        user_id=1,
        query="What does MemoryNest store?",
    )

    assert result["has_context"] is True
    assert result["vector_count"] == 1
    assert result["graph_count"] == 1
    assert len(result["results"]) == 2
    assert "MemoryNest stores personal knowledge." in result["context"]
    assert "MemoryNest --stores--> personal knowledge" in result["context"]


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_vector_results_work_when_graph_is_unavailable(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = [_vector_result()]
    mock_graph.return_value = _graph_data(
        available=False
    )

    result = retrieve_hybrid_context(
        user_id=1,
        query="What does MemoryNest store?",
    )

    assert result["has_context"] is True
    assert result["graph_available"] is False
    assert result["vector_count"] == 1
    assert result["graph_count"] == 0


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_empty_retrieval_returns_empty_context(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = []
    mock_graph.return_value = _graph_data()

    result = retrieve_hybrid_context(
        user_id=1,
        query="Unknown topic",
    )

    assert result["has_context"] is False
    assert result["results"] == []
    assert result["context"] == ""
    assert result["sources"] == []


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_vector_results_are_deduplicated(
    mock_vectors,
    mock_graph,
):
    first = _vector_result(chunk_index=0)
    duplicate = _vector_result(chunk_index=0)

    mock_vectors.return_value = [first, duplicate]
    mock_graph.return_value = _graph_data()

    result = retrieve_hybrid_context(
        user_id=1,
        query="MemoryNest",
    )

    assert result["vector_count"] == 1


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_duplicate_graph_facts_are_removed(
    mock_vectors,
    mock_graph,
):
    fact = _graph_relationship(chunk_index=2)

    mock_vectors.return_value = []
    mock_graph.return_value = _graph_data([fact, fact.copy()])

    result = retrieve_hybrid_context(
        user_id=1,
        query="MemoryNest",
    )

    assert result["graph_count"] == 1


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_document_scope_is_forwarded_to_both_retrievers(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = [
        _vector_result(document_id=10)
    ]
    mock_graph.return_value = _graph_data(
        [_graph_relationship(document_id=10)]
    )

    retrieve_hybrid_context(
        user_id=1,
        query="MemoryNest",
        document_id=10,
    )

    mock_vectors.assert_called_once_with(
        query="MemoryNest",
        user_id=1,
        top_k=5,
        document_id=10,
    )
    mock_graph.assert_called_once_with(
        user_id=1,
        query="MemoryNest",
        document_id=10,
        limit=8,
    )


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_document_scope_excludes_other_document_results(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = [
        _vector_result(document_id=10),
        _vector_result(
            content="Private fact from another document.",
            document_id=20,
            chunk_index=3,
        ),
    ]
    mock_graph.return_value = _graph_data(
        [
            _graph_relationship(document_id=10),
            _graph_relationship(
                subject="Other topic",
                relationship="contains",
                obj="private data",
                document_id=20,
                chunk_index=3,
                filename="other.txt",
            ),
        ]
    )

    result = retrieve_hybrid_context(
        user_id=1,
        query="MemoryNest",
        document_id=10,
    )

    assert all(
        item["metadata"].get("document_id") == 10
        for item in result["results"]
    )
    assert "Private fact from another document." not in result["context"]


@patch(
    "app.services.hybrid_retrieval_service.retrieve_graph_context"
)
@patch(
    "app.services.hybrid_retrieval_service.retrieve_chunks"
)
def test_rrf_ranking_can_promote_top_graph_result(
    mock_vectors,
    mock_graph,
):
    mock_vectors.return_value = [
        _vector_result(
            content="Second-ranked vector passage.",
            chunk_index=1,
        ),
        _vector_result(
            content="Third-ranked vector passage.",
            chunk_index=2,
        ),
    ]
    mock_graph.return_value = _graph_data(
        [
            _graph_relationship(
                subject="MemoryNest",
                relationship="connects",
                obj="timeline",
            )
        ]
    )

    result = retrieve_hybrid_context(
        user_id=1,
        query="MemoryNest timeline",
    )

    assert result["results"][0]["evidence_type"] == "vector"
    assert result["results"][1]["evidence_type"] == "knowledge_graph"
    assert result["results"][1]["content"] == (
        "MemoryNest --connects--> timeline"
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"user_id": 0, "query": "MemoryNest"}, "user_id"),
        ({"user_id": 1, "query": "   "}, "query"),
        ({"user_id": 1, "query": "MemoryNest", "top_k": 0}, "top_k"),
        (
            {
                "user_id": 1,
                "query": "MemoryNest",
                "document_id": 0,
            },
            "document_id",
        ),
        (
            {
                "user_id": 1,
                "query": "MemoryNest",
                "graph_limit": 0,
            },
            "graph_limit",
        ),
    ],
)
def test_invalid_inputs_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        retrieve_hybrid_context(**kwargs)