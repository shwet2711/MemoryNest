
from __future__ import annotations

from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from app.services.ocr_service import (
    configure_tesseract,
)


def extract_pdf_with_ocr(
    file_path: Path,
) -> list[dict]:
    """
    Extract PDF content page-by-page.

    Selectable text is extracted directly.
    Image-only pages are rendered and processed using OCR.

    Each result contains:
    - page_number
    - text
    - method
    """

    configure_tesseract()

    pages = []

    with fitz.open(file_path) as pdf:

        for page_number, page in enumerate(
            pdf,
            start=1,
        ):

            text = page.get_text(
                "text"
            ).strip()

            if text:

                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "method": "text",
                    }
                )

                continue

            # -------------------------------------------------
            # OCR FALLBACK
            # -------------------------------------------------

            try:

                matrix = fitz.Matrix(
                    2.0,
                    2.0,
                )

                pixmap = page.get_pixmap(
                    matrix=matrix,
                    alpha=False,
                )

                image_bytes = pixmap.tobytes(
                    "png"
                )

                from io import BytesIO

                with Image.open(
                    BytesIO(image_bytes)
                ) as image:

                    if image.mode not in (
                        "RGB",
                        "L",
                    ):
                        image = image.convert(
                            "RGB"
                        )

                    ocr_text = (
                        pytesseract.image_to_string(
                            image,
                            lang="eng",
                        )
                        .strip()
                    )

                pages.append(
                    {
                        "page_number": page_number,
                        "text": ocr_text,
                        "method": (
                            "ocr"
                            if ocr_text
                            else "ocr_failed"
                        ),
                    }
                )

            except Exception:

                pages.append(
                    {
                        "page_number": page_number,
                        "text": "",
                        "method": "ocr_failed",
                    }
                )

    return pages
