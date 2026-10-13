
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import indexing_service
from app.services.indexing_service import index_document


def make_db(chunks, records=None):
    """Create a mocked database for indexing tests."""
    db = MagicMock()

    chunks_query = MagicMock()
    chunks_query.filter.return_value.order_by.return_value.all.return_value = (
        chunks
    )

    records_query = MagicMock()
    records_query.filter.return_value.all.return_value = (
        records if records is not None else []
    )

    db.query.side_effect = [chunks_query, records_query]
    return db


def make_chunk(
    chunk_id=10,
    document_id=6,
    user_id=1,
    chunk_index=0,
    content="MemoryNest uses Python and SQLite.",
    filename="notes.txt",
):
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        user_id=user_id,
        chunk_index=chunk_index,
        content=content,
        source_filename=filename,
    )


def mock_vector_indexing(monkeypatch):
    """Replace model inference and vector storage with fast test doubles."""
    monkeypatch.setattr(
        indexing_service,
        "get_embedding_model_name",
        lambda: "test-model",
    )
    monkeypatch.setattr(
        indexing_service,
        "get_embedding_dimension",
        lambda: 3,
    )
    monkeypatch.setattr(
        indexing_service,
        "generate_embeddings",
        lambda texts: [[0.1, 0.2, 0.3] for _ in texts],
    )
    monkeypatch.setattr(
        indexing_service,
        "add_embeddings",
        MagicMock(),
    )
    monkeypatch.setattr(
        indexing_service,
        "delete_embedding",
        MagicMock(),
    )


def test_index_document_rejects_invalid_document_id():
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            index_document(
                db=MagicMock(),
                document_id=value,
                user_id=1,
            )


def test_index_document_rejects_invalid_user_id():
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            index_document(
                db=MagicMock(),
                document_id=1,
                user_id=value,
            )


def test_index_document_rejects_invalid_batch_size():
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            index_document(
                db=MagicMock(),
                document_id=1,
                user_id=1,
                batch_size=value,
            )


def test_index_document_returns_no_chunks():
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    result = index_document(
        db=db,
        document_id=999999,
        user_id=999999,
    )

    assert result == {
        "document_id": 999999,
        "total_chunks": 0,
        "indexed": 0,
        "status": "no_chunks",
    }


def test_vector_indexing_succeeds_when_neo4j_is_disabled(monkeypatch):
    chunk = make_chunk()
    db = make_db([chunk])

    mock_vector_indexing(monkeypatch)
    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", False)

    graph_mock = MagicMock()
    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_mock,
    )

    result = index_document(db, document_id=6, user_id=1)

    assert result["status"] == "completed"
    assert result["indexed"] == 1
    assert result["knowledge_graph_status"] == "disabled"
    assert result["knowledge_graph_processed_chunks"] == 0
    graph_mock.assert_not_called()
    db.commit.assert_called_once()


def test_enabled_knowledge_graph_processes_each_chunk(monkeypatch):
    chunks = [
        make_chunk(chunk_id=10, chunk_index=0),
        make_chunk(
            chunk_id=11,
            chunk_index=1,
            content="Streamlit displays the application.",
        ),
    ]
    db = make_db(chunks)

    mock_vector_indexing(monkeypatch)
    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": True},
    )

    graph_mock = MagicMock(
        side_effect=[
            {"stored_count": 2},
            {"stored_count": 1},
        ]
    )
    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_mock,
    )

    result = index_document(
        db,
        document_id=6,
        user_id=1,
        batch_size=1,
    )

    assert result["status"] == "completed"
    assert result["indexed"] == 2
    assert result["knowledge_graph_status"] == "completed"
    assert result["knowledge_graph_processed_chunks"] == 2
    assert result["knowledge_graph_failed_chunks"] == 0
    assert result["knowledge_graph_relationships_stored"] == 3
    assert graph_mock.call_count == 2

    first_call = graph_mock.call_args_list[0].kwargs
    assert first_call["user_id"] == 1
    assert first_call["document_id"] == 6
    assert first_call["chunk_index"] == 0
    assert first_call["source_filename"] == "notes.txt"


def test_unavailable_neo4j_does_not_break_vector_indexing(monkeypatch):
    db = make_db([make_chunk()])
    mock_vector_indexing(monkeypatch)

    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": False},
    )

    graph_mock = MagicMock()
    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_mock,
    )

    result = index_document(db, document_id=6, user_id=1)

    assert result["status"] == "completed"
    assert result["indexed"] == 1
    assert result["knowledge_graph_status"] == "unavailable"
    graph_mock.assert_not_called()


def test_graph_failure_does_not_break_vector_indexing(monkeypatch):
    db = make_db([make_chunk()])
    mock_vector_indexing(monkeypatch)

    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": True},
    )

    def fail_graph(**kwargs):
        raise RuntimeError("Simulated graph failure")

    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        fail_graph,
    )

    result = index_document(db, document_id=6, user_id=1)

    assert result["status"] == "completed"
    assert result["indexed"] == 1
    assert result["knowledge_graph_status"] == "failed"
    assert result["knowledge_graph_processed_chunks"] == 0
    assert result["knowledge_graph_failed_chunks"] == 1
    db.commit.assert_called_once()


def test_partial_graph_failure_is_reported(monkeypatch):
    chunks = [
        make_chunk(chunk_id=10, chunk_index=0),
        make_chunk(chunk_id=11, chunk_index=1),
    ]
    db = make_db(chunks)
    mock_vector_indexing(monkeypatch)

    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": True},
    )

    graph_mock = MagicMock(
        side_effect=[
            {"stored_count": 2},
            RuntimeError("Simulated failure"),
        ]
    )
    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_mock,
    )

    result = index_document(db, document_id=6, user_id=1)

    assert result["status"] == "completed"
    assert result["indexed"] == 2
    assert result["knowledge_graph_status"] == "partial_failure"
    assert result["knowledge_graph_processed_chunks"] == 1
    assert result["knowledge_graph_failed_chunks"] == 1
    assert result["knowledge_graph_relationships_stored"] == 2
