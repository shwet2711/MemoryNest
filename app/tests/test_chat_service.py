from unittest.mock import patch

import pytest

from app.services.chat_service import (
    chat_with_memorynest,
    get_chat_documents,
    get_retrieved_passages,
    get_source_names,
)


def test_chat_with_memorynest():

    fake_result = {
        "answer": "MindSync is a memory system.",
        "mode": "ollama",
        "sources": ["MindSync.docx"],
        "results": [],
        "context": "MindSync is a memory system.",
        "ollama_available": True,
    }

    with patch(
        "app.services.chat_service.answer_query",
        return_value=fake_result,
    ) as mocked:

        result = chat_with_memorynest(
            user_id=1,
            query="What is MindSync?",
            top_k=5,
        )

    mocked.assert_called_once_with(
        user_id=1,
        query="What is MindSync?",
        top_k=5,
        document_id=None,
        use_ollama=True,
    )

    assert result == fake_result


def test_chat_with_specific_document():

    fake_result = {
        "answer": "MindSync is a memory system.",
        "mode": "ollama",
        "sources": ["MindSync.docx"],
        "results": [],
        "context": "MindSync is a memory system.",
        "ollama_available": True,
    }

    with patch(
        "app.services.chat_service._validate_document_access"
    ) as access_mock, patch(
        "app.services.chat_service.answer_query",
        return_value=fake_result,
    ) as answer_mock:

        result = chat_with_memorynest(
            user_id=1,
            query="What is MindSync?",
            top_k=5,
            document_id=6,
        )

    access_mock.assert_called_once_with(
        user_id=1,
        document_id=6,
    )

    answer_mock.assert_called_once_with(
        user_id=1,
        query="What is MindSync?",
        top_k=5,
        document_id=6,
        use_ollama=True,
    )

    assert result == fake_result


def test_chat_rejects_empty_query():

    with pytest.raises(ValueError):

        chat_with_memorynest(
            user_id=1,
            query="",
        )


def test_chat_rejects_invalid_user():

    with pytest.raises(ValueError):

        chat_with_memorynest(
            user_id=0,
            query="What is MindSync?",
        )


def test_chat_rejects_invalid_top_k():

    with pytest.raises(ValueError):

        chat_with_memorynest(
            user_id=1,
            query="What is MindSync?",
            top_k=0,
        )


def test_chat_rejects_invalid_document_id():

    with pytest.raises(ValueError):

        chat_with_memorynest(
            user_id=1,
            query="What is MindSync?",
            document_id=0,
        )


def test_get_chat_documents():

    documents = get_chat_documents(
        user_id=1
    )

    assert isinstance(
        documents,
        list,
    )

    if documents:

        document = documents[0]

        assert "id" in document
        assert "filename" in document
        assert "extraction_status" in document


def test_get_source_names():

    result = {
        "sources": [
            "MindSync.docx",
            "MindSync.docx",
            "Notes.txt",
        ]
    }

    sources = get_source_names(
        result
    )

    assert sources == [
        "MindSync.docx",
        "Notes.txt",
    ]


def test_get_source_names_without_sources():

    assert get_source_names({}) == []


def test_get_retrieved_passages():

    passages = [
        {
            "content": "Example content.",
            "metadata": {
                "source_filename": "MindSync.docx"
            },
        }
    ]

    result = {
        "results": passages
    }

    assert get_retrieved_passages(
        result
    ) == passages


def test_get_retrieved_passages_without_results():

    assert get_retrieved_passages({}) == []

def test_get_source_details_from_sources():
    from app.services.chat_service import (
        get_source_details,
    )

    result = {
        "sources": [
            {
                "filename": "MindSync.docx",
                "page_number": 3,
                "chunk_index": 7,
                "distance": 0.21,
                "content": "MindSync solves information management problems.",
            }
        ]
    }

    sources = get_source_details(result)

    assert len(sources) == 1
    assert sources[0]["filename"] == "MindSync.docx"
    assert sources[0]["page_number"] == 3
    assert sources[0]["chunk_index"] == 7


def test_get_source_details_without_sources():
    from app.services.chat_service import (
        get_source_details,
    )

    assert get_source_details({}) == []


def test_get_source_names_from_source_objects():
    from app.services.chat_service import (
        get_source_names,
    )

    result = {
        "sources": [
            {
                "filename": "MindSync.docx",
                "page_number": 3,
            },
            {
                "filename": "MindSync.docx",
                "page_number": 4,
            },
        ]
    }

    assert get_source_names(result) == [
        "MindSync.docx"
    ]
