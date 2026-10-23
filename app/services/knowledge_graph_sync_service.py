from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.db.knowledge_graph_sync_model import (
    KnowledgeGraphSyncJob,
    utc_now_naive,
)


def enqueue_sync_job(
    db: Session,
    *,
    user_id: int,
    document_id: int,
    reset_completed: bool = True,
) -> KnowledgeGraphSyncJob:
    """Create or reuse a persistent job to synchronize one document."""
    job = (
        db.query(KnowledgeGraphSyncJob)
        .filter(
            KnowledgeGraphSyncJob.user_id == user_id,
            KnowledgeGraphSyncJob.document_id == document_id,
            KnowledgeGraphSyncJob.operation == "sync",
        )
        .first()
    )

    if job is None:
        job = KnowledgeGraphSyncJob(
            user_id=user_id,
            document_id=document_id,
            operation="sync",
            status="pending",
            attempt_count=0,
            next_attempt_at=utc_now_naive(),
        )
        db.add(job)
    elif not reset_completed:
        return job
    else:
        job.status = "pending"
        job.attempt_count = 0
        job.last_error = None
        job.next_attempt_at = utc_now_naive()

    db.flush()
    return job


def enqueue_delete_job(
    db: Session,
    *,
    user_id: int,
    document_id: int,
) -> KnowledgeGraphSyncJob:
    """Queue graph cleanup after a document is deleted."""
    sync_jobs = (
        db.query(KnowledgeGraphSyncJob)
        .filter(
            KnowledgeGraphSyncJob.user_id == user_id,
            KnowledgeGraphSyncJob.document_id == document_id,
            KnowledgeGraphSyncJob.operation == "sync",
        )
        .all()
    )

    for sync_job in sync_jobs:
        sync_job.status = "cancelled"

    job = (
        db.query(KnowledgeGraphSyncJob)
        .filter(
            KnowledgeGraphSyncJob.user_id == user_id,
            KnowledgeGraphSyncJob.document_id == document_id,
            KnowledgeGraphSyncJob.operation == "delete",
        )
        .first()
    )

    if job is None:
        job = KnowledgeGraphSyncJob(
            user_id=user_id,
            document_id=document_id,
            operation="delete",
            status="pending",
            attempt_count=0,
            next_attempt_at=utc_now_naive(),
        )
        db.add(job)
    else:
        job.status = "pending"
        job.attempt_count = 0
        job.last_error = None
        job.next_attempt_at = utc_now_naive()

    db.flush()
    return job


def backfill_existing_documents(db: Session) -> int:
    """Queue existing documents with chunks, preserving completed jobs."""
    document_rows = (
        db.query(
            Document.id,
            Document.user_id,
        )
        .join(
            DocumentChunk,
            (DocumentChunk.document_id == Document.id)
            & (DocumentChunk.user_id == Document.user_id),
        )
        .distinct()
        .all()
    )

    queued_count = 0

    for document_id, user_id in document_rows:
        job = enqueue_sync_job(
            db,
            user_id=user_id,
            document_id=document_id,
            reset_completed=False,
        )

        if job.status == "pending" and job.attempt_count == 0:
            queued_count += 1

    db.flush()
    return queued_count


def retry_delay_minutes(attempt_count: int) -> int:
    """Return an increasing retry delay, capped at one hour."""
    if attempt_count < 1:
        attempt_count = 1

    return min(60, 2 ** min(attempt_count - 1, 6))


def schedule_job_retry(
    job: KnowledgeGraphSyncJob,
    error: str,
) -> None:
    """Record a failed attempt and schedule the next retry."""
    job.status = "pending"
    job.last_error = error[:4000]
    job.next_attempt_at = utc_now_naive() + timedelta(
        minutes=retry_delay_minutes(job.attempt_count)
    )

def mark_sync_job_completed(
    db: Session,
    *,
    user_id: int,
    document_id: int,
) -> bool:
    """Mark an existing synchronization job completed after a successful sync."""
    job = (
        db.query(KnowledgeGraphSyncJob)
        .filter(
            KnowledgeGraphSyncJob.user_id == user_id,
            KnowledgeGraphSyncJob.document_id == document_id,
            KnowledgeGraphSyncJob.operation == "sync",
        )
        .first()
    )

    if job is None:
        return False

    job.status = "completed"
    job.last_error = None
    job.next_attempt_at = utc_now_naive()
    db.flush()

    return True