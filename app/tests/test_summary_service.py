from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.summary_service import (
    build_summary_prompt,
    read_extracted_text,
    summarize_document,
)


def test_build_summary_prompt():
    prompt = build_summary_prompt(
        filename="MindSync.docx",
        document_text="MindSync is a personal memory system.",
    )

    assert "MindSync.docx" in prompt
    assert "personal memory system" in prompt
    assert "Summarize" in prompt


def test_build_summary_prompt_rejects_empty_text():
    with pytest.raises(ValueError):
        build_summary_prompt(
            filename="MindSync.docx",
            document_text="",
        )


def test_read_extracted_text(tmp_path: Path):
    text_file = tmp_path / "document.txt"

    text_file.write_text(
        "This is extracted document text.",
        encoding="utf-8",
    )

    result = read_extracted_text(
        str(text_file)
    )

    assert result == (
        "This is extracted document text."
    )


def test_read_extracted_text_rejects_missing_file(
    tmp_path: Path,
):
    missing_file = (
        tmp_path / "missing.txt"
    )

    with pytest.raises(FileNotFoundError):
        read_extracted_text(
            str(missing_file)
        )


def test_summarize_document():
    fake_document = {
        "id": 6,
        "filename": "MindSync.docx",
        "file_path": "data/uploads/mindsync.docx",
        "extracted_text_path": (
            "data/extracted/document_6.txt"
        ),
        "extraction_status": "completed",
        "title": None,
    }

    with patch(
        "app.services.summary_service.get_user_document",
        return_value=fake_document,
    ), patch(
        "app.services.summary_service.read_extracted_text",
        return_value=(
            "MindSync is a personal memory and "
            "knowledge management system."
        ),
    ), patch(
        "app.services.summary_service.is_ollama_available",
        return_value=True,
    ), patch(
        "app.services.summary_service.get_ollama_model",
        return_value="llama3.2:3b",
    ), patch(
        "app.services.summary_service.generate_with_ollama",
        return_value=(
            "MindSync is a personal memory and "
            "knowledge management system."
        ),
    ) as mock_generate:

        result = summarize_document(
            user_id=1,
            document_id=6,
        )

    assert result["document_id"] == 6
    assert result["filename"] == "MindSync.docx"
    assert result["mode"] == "ollama"
    assert result["ollama_available"] is True
    assert result["model"] == "llama3.2:3b"
    assert "MindSync" in result["summary"]

    mock_generate.assert_called_once()


def test_summarize_document_rejects_invalid_user():
    with pytest.raises(ValueError):
        summarize_document(
            user_id=0,
            document_id=6,
        )


def test_summarize_document_rejects_invalid_document():
    with pytest.raises(ValueError):
        summarize_document(
            user_id=1,
            document_id=0,
        )


def test_summarize_document_requires_completed_extraction():
    fake_document = {
        "id": 6,
        "filename": "MindSync.docx",
        "file_path": "data/uploads/mindsync.docx",
        "extracted_text_path": (
            "data/extracted/document_6.txt"
        ),
        "extraction_status": "pending",
        "title": None,
    }

    with patch(
        "app.services.summary_service.get_user_document",
        return_value=fake_document,
    ):

        with pytest.raises(ValueError):
            summarize_document(
                user_id=1,
                document_id=6,
            )


def test_summarize_document_when_ollama_unavailable():
    fake_document = {
        "id": 6,
        "filename": "MindSync.docx",
        "file_path": "data/uploads/mindsync.docx",
        "extracted_text_path": (
            "data/extracted/document_6.txt"
        ),
        "extraction_status": "completed",
        "title": None,
    }

    with patch(
        "app.services.summary_service.get_user_document",
        return_value=fake_document,
    ), patch(
        "app.services.summary_service.read_extracted_text",
        return_value="Some document content.",
    ), patch(
        "app.services.summary_service.is_ollama_available",
        return_value=False,
    ), patch(
        "app.services.summary_service.get_ollama_model",
        return_value="llama3.2:3b",
    ):

        result = summarize_document(
            user_id=1,
            document_id=6,
        )

    assert result["mode"] == "unavailable"
    assert result["ollama_available"] is False
    assert "unavailable" in result["summary"].lower()