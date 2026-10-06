
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.chunk_model import DocumentChunk
from app.db.embedding_model import ChunkEmbedding

from app.services.embedding_config import get_embedding_model_name
from app.services.embedding_service import (
    generate_embeddings,
    get_embedding_dimension,
)

from app.services.vector_store import (
    add_embeddings,
    delete_embedding,
)


def index_document(
    db: Session,
    document_id: int,
    user_id: int,
    batch_size: int = 32,
) -> dict:
    """
    Index every chunk of a document.

    ChromaDB stores the actual vectors.
    SQLite stores their metadata and vector IDs.

    Repeated indexing updates existing vector IDs.
    """

    if document_id < 1 or user_id < 1:
        raise ValueError("Document ID and user ID must be positive.")

    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == user_id,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    if not chunks:
        return {
            "document_id": document_id,
            "total_chunks": 0,
            "indexed": 0,
            "status": "no_chunks",
        }

    records = (
        db.query(ChunkEmbedding)
        .filter(
            ChunkEmbedding.document_id == document_id,
            ChunkEmbedding.user_id == user_id,
        )
        .all()
    )

    records_by_chunk = {
        record.chunk_id: record
        for record in records
    }

    model_name = get_embedding_model_name()
    dimension = get_embedding_dimension()

    indexed_count = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]

        texts = [chunk.content for chunk in batch]

        vectors = generate_embeddings(texts)

        vector_ids = [f"chunk_{chunk.id}" for chunk in batch]

        # Store/update vectors first.
        add_embeddings(
            vector_ids=vector_ids,
            embeddings=vectors,
            document_ids=[chunk.document_id for chunk in batch],
            chunk_ids=[chunk.id for chunk in batch],
            user_ids=[chunk.user_id for chunk in batch],
            source_filenames=[
                chunk.source_filename for chunk in batch
            ],
            chunk_indexes=[chunk.chunk_index for chunk in batch],
            contents=texts,
        )

        # Synchronize SQLite metadata.
        for chunk, vector_id in zip(
            batch,
            vector_ids,
            strict=True,
        ):
            record = records_by_chunk.get(chunk.id)

            if record is None:
                record = ChunkEmbedding(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    user_id=chunk.user_id,
                    model_name=model_name,
                    dimension=dimension,
                    vector_store="chroma",
                    vector_id=vector_id,
                )
                db.add(record)
                records_by_chunk[chunk.id] = record
            else:
                record.model_name = model_name
                record.dimension = dimension
                record.vector_store = "chroma"
                record.vector_id = vector_id

        db.commit()

        indexed_count += len(batch)

    # Remove metadata for chunks that no longer exist.
    current_chunk_ids = {chunk.id for chunk in chunks}

    stale_records = [
        record
        for record in records
        if record.chunk_id not in current_chunk_ids
    ]

    for record in stale_records:
        if record.vector_id:
            delete_embedding(record.vector_id)

        db.delete(record)

    if stale_records:
        db.commit()

    return {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "indexed": indexed_count,
        "status": "completed",
    }