from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.services.embedding_config import get_embedding_model_name


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """
    Load the embedding model once and reuse it.
    """

    model_name = get_embedding_model_name()

    return SentenceTransformer(model_name)


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for one text string.
    """

    if not isinstance(text, str):
        raise TypeError("Text must be a string.")

    cleaned_text = text.strip()

    if not cleaned_text:
        raise ValueError("Text cannot be empty.")

    model = get_embedding_model()

    embedding = model.encode(
        cleaned_text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embedding vectors for multiple texts.
    """

    if not isinstance(texts, list):
        raise TypeError("texts must be a list.")

    cleaned_texts = [text.strip() for text in texts]

    if any(not text for text in cleaned_texts):
        raise ValueError("Texts cannot contain empty values.")

    if not cleaned_texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode(
        cleaned_texts,
        normalize_embeddings=True,
    )

    return embeddings.tolist()


def get_embedding_dimension() -> int:
    """
    Return the dimension of the generated embedding vector.
    """

    model = get_embedding_model()

    return model.get_embedding_dimension()