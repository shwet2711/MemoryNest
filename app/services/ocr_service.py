
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image


DEFAULT_TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def configure_tesseract() -> None:
    """
    Configure the Tesseract executable.

    Uses the standard Windows installation path when
    Tesseract is not already available through PATH.
    """

    configured_path = Path(
        DEFAULT_TESSERACT_PATH
    )

    if configured_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(
            configured_path
        )


def check_tesseract() -> tuple[bool, str]:
    """
    Check whether Tesseract OCR is available.
    """

    configure_tesseract()

    try:
        version = pytesseract.get_tesseract_version()

        return True, str(version)

    except Exception as error:

        return False, str(error)


def extract_image_text(
    image_path: Path,
) -> str:
    """
    Extract text from an image using Tesseract OCR.
    """

    configure_tesseract()

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image file not found: {image_path}"
        )

    with Image.open(image_path) as image:

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        text = pytesseract.image_to_string(
            image,
            lang="eng",
        )

    return text.strip()
