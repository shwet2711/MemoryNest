
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

import fitz
from docx import Document as DocxDocument
from PIL import Image
from sqlalchemy.orm import Session

from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.services.ocr_service import extract_image_text
from app.services.pdf_service import extract_pdf_with_ocr


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

UPLOAD_DIR = (
    PROJECT_ROOT
    / "data"
    / "uploads"
)

EXTRACTED_DIR = (
    PROJECT_ROOT
    / "data"
    / "extracted"
)

CHUNK_OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "chunks"
)

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

EXTRACTED_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CHUNK_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
}

MAX_FILE_SIZE = 20 * 1024 * 1024


def validate_file(
    filename: str,
    file_size: int,
) -> tuple[bool, str]:

    if not filename:
        return False, "Filename is missing."

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:

        allowed = ", ".join(
            sorted(ALLOWED_EXTENSIONS)
        )

        return (
            False,
            f"Unsupported file type. Allowed: {allowed}",
        )

    if file_size <= 0:
        return False, "The uploaded file is empty."

    if file_size > MAX_FILE_SIZE:

        return (
            False,
            "File is too large. "
            "Maximum allowed size is 20 MB.",
        )

    return True, ""


def sanitize_filename(
    filename: str,
) -> str:

    original = Path(
        filename
    ).name

    cleaned = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        original,
    )

    return cleaned[:180]


def calculate_file_hash(
    file_path: Path,
) -> str:

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:

        while True:

            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def extract_pdf_text(
    file_path: Path,
) -> str:

    pages = extract_pdf_with_ocr(
        file_path
    )

    sections = []

    for page in pages:

        if page["text"].strip():

            sections.append(
                f"\n--- Page "
                f"{page['page_number']} ---\n"
            )

            sections.append(
                page["text"]
            )

    return "\n".join(
        sections
    ).strip()


def extract_docx_text(
    file_path: Path,
) -> str:

    document = DocxDocument(
        file_path
    )

    paragraphs = []

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:
            paragraphs.append(text)

    return "\n".join(
        paragraphs
    ).strip()


def extract_txt_text(
    file_path: Path,
) -> str:

    encodings = [
        "utf-8",
        "utf-8-sig",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:

        try:

            return file_path.read_text(
                encoding=encoding
            ).strip()

        except UnicodeDecodeError:
            continue

    raise ValueError(
        "Unable to decode text file."
    )


def validate_image(
    file_path: Path,
) -> dict:

    with Image.open(
        file_path
    ) as image:

        return {
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
        }


def extract_text(
    file_path: Path,
) -> tuple[str, str]:

    extension = file_path.suffix.lower()

    # ---------------------------------------------------------
    # PDF
    # ---------------------------------------------------------

    if extension == ".pdf":

        text = extract_pdf_text(
            file_path
        )

        if text:
            return text, "completed"

        return "", "ocr_required"

    # ---------------------------------------------------------
    # DOCX
    # ---------------------------------------------------------

    if extension == ".docx":

        text = extract_docx_text(
            file_path
        )

        if text:
            return text, "completed"

        return "", "empty"

    # ---------------------------------------------------------
    # TXT
    # ---------------------------------------------------------

    if extension == ".txt":

        text = extract_txt_text(
            file_path
        )

        if text:
            return text, "completed"

        return "", "empty"

    # ---------------------------------------------------------
    # IMAGE
    # ---------------------------------------------------------

    if extension in {
        ".jpg",
        ".jpeg",
        ".png",
    }:

        validate_image(
            file_path
        )

        text = extract_image_text(
            file_path
        )

        if text:
            return text, "completed"

        return "", "ocr_failed"

    raise ValueError(
        f"Unsupported file extension: {extension}"
    )


def save_extracted_text(
    document_id: int,
    text: str,
) -> Path:

    output_path = (
        EXTRACTED_DIR
        / f"document_{document_id}.txt"
    )

    output_path.write_text(
        text,
        encoding="utf-8",
    )

    return output_path


def create_document(
    db: Session,
    user_id: int,
    filename: str,
    file_bytes: bytes,
) -> Document:

    file_size = len(
        file_bytes
    )

    valid, error = validate_file(
        filename,
        file_size,
    )

    if not valid:
        raise ValueError(error)

    safe_name = sanitize_filename(
        filename
    )

    extension = Path(
        safe_name
    ).suffix.lower()

    unique_id = uuid.uuid4().hex

    stored_filename = (
        f"{unique_id}{extension}"
    )

    file_path = (
        UPLOAD_DIR
        / stored_filename
    )

    file_path.write_bytes(
        file_bytes
    )

    try:

        document = Document(
            user_id=user_id,
            original_filename=filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            file_type=extension.lstrip(
                "."
            ),
            file_size=file_size,
            title=Path(
                filename
            ).stem,
            extraction_status="processing",
        )

        db.add(document)

        db.flush()

        text, status = extract_text(
            file_path
        )

        document.extraction_status = status

        if text:

            extracted_path = (
                save_extracted_text(
                    document.id,
                    text,
                )
            )

            document.extracted_text_path = (
                str(extracted_path)
            )

        db.commit()

        db.refresh(
            document
        )

        return document

    except Exception:

        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise


def get_user_documents(
    db: Session,
    user_id: int,
) -> list[Document]:

    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id
        )
        .order_by(
            Document.created_at.desc()
        )
        .all()
    )


def get_document(
    db: Session,
    user_id: int,
    document_id: int,
) -> Document | None:

    return (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .first()
    )


def delete_document(
    db: Session,
    user_id: int,
    document_id: int,
) -> bool:

    document = get_document(
        db,
        user_id,
        document_id,
    )

    if document is None:
        return False

    # Delete chunks.
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id
            == document_id,
            DocumentChunk.user_id
            == user_id,
        )
        .all()
    )

    for chunk in chunks:
        db.delete(chunk)

    # Delete uploaded file.
    file_path = Path(
        document.file_path
    )

    if file_path.exists():
        file_path.unlink()

    # Delete extracted text.
    if document.extracted_text_path:

        text_path = Path(
            document.extracted_text_path
        )

        if text_path.exists():
            text_path.unlink()

    # Delete chunk preview file.
    chunk_output_path = (
        CHUNK_OUTPUT_DIR
        / f"document_{document.id}_chunks.txt"
    )

    if chunk_output_path.exists():
        chunk_output_path.unlink()

    # Delete database record.
    db.delete(document)

    db.commit()

    return True
