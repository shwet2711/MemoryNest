from unittest.mock import patch

from app.services.answer_service import (
    answer_query,
)


def test_answer_without_ollama():

    fake_rag = {
        "query": "What is MindSync?",
        "results": [
            {
                "content": "MindSync is a memory management system.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "chunk_index": 1,
                },
                "distance": 0.4,
            }
        ],
        "context": (
            "[Source 1]\n"
            "File: MindSync.docx\n"
            "Chunk: 1\n"
            "Content:\n"
            "MindSync is a memory management system."
        ),
        "has_context": True,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=False,
    ):

        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            use_ollama=False,
        )

    assert result["mode"] == "retrieval_only"
    assert "MindSync.docx" in result["sources"]


def test_no_context():

    fake_rag = {
        "query": "Unknown question",
        "results": [],
        "context": "",
        "has_context": False,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ):

        result = answer_query(
            user_id=1,
            query="Unknown question",
        )

    assert result["mode"] == "retrieval_only"
    assert result["sources"] == []
    assert "couldn't find enough information" in (
        result["answer"].lower()
    )


def test_ollama_unavailable():

    fake_rag = {
        "query": "What is MindSync?",
        "results": [
            {
                "content": "MindSync is a memory system.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "chunk_index": 1,
                },
            }
        ],
        "context": "MindSync is a memory system.",
        "has_context": True,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=False,
    ):

        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            use_ollama=True,
        )

    assert result["mode"] == "retrieval_only"
    assert result["ollama_available"] is False

from unittest.mock import patch


def test_answer_query_returns_sources():
    from app.services.answer_service import answer_query

    rag_result = {
        "query": "What is MindSync?",
        "top_k": 2,
        "document_id": 6,
        "results": [
            {
                "content": "MindSync manages personal information.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "page_number": 2,
                    "chunk_index": 4,
                },
                "distance": 0.18,
            }
        ],
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=rag_result,
    ):
        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            top_k=2,
            document_id=6,
            use_ollama=False,
        )

    assert result["mode"] == "retrieval"
    assert result["document_id"] == 6
    assert len(result["sources"]) == 1
    assert result["sources"][0]["filename"] == "MindSync.docx"
    assert result["sources"][0]["page_number"] == 2


def test_answer_query_without_context_uses_fallback():
    from app.services.answer_service import answer_query

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value={
            "query": "Unknown question",
            "top_k": 5,
            "document_id": None,
            "results": [],
        },
    ):
        result = answer_query(
            user_id=1,
            query="Unknown question",
            use_ollama=False,
        )

    assert result["mode"] == "fallback"
    assert result["sources"] == []
    assert result["results"] == []

def test_answer_query_blocks_weak_context_before_ollama():
    fake_rag = {
        "query": "Tell me something specific.",
        "results": [
            {
                "content": "Only loosely related information.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "chunk_index": 0,
                },
                "distance": 0.6568,
            }
        ],
        "context": (
            "[Source 1]\n"
            "File: MindSync.docx\n"
            "Chunk: 0\n"
            "Content:\n"
            "Only loosely related information."
        ),
        "has_context": True,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=True,
    ), patch(
        "app.services.answer_service.generate_with_ollama",
    ) as generate:

        result = answer_query(
            user_id=1,
            query="Tell me something specific.",
            use_ollama=True,
        )

    assert result["answer"] == (
        "I couldn't find enough information in your documents."
    )
    assert result["mode"] == "fallback"
    assert result["sources"] == []
    assert result["rag_evaluation"]["grounding_ready"] is False
    generate.assert_not_called()


def test_answer_query_allows_strong_context_to_ollama():
    fake_rag = {
        "query": "What is MindSync?",
        "results": [
            {
                "content": "MindSync is a memory management system.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "chunk_index": 0,
                },
                "distance": 0.30,
            }
        ],
        "context": (
            "[Source 1]\n"
            "File: MindSync.docx\n"
            "Chunk: 0\n"
            "Content:\n"
            "MindSync is a memory management system."
        ),
        "has_context": True,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=True,
    ), patch(
        "app.services.answer_service.generate_with_ollama",
        return_value="MindSync is a memory management system.",
    ) as generate:

        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            use_ollama=True,
        )

    assert result["mode"] == "ollama"
    assert result["answer"] == (
        "MindSync is a memory management system."
    )
    assert result["rag_evaluation"]["grounding_ready"] is True
    generate.assert_called_once()
