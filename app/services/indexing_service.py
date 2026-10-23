
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import NEO4J_ENABLED
from app.db.chunk_model import DocumentChunk
from app.db.embedding_model import ChunkEmbedding
from app.services.embedding_config import get_embedding_model_name
from app.services.embedding_service import (
    generate_embeddings,
    get_embedding_dimension,
)
from app.services.knowledge_graph_pipeline_service import (
    process_chunk_for_knowledge_graph,
)
from app.services.knowledge_graph_service import check_neo4j_connection
from app.services.knowledge_graph_sync_service import (
    enqueue_sync_job,
    mark_sync_job_completed,
)
from app.services.vector_store import (
    add_embeddings,
    delete_embedding,
)

logger = logging.getLogger(__name__)


def index_document(
    db: Session,
    document_id: int,
    user_id: int,
    batch_size: int = 32,
) -> dict:
    """
    Index document chunks in ChromaDB and synchronize SQLite metadata.

    All chunks remain available for vector search, including low-confidence
    OCR chunks. Unreliable OCR chunks are excluded from graph processing.

    Graph work is queued for retry when Neo4j is disabled or unavailable,
    or when any reliable chunk fails graph processing. Graph failures do
    not undo successful vector indexing.
    """

    if (
        isinstance(document_id, bool)
        or not isinstance(document_id, int)
        or document_id < 1
    ):
        raise ValueError("Document ID must be a positive integer.")

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError("User ID must be a positive integer.")

    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size < 1
    ):
        raise ValueError("Batch size must be a positive integer.")

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

    # Preserve vector indexing independently of graph availability.
    # Low-confidence OCR chunks must remain searchable.
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        texts = [chunk.content for chunk in batch]
        vectors = generate_embeddings(texts)
        vector_ids = [f"chunk_{chunk.id}" for chunk in batch]

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

    # Remove stale vector metadata for chunks that no longer exist.
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

    graph_result = {
        "knowledge_graph_status": "disabled",
        "knowledge_graph_processed_chunks": 0,
        "knowledge_graph_failed_chunks": 0,
        "knowledge_graph_skipped_low_confidence_chunks": 0,
        "knowledge_graph_relationships_stored": 0,
    }

    # Queue work when immediate graph synchronization is not possible.
    queue_graph_sync = not NEO4J_ENABLED

    if NEO4J_ENABLED:
        try:
            connection = check_neo4j_connection()
        except Exception:
            logger.exception("Neo4j connection check failed.")
            connection = {"available": False}

        if not connection.get("available", False):
            logger.warning(
                "Knowledge graph skipped for document %s: "
                "Neo4j is unavailable.",
                document_id,
            )

            graph_result["knowledge_graph_status"] = "unavailable"
            queue_graph_sync = True

        else:
            processed_count = 0
            failed_count = 0
            skipped_count = 0
            relationship_count = 0

            for chunk in chunks:
                extraction_method = (
                    getattr(chunk, "extraction_method", "text")
                    or "text"
                )

                # Never replace relationships for unreliable OCR chunks.
                if extraction_method == "ocr_low_confidence":
                    skipped_count += 1

                    logger.info(
                        "Knowledge graph skipped low-confidence OCR "
                        "for document %s, chunk %s.",
                        document_id,
                        chunk.chunk_index,
                    )
                    continue

                try:
                    result = process_chunk_for_knowledge_graph(
                        user_id=user_id,
                        document_id=document_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.content,
                        source_filename=chunk.source_filename,
                    )

                    processed_count += 1
                    relationship_count += result["stored_count"]

                except Exception:
                    failed_count += 1

                    logger.exception(
                        "Knowledge graph processing failed for "
                        "document %s, chunk %s.",
                        document_id,
                        chunk.chunk_index,
                    )

            if skipped_count == len(chunks):
                graph_status = "skipped_low_confidence"
            elif failed_count == 0:
                graph_status = "completed"
            elif processed_count == 0:
                graph_status = "failed"
            else:
                graph_status = "partial_failure"

            graph_result = {
                "knowledge_graph_status": graph_status,
                "knowledge_graph_processed_chunks": processed_count,
                "knowledge_graph_failed_chunks": failed_count,
                "knowledge_graph_skipped_low_confidence_chunks": (
                    skipped_count
                ),
                "knowledge_graph_relationships_stored": (
                    relationship_count
                ),
            }

            if failed_count > 0:
                queue_graph_sync = True

    # Persist retry work or resolve an existing sync job.
    if queue_graph_sync:
        try:
            enqueue_sync_job(
                db,
                user_id=user_id,
                document_id=document_id,
                reset_completed=True,
            )
            db.commit()

        except Exception:
            db.rollback()

            logger.exception(
                "Failed to queue knowledge graph synchronization "
                "for document %s, user %s.",
                document_id,
                user_id,
            )

    elif graph_result["knowledge_graph_status"] in {
        "completed",
        "skipped_low_confidence",
    }:
        try:
            mark_sync_job_completed(
                db,
                user_id=user_id,
                document_id=document_id,
            )
            db.commit()

        except Exception:
            db.rollback()

            logger.exception(
                "Failed to mark knowledge graph synchronization "
                "completed for document %s, user %s.",
                document_id,
                user_id,
            )

    return {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "indexed": indexed_count,
        "status": "completed",
        **graph_result,
    }
