
from __future__ import annotations

from functools import lru_cache

import chromadb

from app.services.vector_config import (
    get_chroma_path,
    get_collection_name,
)


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    """Create and reuse the persistent ChromaDB client."""

    return chromadb.PersistentClient(
        path=str(get_chroma_path())
    )


@lru_cache(maxsize=1)
def get_collection():
    """Get or create the MemoryNest vector collection."""

    return get_chroma_client().get_or_create_collection(
        name=get_collection_name(),
        metadata={
            "description": "MemoryNest document chunk embeddings",
            "hnsw:space": "cosine",
        },
    )


def add_embeddings(
    vector_ids: list[str],
    embeddings: list[list[float]],
    document_ids: list[int],
    chunk_ids: list[int],
    user_ids: list[int],
    source_filenames: list[str],
    chunk_indexes: list[int],
    contents: list[str],
) -> None:
    """Insert or update document chunk vectors."""

    values = [
        vector_ids,
        embeddings,
        document_ids,
        chunk_ids,
        user_ids,
        source_filenames,
        chunk_indexes,
        contents,
    ]

    if not vector_ids:
        return

    if len({len(value) for value in values}) != 1:
        raise ValueError(
            "All embedding data lists must have equal lengths."
        )

    if any(not value.strip() for value in contents):
        raise ValueError("Chunk contents cannot be empty.")

    metadata = []

    for document_id, chunk_id, user_id, filename, index in zip(
        document_ids,
        chunk_ids,
        user_ids,
        source_filenames,
        chunk_indexes,
        strict=True,
    ):
        metadata.append(
            {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "user_id": user_id,
                "source_filename": filename,
                "chunk_index": index,
            }
        )

    get_collection().upsert(
        ids=vector_ids,
        embeddings=embeddings,
        documents=contents,
        metadatas=metadata,
    )


def get_collection_count() -> int:
    return get_collection().count()


def get_vector(vector_id: str) -> dict:
    """Retrieve a stored vector's content and metadata."""

    return get_collection().get(
        ids=[vector_id],
        include=["documents", "metadatas"],
    )


def delete_embedding(vector_id: str) -> None:
    get_collection().delete(ids=[vector_id])


def delete_document_embeddings(
    document_id: int,
    user_id: int | None = None,
) -> int:
    """Delete vectors for a document, optionally scoped to a user."""

    filters = [{"document_id": document_id}]

    if user_id is not None:
        filters.append({"user_id": user_id})

    where = filters[0] if len(filters) == 1 else {"$and": filters}

    collection = get_collection()

    result = collection.get(
        where=where,
        include=[],
    )

    ids = result.get("ids", [])

    if ids:
        collection.delete(ids=ids)

    return len(ids)


def delete_user_embeddings(user_id: int) -> int:
    """Delete all vectors belonging to a user."""

    collection = get_collection()

    result = collection.get(
        where={"user_id": user_id},
        include=[],
    )

    ids = result.get("ids", [])

    if ids:
        collection.delete(ids=ids)

    return len(ids)