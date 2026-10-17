
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image


DEFAULT_TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def configure_tesseract() -> None:
    """Configure Tesseract when it exists at the default location."""
    configured_path = Path(DEFAULT_TESSERACT_PATH)

    if configured_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(configured_path)


def check_tesseract() -> tuple[bool, str]:
    """Check whether Tesseract OCR is available."""
    configure_tesseract()

    try:
        version = pytesseract.get_tesseract_version()
        return True, str(version)
    except Exception as error:
        return False, str(error)


def extract_image_text_with_confidence(
    image: Image.Image,
) -> tuple[str, float | None]:
    """
    Extract text and calculate mean confidence for recognized words.

    Returns:
        (extracted_text, mean_confidence)

    Confidence is on a 0–100 scale. None means no valid word
    confidence values were available. Confidence is not a spelling
    accuracy guarantee.
    """
    configure_tesseract()

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    text = pytesseract.image_to_string(
        image,
        lang="eng",
    ).strip()

    data = pytesseract.image_to_data(
        image,
        lang="eng",
        output_type=pytesseract.Output.DICT,
    )

    confidences: list[float] = []

    for word, raw_confidence in zip(
        data.get("text", []),
        data.get("conf", []),
    ):
        if not word.strip():
            continue

        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            continue

        # Tesseract uses negative confidence values for invalid entries.
        if confidence >= 0:
            confidences.append(confidence)

    mean_confidence = (
        round(sum(confidences) / len(confidences), 2)
        if confidences
        else None
    )

    return text, mean_confidence


def extract_image_text(image_path: Path) -> str:
    """Extract text from an image, preserving the existing API."""
    configure_tesseract()

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image file not found: {image_path}"
        )

    with Image.open(image_path) as image:
        text, _ = extract_image_text_with_confidence(image)

    return text
