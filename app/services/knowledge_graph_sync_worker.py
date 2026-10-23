from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import NEO4J_ENABLED
from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.db.knowledge_graph_sync_model import (
    KnowledgeGraphSyncJob,
    utc_now_naive,
)
from app.db.session import SessionLocal
from app.services.knowledge_graph_pipeline_service import (
    process_chunk_for_knowledge_graph,
)
from app.services.knowledge_graph_service import (
    check_neo4j_connection,
    delete_document_relationships,
)
from app.services.knowledge_graph_sync_service import schedule_job_retry

logger = logging.getLogger(__name__)

STALE_JOB_TIMEOUT_MINUTES = 30


def process_sync_job(
    db: Session,
    job: KnowledgeGraphSyncJob,
) -> None:
    """Synchronize all reliable chunks for one existing document."""
    document = (
        db.query(Document)
        .filter(
            Document.id == job.document_id,
            Document.user_id == job.user_id,
        )
        .first()
    )

    # Never recreate graph data for a document that has been deleted.
    if document is None:
        job.status = "cancelled"
        job.last_error = None
        return

    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == job.document_id,
            DocumentChunk.user_id == job.user_id,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    if not chunks:
        job.status = "completed"
        job.last_error = None
        return

    connection = check_neo4j_connection()
    if not connection.get("available", False):
        raise RuntimeError("Neo4j is unavailable.")

    for chunk in chunks:
        extraction_method = (
            getattr(chunk, "extraction_method", "text") or "text"
        )

        # Do not replace relationships using unreliable OCR output.
        if extraction_method == "ocr_low_confidence":
            continue

        process_chunk_for_knowledge_graph(
            user_id=job.user_id,
            document_id=job.document_id,
            chunk_index=chunk.chunk_index,
            text=chunk.content,
            source_filename=chunk.source_filename,
        )

    job.status = "completed"
    job.last_error = None


def process_delete_job(
    job: KnowledgeGraphSyncJob,
) -> None:
    """Remove graph relationships for a deleted document."""
    delete_document_relationships(
        user_id=job.user_id,
        document_id=job.document_id,
    )


def recover_stale_jobs(db: Session) -> int:
    """Return jobs abandoned in processing for at least 30 minutes to pending."""
    now = utc_now_naive()
    stale_before = now - timedelta(minutes=STALE_JOB_TIMEOUT_MINUTES)

    recovered = (
        db.query(KnowledgeGraphSyncJob)
        .filter(
            KnowledgeGraphSyncJob.status == "processing",
            KnowledgeGraphSyncJob.updated_at <= stale_before,
        )
        .update(
            {
                KnowledgeGraphSyncJob.status: "pending",
                KnowledgeGraphSyncJob.next_attempt_at: now,
                KnowledgeGraphSyncJob.last_error: (
                    "Recovered after an interrupted processing attempt."
                ),
                KnowledgeGraphSyncJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    return recovered


def _claim_job(job_id: int) -> bool:
    """Atomically claim one pending, due job."""
    now = utc_now_naive()

    with SessionLocal() as db:
        claimed = (
            db.query(KnowledgeGraphSyncJob)
            .filter(
                KnowledgeGraphSyncJob.id == job_id,
                KnowledgeGraphSyncJob.status == "pending",
                KnowledgeGraphSyncJob.next_attempt_at <= now,
            )
            .update(
                {
                    KnowledgeGraphSyncJob.status: "processing",
                    KnowledgeGraphSyncJob.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return claimed == 1


def process_due_jobs(
    *,
    limit: int = 10,
) -> int:
    """Recover abandoned jobs and process due work in independent sessions."""
    if not NEO4J_ENABLED:
        return 0

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    with SessionLocal() as db:
        recover_stale_jobs(db)

        now = utc_now_naive()
        jobs = (
            db.query(KnowledgeGraphSyncJob.id)
            .filter(
                KnowledgeGraphSyncJob.status == "pending",
                KnowledgeGraphSyncJob.next_attempt_at <= now,
            )
            .order_by(
                KnowledgeGraphSyncJob.next_attempt_at,
                KnowledgeGraphSyncJob.id,
            )
            .limit(limit)
            .all()
        )
        job_ids = [row[0] for row in jobs]

    processed_count = 0

    for job_id in job_ids:
        if not _claim_job(job_id):
            # Another worker may already have claimed this job.
            continue

        try:
            with SessionLocal() as db:
                job = db.get(KnowledgeGraphSyncJob, job_id)
                if job is None or job.status != "processing":
                    continue

                if job.operation == "delete":
                    process_delete_job(job)
                    job.status = "completed"
                    job.last_error = None
                elif job.operation == "sync":
                    process_sync_job(db, job)
                else:
                    raise ValueError(
                        f"Unsupported graph operation: {job.operation}"
                    )

                db.commit()
                processed_count += 1

        except Exception as exc:
            logger.exception(
                "Knowledge graph job %s failed; scheduling retry.",
                job_id,
            )

            with SessionLocal() as db:
                job = db.get(KnowledgeGraphSyncJob, job_id)
                if job is not None and job.status == "processing":
                    job.attempt_count += 1
                    schedule_job_retry(job, str(exc))
                    db.commit()

    return processed_count
