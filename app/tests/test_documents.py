from pathlib import Path

from app.services.document_service import (
    sanitize_filename,
    validate_file,
)


def test_valid_pdf():

    valid, error = validate_file(
        "resume.pdf",
        1024,
    )

    assert valid is True
    assert error == ""


def test_valid_docx():

    valid, error = validate_file(
        "project.docx",
        1024,
    )

    assert valid is True
    assert error == ""


def test_invalid_file_type():

    valid, error = validate_file(
        "virus.exe",
        1024,
    )

    assert valid is False
    assert "Unsupported" in error


def test_empty_file():

    valid, error = validate_file(
        "notes.txt",
        0,
    )

    assert valid is False


def test_large_file():

    valid, error = validate_file(
        "large.pdf",
        21 * 1024 * 1024,
    )

    assert valid is False


def test_filename_sanitization():

    filename = sanitize_filename(
        "My Resume 2026!.pdf"
    )

    assert filename == "My_Resume_2026_.pdf"