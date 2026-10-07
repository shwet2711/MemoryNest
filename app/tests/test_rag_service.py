
import os
from unittest.mock import patch

from app.services.rag_service import (
    build_context,
    get_rag_context,
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
            "distance": 0.21,
        }
    ]

    context = build_context(results)

    assert "MindSync.docx" in context
    assert "memory management system" in context
    assert "Chunk: 2" in context
    assert "Similarity distance: 0.2100" in context


def test_build_context_includes_page_number():
    results = [
        {
            "content": "MemoryNest stores personal knowledge.",
            "metadata": {
                "source_filename": "MemoryNest.pdf",
                "page_number": 4,
                "chunk_index": 2,
            },
            "distance": 0.18,
        }
    ]

    context = build_context(results)

    assert "File: MemoryNest.pdf" in context
    assert "Page: 4" in context
    assert "Chunk: 2" in context


def test_build_context_skips_empty_content():
    results = [
        {
            "content": "   ",
            "metadata": {
                "source_filename": "Empty.docx",
                "chunk_index": 1,
            },
        },
        {
            "content": "Valid content.",
            "metadata": {
                "source_filename": "Valid.docx",
                "chunk_index": 2,
            },
        },
    ]

    context = build_context(results)

    assert "Empty.docx" not in context
    assert "Valid content." in context


def test_build_context_respects_max_chars():
    results = [
        {
            "content": "A" * 5000,
            "metadata": {
                "source_filename": "Large.docx",
                "chunk_index": 1,
            },
        },
        {
            "content": "B" * 5000,
            "metadata": {
                "source_filename": "Large.docx",
                "chunk_index": 2,
            },
        },
    ]

    context = build_context(
        results,
        max_chars=6000,
    )

    assert len(context) <= 6000


def test_get_rag_context_reports_effective_distance():
    with patch.dict(
        "os.environ",
        {},
        clear=True,
    ):
        with patch(
            "app.services.rag_service.retrieve_context",
            return_value=[],
        ):
            result = get_rag_context(
                user_id=1,
                query="test query",
            )

    assert result["max_distance"] == 0.70


def test_get_rag_context_preserves_explicit_distance():
    with patch(
        "app.services.rag_service.retrieve_context",
        return_value=[],
    ):
        result = get_rag_context(
            user_id=1,
            query="test query",
            max_distance=0.55,
        )

    assert result["max_distance"] == 0.55
