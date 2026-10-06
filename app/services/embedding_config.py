from __future__ import annotations

import os


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def get_embedding_model_name() -> str:
    """Return the configured embedding model name."""
    return os.getenv(
        "MEMORYNEST_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    )


def get_embedding_dimension() -> int:
    """Return the embedding dimension for the default model."""
    model_name = get_embedding_model_name()

    dimensions = {
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

    return dimensions.get(model_name, 384)