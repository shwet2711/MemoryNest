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



def test_retrieval_only_includes_graph_evidence_and_source():
    fake_rag = {
        "query": "What is MindSync?",
        "document_id": 6,
        "results": [
            {
                "content": "MindSync manages personal information.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "document_id": 6,
                    "chunk_index": 4,
                },
                "distance": 0.3,
            }
        ],
        "context": "MindSync manages personal information.",
        "has_context": True,
    }

    fake_graph = {
        "available": True,
        "context": (
            "[Graph fact 1]\n"
            "Fact: MindSync --stores--> Memories\n"
            "Source file: MindSync.docx\n"
            "Document ID: 6\n"
            "Chunk: 4"
        ),
        "sources": [
            {
                "filename": "MindSync.docx",
                "document_id": 6,
                "chunk_index": 4,
                "evidence_type": "knowledge_graph",
            }
        ],
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=False,
    ), patch(
        "app.services.answer_service.retrieve_graph_context",
        return_value=fake_graph,
    ) as graph_retrieval:
        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            document_id=6,
            use_ollama=False,
        )

    assert "Supplementary knowledge-graph evidence" in result["context"]
    assert "MindSync --stores--> Memories" in result["context"]
    assert any(
        source.get("evidence_type") == "knowledge_graph"
        for source in result["sources"]
    )
    assert result["document_id"] == 6

    graph_retrieval.assert_called_once_with(
        user_id=1,
        query="What is MindSync?",
        document_id=6,
    )


def test_graph_failure_does_not_break_retrieval_only_answer():
    fake_rag = {
        "query": "What is MindSync?",
        "results": [
            {
                "content": "MindSync manages personal information.",
                "metadata": {
                    "source_filename": "MindSync.docx",
                    "chunk_index": 4,
                },
                "distance": 0.3,
            }
        ],
        "context": "MindSync manages personal information.",
        "has_context": True,
    }

    with patch(
        "app.services.answer_service.get_rag_context",
        return_value=fake_rag,
    ), patch(
        "app.services.answer_service.is_ollama_available",
        return_value=False,
    ), patch(
        "app.services.answer_service.retrieve_graph_context",
        side_effect=RuntimeError("Graph service unavailable"),
    ):
        result = answer_query(
            user_id=1,
            query="What is MindSync?",
            use_ollama=False,
        )

    assert result["mode"] == "retrieval_only"
    assert "MindSync manages personal information." in result["context"]
    assert any(
        source.get("filename") == "MindSync.docx"
        for source in result["sources"]
    )
    assert not any(
        source.get("evidence_type") == "knowledge_graph"
        for source in result["sources"]
    )
