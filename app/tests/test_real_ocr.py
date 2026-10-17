
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.ocr_quality_service import assess_ocr_text
from app.services.ocr_service import (
    check_tesseract,
    extract_image_text,
    extract_image_text_with_confidence,
)


TEST_IMAGE = Path("data") / "ocr_test.png"


def create_test_image() -> Path:
    TEST_IMAGE.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()

    draw.text(
        (60, 80),
        "MemoryNest OCR Test",
        fill="black",
        font=font,
    )

    draw.text(
        (60, 180),
        "Personal Knowledge Management",
        fill="black",
        font=font,
    )

    image.save(TEST_IMAGE)
    return TEST_IMAGE


def test_real_image_ocr():
    available, message = check_tesseract()

    if not available:
        pytest.skip(f"Tesseract is not available: {message}")

    image_path = create_test_image()

    try:
        extracted_text = extract_image_text(image_path)

        assert isinstance(extracted_text, str)
        assert len(extracted_text) > 0

        normalized_text = extracted_text.lower()

        assert "memorynest" in normalized_text
        assert "ocr" in normalized_text
    finally:
        image_path.unlink(missing_ok=True)


def test_real_image_ocr_returns_confidence():
    available, message = check_tesseract()

    if not available:
        pytest.skip(f"Tesseract is not available: {message}")

    image_path = create_test_image()

    try:
        with Image.open(image_path) as image:
            extracted_text, confidence = (
                extract_image_text_with_confidence(image)
            )

        assert extracted_text
        assert confidence is not None
        assert 0.0 <= confidence <= 100.0
    finally:
        image_path.unlink(missing_ok=True)


def test_ocr_quality_flags_empty_text():
    quality = assess_ocr_text("   ")

    assert quality.is_reliable is False
    assert quality.score == 0.0
    assert "empty_text" in quality.reasons


def test_ocr_quality_flags_short_text():
    quality = assess_ocr_text("OCR test")

    assert quality.is_reliable is False
    assert "too_little_text" in quality.reasons


def test_ocr_quality_does_not_modify_original_text():
    original_text = (
        "MemoryNest uses Python and SQLite to manage "
        "personal documents and searchable knowledge."
    )

    quality = assess_ocr_text(original_text)

    assert quality.is_reliable is True
    assert isinstance(quality.score, float)
    assert original_text == (
        "MemoryNest uses Python and SQLite to manage "
        "personal documents and searchable knowledge."
    )
