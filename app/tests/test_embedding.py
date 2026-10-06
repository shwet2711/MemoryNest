import pytest

from app.services.embedding_config import (
    get_embedding_dimension,
    get_embedding_model_name,
)
from app.services.embedding_service import (
    generate_embedding,
    generate_embeddings,
    get_embedding_dimension as service_embedding_dimension,
)


def test_embedding_model_name():
    model_name = get_embedding_model_name()

    assert isinstance(model_name, str)
    assert len(model_name) > 0


def test_configured_embedding_dimension():
    dimension = get_embedding_dimension()

    assert isinstance(dimension, int)
    assert dimension > 0


def test_generate_embedding():
    embedding = generate_embedding(
        "MemoryNest stores personal knowledge."
    )

    assert isinstance(embedding, list)
    assert len(embedding) > 0
    assert all(isinstance(value, float) for value in embedding)


def test_embedding_dimension_matches_vector():
    embedding = generate_embedding(
        "MemoryNest OCR test."
    )

    dimension = service_embedding_dimension()

    assert len(embedding) == dimension


def test_generate_multiple_embeddings():
    texts = [
        "MemoryNest personal knowledge system.",
        "Document retrieval using embeddings.",
        "Artificial intelligence and RAG.",
    ]

    embeddings = generate_embeddings(texts)

    assert len(embeddings) == 3

    dimension = service_embedding_dimension()

    for embedding in embeddings:
        assert len(embedding) == dimension


def test_empty_text_rejected():
    with pytest.raises(ValueError):
        generate_embedding("")


def test_non_string_rejected():
    with pytest.raises(TypeError):
        generate_embedding(None)