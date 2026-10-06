
import pytest

from app.services.retrieval_service import retrieve_chunks


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