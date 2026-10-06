
from app.services.text_processor import (
    create_chunks,
    normalize_text,
    split_into_paragraphs,
    split_long_text,
)


def test_normalize_text():
    text = (
        "Hello   world.\r\n"
        "\r\n"
        "\r\n"
        "This   is   MemoryNest."
    )

    result = normalize_text(text)

    assert result == (
        "Hello world.\n\n"
        "This is MemoryNest."
    )


def test_split_into_paragraphs():
    text = (
        "First paragraph.\n\n"
        "Second paragraph.\n\n"
        "Third paragraph."
    )

    paragraphs = split_into_paragraphs(text)

    assert len(paragraphs) == 3
    assert paragraphs[0] == "First paragraph."
    assert paragraphs[1] == "Second paragraph."
    assert paragraphs[2] == "Third paragraph."


def test_split_long_text():
    text = "A" * 250

    chunks = split_long_text(
        text,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert len(chunks) == 3

    assert len(chunks[0]) == 100
    assert len(chunks[1]) == 100
    assert len(chunks[2]) == 90


def test_create_chunks():
    text = (
        "MemoryNest is a personal knowledge system.\n\n"
        "It stores documents and extracts useful information.\n\n"
        "The system will later use embeddings and retrieval."
    )

    chunks = create_chunks(
        text,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk.strip()


def test_create_chunks_empty_text():
    chunks = create_chunks("")

    assert chunks == []


def test_invalid_chunk_size():
    try:
        split_long_text(
            "Hello",
            chunk_size=0,
            chunk_overlap=0,
        )
        assert False
    except ValueError as error:
        assert "chunk_size" in str(error)


def test_invalid_overlap():
    try:
        split_long_text(
            "Hello",
            chunk_size=100,
            chunk_overlap=100,
        )
        assert False
    except ValueError as error:
        assert "chunk_overlap" in str(error)
