from unittest.mock import MagicMock, patch


import pytest

from app.services.retrieval_service import (
    get_max_distance,
    retrieve_chunks,
)


def test_retrieval_rejects_empty_query():
    with pytest.raises(ValueError):
        retrieve_chunks(
            query="   ",
            user_id=1,
        )


def test_retrieval_rejects_invalid_user():
    with pytest.raises(ValueError):
        retrieve_chunks(
            query="What is MemoryNest?",
            user_id=0,
        )


def test_retrieval_rejects_invalid_top_k():
    with pytest.raises(ValueError):
        retrieve_chunks(
            query="What is MemoryNest?",
            user_id=1,
            top_k=0,
        )


def test_retrieval_rejects_invalid_document_id():
    with pytest.raises(ValueError):
        retrieve_chunks(
            query="What is MemoryNest?",
            user_id=1,
            document_id=0,
        )


def test_retrieval_rejects_non_string_query():
    with pytest.raises(TypeError):
        retrieve_chunks(
            query=None,
            user_id=1,
        )


def test_get_max_distance_default():
    with patch.dict(
        "os.environ",
        {},
        clear=True,
    ):
        assert get_max_distance() == 0.70


def test_get_max_distance_from_environment():
    with patch.dict(
        "os.environ",
        {
            "MEMORYNEST_RAG_MAX_DISTANCE": "0.45",
        },
        clear=False,
    ):
        assert get_max_distance() == 0.45


def test_get_max_distance_rejects_invalid_value():
    with patch.dict(
        "os.environ",
        {
            "MEMORYNEST_RAG_MAX_DISTANCE": "invalid",
        },
        clear=False,
    ):
        with pytest.raises(ValueError):
            get_max_distance()


@patch("app.services.retrieval_service.generate_embedding")
@patch("app.services.retrieval_service.get_collection")
def test_retrieval_filters_weak_results(
    mock_get_collection,
    mock_generate_embedding,
):
    collection = mock_get_collection.return_value

    collection.count.return_value = 3

    collection.get.return_value = {
        "ids": [
            "vector-1",
            "vector-2",
            "vector-3",
        ]
    }

    collection.query.return_value = {
        "ids": [[
            "vector-1",
            "vector-2",
            "vector-3",
        ]],
        "documents": [[
            "Relevant passage",
            "Weak passage",
            "Another relevant passage",
        ]],
        "metadatas": [[
            {
                "source_filename": "MindSync.docx",
                "chunk_index": 1,
            },
            {
                "source_filename": "Other.docx",
                "chunk_index": 2,
            },
            {
                "source_filename": "MindSync.docx",
                "chunk_index": 3,
            },
        ]],
        "distances": [[
            0.20,
            0.90,
            0.40,
        ]],
    }

    mock_generate_embedding.return_value = [0.1, 0.2]

    results = retrieve_chunks(
        query="What is MindSync?",
        user_id=1,
        top_k=3,
        max_distance=0.65,
    )

    assert len(results) == 2
    assert results[0]["vector_id"] == "vector-1"
    assert results[1]["vector_id"] == "vector-3"


@patch("app.services.retrieval_service.generate_embedding")
@patch("app.services.retrieval_service.get_collection")
def test_retrieval_removes_duplicate_content(
    mock_get_collection,
    mock_generate_embedding,
):
    collection = mock_get_collection.return_value

    collection.count.return_value = 2

    collection.get.return_value = {
        "ids": [
            "vector-1",
            "vector-2",
        ]
    }

    collection.query.return_value = {
        "ids": [[
            "vector-1",
            "vector-2",
        ]],
        "documents": [[
            "Same passage",
            "Same passage",
        ]],
        "metadatas": [[
            {
                "source_filename": "MindSync.docx",
                "chunk_index": 1,
            },
            {
                "source_filename": "MindSync.docx",
                "chunk_index": 2,
            },
        ]],
        "distances": [[
            0.20,
            0.30,
        ]],
    }

    mock_generate_embedding.return_value = [0.1, 0.2]

    results = retrieve_chunks(
        query="What is MindSync?",
        user_id=1,
        top_k=2,
        max_distance=0.65,
    )

    assert len(results) == 1
    assert results[0]["content"] == "Same passage"

def test_retrieval_explicit_max_distance(
    monkeypatch,
):
    monkeypatch.setenv(
        "MEMORYNEST_RAG_MAX_DISTANCE",
        "0.40",
    )

    collection = MagicMock()

    collection.count.return_value = 1

    collection.get.return_value = {
        "ids": ["chunk-1"],
    }

    collection.query.return_value = {
        "ids": [["chunk-1"]],
        "documents": [["Relevant content"]],
        "metadatas": [[
            {
                "user_id": 1,
                "source_filename": "test.txt",
                "chunk_index": 0,
            }
        ]],
        "distances": [[0.50]],
    }

    with patch(
        "app.services.retrieval_service.get_collection",
        return_value=collection,
    ):
        with patch(
            "app.services.retrieval_service.generate_embedding",
            return_value=[0.1, 0.2],
        ):
            results = retrieve_chunks(
                query="test",
                user_id=1,
                top_k=5,
                max_distance=0.60,
            )

    assert len(results) == 1
    assert results[0]["distance"] == 0.50
