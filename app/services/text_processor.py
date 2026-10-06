
from __future__ import annotations

import re


# Default chunk configuration.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


def normalize_text(text: str) -> str:
    """
    Clean extracted document text.

    The function:
    - normalizes line endings
    - removes null characters
    - removes excessive spaces
    - reduces excessive blank lines
    - keeps paragraph structure
    """

    if not text:
        return ""

    # Normalize Windows / old-style line endings.
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove null characters.
    text = text.replace("\x00", "")

    # Replace tabs with spaces.
    text = text.replace("\t", " ")

    # Remove trailing spaces from each line.
    lines = [
        line.rstrip()
        for line in text.split("\n")
    ]

    text = "\n".join(lines)

    # Reduce repeated spaces.
    text = re.sub(r"[ ]{2,}", " ", text)

    # Reduce excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_into_paragraphs(text: str) -> list[str]:
    """
    Split normalized text into meaningful paragraphs.
    """

    if not text:
        return []

    paragraphs = re.split(
        r"\n\s*\n",
        text,
    )

    return [
        paragraph.strip()
        for paragraph in paragraphs
        if paragraph.strip()
    ]


def split_long_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split long text using a sliding window.

    This is used when an individual paragraph is
    larger than the configured chunk size.
    """

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than 0."
        )

    if chunk_overlap < 0:
        raise ValueError(
            "chunk_overlap cannot be negative."
        )

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size."
        )

    chunks = []

    start = 0
    text_length = len(text)

    step = chunk_size - chunk_overlap

    while start < text_length:

        end = min(
            start + chunk_size,
            text_length,
        )

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start += step

    return chunks


def create_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Create semantically useful chunks from extracted text.

    Paragraphs are kept together whenever possible.
    Very large paragraphs are split using overlap.
    """

    normalized = normalize_text(text)

    if not normalized:
        return []

    paragraphs = split_into_paragraphs(normalized)

    chunks: list[str] = []
    current_chunk = ""

    for paragraph in paragraphs:

        # If the paragraph itself is larger than the
        # chunk size, first flush the current chunk.
        if len(paragraph) > chunk_size:

            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            long_chunks = split_long_text(
                paragraph,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            chunks.extend(long_chunks)

            continue

        # First paragraph in a chunk.
        if not current_chunk:
            current_chunk = paragraph
            continue

        # Try adding the next paragraph.
        candidate = (
            f"{current_chunk}\n\n{paragraph}"
        )

        if len(candidate) <= chunk_size:
            current_chunk = candidate

        else:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph

    # Add remaining content.
    if current_chunk:
        chunks.append(current_chunk.strip())

    return [
        chunk
        for chunk in chunks
        if chunk
    ]
