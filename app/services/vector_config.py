from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

DEFAULT_COLLECTION_NAME = "memorynest_documents"


def get_chroma_path() -> Path:
    """Return the persistent ChromaDB directory."""

    configured_path = os.getenv("MEMORYNEST_CHROMA_PATH")

    if configured_path:
        path = Path(configured_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path
    else:
        path = DEFAULT_CHROMA_PATH

    path.mkdir(parents=True, exist_ok=True)

    return path


def get_collection_name() -> str:
    """Return the ChromaDB collection name."""

    return os.getenv(
        "MEMORYNEST_CHROMA_COLLECTION",
        DEFAULT_COLLECTION_NAME,
    )