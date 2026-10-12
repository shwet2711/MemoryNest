from unittest.mock import call

import pytest

from app.services import knowledge_graph_pipeline_service as pipeline


@pytest.fixture
def mocked_pipeline(monkeypatch):
    relationships = [
        {
            "subject": "MemoryNest",
            "subject_type": "project",
            "relationship": "uses",
            "object": "Python",
            "object_type": "technology",
        },
        {
            "subject": "MemoryNest",
            "subject_type": "project",
            "relationship": "stores data in",
            "object": "SQLite",
            "object_type": "technology",
        },
    ]

    stored_records = [
        {"subject": "MemoryNest", "object": "Python"},
        {"subject": "MemoryNest", "object": "SQLite"},
    ]

    extract_mock = lambda text: relationships
    store_calls = []

    def store_mock(**kwargs):
        store_calls.append(kwargs)
        return stored_records[len(store_calls) - 1]

    monkeypatch.setattr(pipeline, "extract_relationships", extract_mock)
    monkeypatch.setattr(pipeline, "store_entity_relationship", store_mock)

    return relationships, stored_records, store_calls


def test_process_chunk_extracts_and_stores_relationships(mocked_pipeline):
    relationships, stored_records, store_calls = mocked_pipeline

    result = pipeline.process_chunk_for_knowledge_graph(
        user_id=1,
        document_id=6,
        chunk_index=2,
        text="MemoryNest uses Python and stores data in SQLite.",
        source_filename="MindSync.docx",
    )

    assert result["extracted_count"] == 2
    assert result["stored_count"] == 2
    assert result["user_id"] == 1
    assert result["document_id"] == 6
    assert result["chunk_index"] == 2
    assert result["source_filename"] == "MindSync.docx"
    assert result["relationships"] == stored_records

    assert len(store_calls) == 2
    assert store_calls[0]["user_id"] == 1
    assert store_calls[0]["document_id"] == 6
    assert store_calls[0]["chunk_index"] == 2
    assert store_calls[0]["source_filename"] == "MindSync.docx"
    assert store_calls[0]["subject"] == relationships[0]["subject"]


def test_empty_text_is_rejected_before_extraction(monkeypatch):
    def fail_if_called(text):
        pytest.fail("Extraction must not run for empty text.")

    monkeypatch.setattr(pipeline, "extract_relationships", fail_if_called)

    with pytest.raises(ValueError, match="text"):
        pipeline.process_chunk_for_knowledge_graph(
            user_id=1,
            document_id=6,
            chunk_index=0,
            text=" ",
            source_filename="MindSync.docx",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", 0),
        ("user_id", -1),
        ("user_id", True),
        ("document_id", 0),
        ("document_id", -1),
        ("document_id", True),
    ],
)
def test_invalid_ids_are_rejected(field, value, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "extract_relationships",
        lambda text: pytest.fail("Extraction should not run."),
    )

    arguments = {
        "user_id": 1,
        "document_id": 6,
        "chunk_index": 0,
        "text": "MemoryNest uses Python.",
        "source_filename": "MindSync.docx",
    }
    arguments[field] = value

    with pytest.raises(ValueError):
        pipeline.process_chunk_for_knowledge_graph(**arguments)


@pytest.mark.parametrize("chunk_index", [-1, True, 1.5])
def test_invalid_chunk_index_is_rejected(chunk_index, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "extract_relationships",
        lambda text: pytest.fail("Extraction should not run."),
    )

    with pytest.raises(ValueError, match="chunk_index"):
        pipeline.process_chunk_for_knowledge_graph(
            user_id=1,
            document_id=6,
            chunk_index=chunk_index,
            text="MemoryNest uses Python.",
            source_filename="MindSync.docx",
        )


def test_no_relationships_means_no_graph_writes(monkeypatch):
    store_mock = lambda **kwargs: pytest.fail(
        "Neo4j should not be called when there are no relationships."
    )

    monkeypatch.setattr(
        pipeline, "extract_relationships", lambda text: []
    )
    monkeypatch.setattr(
        pipeline, "store_entity_relationship", store_mock
    )

    result = pipeline.process_chunk_for_knowledge_graph(
        user_id=1,
        document_id=6,
        chunk_index=0,
        text="A paragraph without explicit relationships.",
        source_filename="notes.txt",
    )

    assert result["extracted_count"] == 0
    assert result["stored_count"] == 0
    assert result["relationships"] == []


def test_extraction_failure_does_not_write_to_graph(monkeypatch):
    def raise_extraction_error(text):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(
        pipeline, "extract_relationships", raise_extraction_error
    )
    monkeypatch.setattr(
        pipeline,
        "store_entity_relationship",
        lambda **kwargs: pytest.fail("Graph write should not run."),
    )

    with pytest.raises(RuntimeError, match="Model unavailable"):
        pipeline.process_chunk_for_knowledge_graph(
            user_id=1,
            document_id=6,
            chunk_index=0,
            text="MemoryNest uses Python.",
            source_filename="MindSync.docx",
        )
