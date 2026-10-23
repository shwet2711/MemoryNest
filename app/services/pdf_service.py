
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf as fitz
from PIL import Image

from app.services.ocr_quality_service import assess_ocr_text
from app.services.ocr_service import (
    configure_tesseract,
    extract_image_text_with_confidence,
)


# OCR confidence ranges from 0 to 100.
# Pages below this threshold are retained but flagged as unreliable.
MIN_OCR_CONFIDENCE = 60.0


def extract_pdf_with_ocr(
    file_path: Path,
) -> list[dict]:
    """
    Extract PDF content page by page.

    Selectable text is extracted directly.
    Image-only pages use OCR with a confidence estimate.

    Each page result contains:
    - page_number
    - text
    - method
    - ocr_confidence
    - quality_score
    - quality_reasons

    Low-confidence text is preserved, not silently corrected.
    """

    configure_tesseract()
    pages: list[dict] = []

    with fitz.open(file_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()

            if text:
                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "method": "text",
                        "ocr_confidence": None,
                        "quality_score": None,
                        "quality_reasons": [],
                    }
                )
                continue

            # Render scanned/image-only pages for OCR.
            try:
                matrix = fitz.Matrix(2.0, 2.0)
                pixmap = page.get_pixmap(
                    matrix=matrix,
                    alpha=False,
                )

                image_bytes = pixmap.tobytes("png")

                with Image.open(BytesIO(image_bytes)) as image:
                    if image.mode not in ("RGB", "L"):
                        image = image.convert("RGB")

                    ocr_text, confidence = (
                        extract_image_text_with_confidence(image)
                    )

                quality = assess_ocr_text(ocr_text)

                reasons = list(quality.reasons)

                if confidence is None:
                    reasons.append("ocr_confidence_unavailable")
                elif confidence < MIN_OCR_CONFIDENCE:
                    reasons.append("low_ocr_confidence")

                if not ocr_text:
                    method = "ocr_failed"
                elif reasons:
                    method = "ocr_low_confidence"
                else:
                    method = "ocr"

                pages.append(
                    {
                        "page_number": page_number,
                        "text": ocr_text,
                        "method": method,
                        "ocr_confidence": confidence,
                        "quality_score": quality.score,
                        "quality_reasons": list(dict.fromkeys(reasons)),
                    }
                )

            except Exception:
                pages.append(
                    {
                        "page_number": page_number,
                        "text": "",
                        "method": "ocr_failed",
                        "ocr_confidence": None,
                        "quality_score": 0.0,
                        "quality_reasons": ["ocr_processing_error"],
                    }
                )

    return pages
