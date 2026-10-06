from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.ocr_service import check_tesseract, extract_image_text


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

    extracted_text = extract_image_text(image_path)

    assert isinstance(extracted_text, str)
    assert len(extracted_text) > 0

    normalized_text = extracted_text.lower()

    assert "memorynest" in normalized_text
    assert "ocr" in normalized_text

    if image_path.exists():
        image_path.unlink()