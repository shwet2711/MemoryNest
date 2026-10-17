from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.ocr_service import check_tesseract
from app.services.pdf_service import extract_pdf_with_ocr


def create_scanned_pdf(pdf_path: Path) -> Path:
    """Create an image-only PDF containing readable sample text."""
    image = Image.new("RGB", (1600, 600), "white")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()

    draw.text(
        (60, 70),
        "MemoryNest Scanned PDF Test",
        fill="black",
        font=font,
    )
    draw.text(
        (60, 190),
        "Python SQLite document search and retrieval",
        fill="black",
        font=font,
    )
    draw.text(
        (60, 310),
        "Reliable text extraction preserves original content.",
        fill="black",
        font=font,
    )

    image_bytes_path = pdf_path.with_suffix(".png")

    try:
        image.save(image_bytes_path)

        with fitz.open() as pdf:
            page = pdf.new_page(width=800, height=300)
            page.insert_image(
                page.rect,
                filename=str(image_bytes_path),
            )
            pdf.save(pdf_path)
    finally:
        image_bytes_path.unlink(missing_ok=True)

    return pdf_path


def test_scanned_pdf_uses_ocr_and_returns_metadata(tmp_path):
    available, message = check_tesseract()
    if not available:
        pytest.skip(f"Tesseract is not available: {message}")

    pdf_path = create_scanned_pdf(tmp_path / "scanned_test.pdf")

    # Verify that this is genuinely an image-only PDF.
    with fitz.open(pdf_path) as pdf:
        assert len(pdf) == 1
        assert pdf[0].get_text("text").strip() == ""

    pages = extract_pdf_with_ocr(pdf_path)

    assert len(pages) == 1

    result = pages[0]
    assert result["page_number"] == 1
    assert result["method"] == "ocr"
    assert "MemoryNest" in result["text"]
    assert "SQLite" in result["text"]
    assert result["ocr_confidence"] is not None
    assert 0 <= result["ocr_confidence"] <= 100
    assert result["quality_score"] > 0
    assert result["quality_reasons"] == []


def test_scanned_pdf_preserves_low_confidence_text(
    tmp_path,
    monkeypatch,
):
    from app.services import pdf_service

    pdf_path = create_scanned_pdf(tmp_path / "low_confidence_test.pdf")

    monkeypatch.setattr(
        pdf_service,
        "extract_image_text_with_confidence",
        lambda image: (
            "MemoryNest extracted sample text that should be preserved.",
            25.0,
        ),
    )

    pages = pdf_service.extract_pdf_with_ocr(pdf_path)

    assert len(pages) == 1
    result = pages[0]

    assert result["text"] == (
        "MemoryNest extracted sample text that should be preserved."
    )
    assert result["method"] == "ocr_low_confidence"
    assert result["ocr_confidence"] == 25.0
    assert "low_ocr_confidence" in result["quality_reasons"]
