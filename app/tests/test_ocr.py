
from pathlib import Path

from app.services.ocr_service import (
    check_tesseract,
)


def test_tesseract_check():

    available, message = check_tesseract()

    assert isinstance(
        available,
        bool,
    )

    assert isinstance(
        message,
        str,
    )


def test_default_tesseract_path():

    expected_path = Path(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    assert (
        expected_path.name
        == "tesseract.exe"
    )
