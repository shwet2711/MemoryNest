import pytest

from app.services.rag_evaluation_service import (
    evaluate_rag_context,
    evaluate_retrieval_results,
)


def test_evaluation_with_no_results():
    result = evaluate_retrieval_results(
        [],
        max_distance=0.70,
    )

    assert result["status"] == "no_results"
    assert result["result_count"] == 0
    assert result["best_distance"] is None
    assert result["confidence"] == 0.0
    assert result["grounding_ready"] if "grounding_ready" in result else True


def test_evaluation_strong_result():
    results = [
        {
            "content": "MemoryNest stores personal documents.",
            "metadata": {
                "source_filename": "MindSync.docx",
            },
            "distance": 0.20,
        }
    ]

    result = evaluate_retrieval_results(
        results,
        max_distance=0.70,
    )

    assert result["status"] == "strong"
    assert result["result_count"] == 1
    assert result["best_distance"] == 0.20
    assert result["source_count"] == 1
    assert result["sources"] == ["MindSync.docx"]
    assert result["confidence"] == 1.0


def test_evaluation_good_result():
    results = [
        {
            "content": "Relevant content.",
            "metadata": {
                "source_filename": "notes.txt",
            },
            "distance": 0.45,
        }
    ]

    result = evaluate_retrieval_results(
        results,
        max_distance=0.70,
    )

    assert result["status"] == "good"
    assert result["confidence"] == 0.75


def test_evaluation_moderate_result():
    results = [
        {
            "content": "Relevant content.",
            "metadata": {
                "source_filename": "notes.txt",
            },
            "distance": 0.60,
        }
    ]

    result = evaluate_retrieval_results(
        results,
        max_distance=0.70,
    )

    assert result["status"] == "moderate"
    assert result["confidence"] == 0.50


def test_evaluation_multiple_sources():
    results = [
        {
            "content": "First passage.",
            "metadata": {
                "source_filename": "one.pdf",
            },
            "distance": 0.30,
        },
        {
            "content": "Second passage.",
            "metadata": {
                "source_filename": "two.docx",
            },
            "distance": 0.40,
        },
        {
            "content": "Third passage.",
            "metadata": {
                "source_filename": "one.pdf",
            },
            "distance": 0.50,
        },
    ]

    result = evaluate_retrieval_results(
        results,
        max_distance=0.70,
    )

    assert result["result_count"] == 3
    assert result["source_count"] == 2
    assert result["sources"] == [
        "one.pdf",
        "two.docx",
    ]
    assert result["average_distance"] == pytest.approx(0.40)


def test_evaluate_rag_context():
    results = [
        {
            "content": "MemoryNest content.",
            "metadata": {
                "source_filename": "MindSync.docx",
            },
            "distance": 0.30,
        }
    ]

    result = evaluate_rag_context(
        results=results,
        context="File: MindSync.docx\nContent:\nMemoryNest content.",
        max_distance=0.70,
    )

    assert result["status"] == "strong"
    assert result["context_available"] is True
    assert result["context_length"] > 0
    assert result["grounding_ready"] is True


def test_evaluate_empty_context():
    result = evaluate_rag_context(
        results=[],
        context="",
        max_distance=0.70,
    )

    assert result["status"] == "no_results"
    assert result["context_available"] is False
    assert result["context_length"] == 0
    assert result["grounding_ready"] is False