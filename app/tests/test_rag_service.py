from app.services.rag_service import (
    build_context,
)


def test_build_context_empty():
    result = build_context([])

    assert result == ""


def test_build_context_with_result():
    results = [
        {
            "content": "MindSync is a memory management system.",
            "metadata": {
                "source_filename": "MindSync.docx",
                "chunk_index": 2,
            },
        }
    ]

    context = build_context(results)

    assert "MindSync.docx" in context
    assert "memory management system" in context
    assert "Chunk: 2" in context