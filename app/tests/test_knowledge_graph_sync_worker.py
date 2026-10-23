from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.db.knowledge_graph_sync_model import (
    KnowledgeGraphSyncJob,
    utc_now_naive,
)
from app.services import knowledge_graph_sync_worker as worker


@pytest.fixture
def worker_session(tmp_path, monkeypatch):
    database_file = tmp_path / "knowledge_graph_worker.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    Document.__table__.create(bind=engine)
    DocumentChunk.__table__.create(bind=engine)
    KnowledgeGraphSyncJob.__table__.create(bind=engine)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)

    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


def add_document(db, document_id=10, user_id=1):
    document = Document(
        id=document_id,
        user_id=user_id,
        original_filename="notes.txt",
        stored_filename=f"stored-{document_id}.txt",
        file_path=f"/temporary/{document_id}.txt",
        file_type="txt",
        file_size=100,
    )
    db.add(document)
    db.flush()
    return document


def add_chunk(
    db,
    *,
    document_id=10,
    user_id=1,
    chunk_index=0,
    extraction_method="text",
):
    chunk = DocumentChunk(
        document_id=document_id,
        user_id=user_id,
        chunk_index=chunk_index,
        source_filename="notes.txt",
        file_type="txt",
        extraction_method=extraction_method,
        content=f"Test content {chunk_index}",
        character_count=20,
    )
    db.add(chunk)
    db.flush()
    return chunk


def add_job(db, *, operation="sync", document_id=10, user_id=1):
    job = KnowledgeGraphSyncJob(
        user_id=user_id,
        document_id=document_id,
        operation=operation,
        status="pending",
        attempt_count=0,
        next_attempt_at=utc_now_naive() - timedelta(seconds=1),
    )
    db.add(job)
    db.commit()
    return job


def test_worker_returns_zero_when_neo4j_is_disabled(
    worker_session, monkeypatch
):
    monkeypatch.setattr(worker, "NEO4J_ENABLED", False)
    add_job(worker_session)

    assert worker.process_due_jobs() == 0

    job = worker_session.query(KnowledgeGraphSyncJob).one()
    assert job.status == "pending"


def test_worker_rejects_invalid_job_limit(worker_session, monkeypatch):
    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)

    for invalid_limit in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            worker.process_due_jobs(limit=invalid_limit)


def test_sync_job_processes_reliable_chunks_and_skips_low_confidence_ocr(
    worker_session, monkeypatch
):
    monkeypatch.setattr(
        worker,
        "check_neo4j_connection",
        lambda: {"available": True},
    )
    processed_chunks = []
    monkeypatch.setattr(
        worker,
        "process_chunk_for_knowledge_graph",
        lambda **kwargs: processed_chunks.append(kwargs),
    )

    add_document(worker_session)
    add_chunk(worker_session, chunk_index=0, extraction_method="text")
    add_chunk(
        worker_session,
        chunk_index=1,
        extraction_method="ocr_low_confidence",
    )
    job = add_job(worker_session)

    assert worker.process_due_jobs() == 1

    worker_session.refresh(job)
    assert job.status == "completed"
    assert job.last_error is None
    assert len(processed_chunks) == 1
    assert processed_chunks[0]["chunk_index"] == 0


def test_delete_job_completes_after_graph_cleanup(
    worker_session, monkeypatch
):
    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)
    deleted_documents = []
    monkeypatch.setattr(
        worker,
        "delete_document_relationships",
        lambda **kwargs: deleted_documents.append(kwargs),
    )

    job = add_job(worker_session, operation="delete")

    assert worker.process_due_jobs() == 1

    worker_session.refresh(job)
    assert job.status == "completed"
    assert job.last_error is None
    assert deleted_documents == [
        {"user_id": 1, "document_id": 10}
    ]


def test_failed_sync_is_rescheduled_for_retry(
    worker_session, monkeypatch
):
    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        worker,
        "check_neo4j_connection",
        lambda: {"available": False},
    )

    add_document(worker_session)
    add_chunk(worker_session)
    job = add_job(worker_session)

    assert worker.process_due_jobs() == 0

    worker_session.refresh(job)
    assert job.status == "pending"
    assert job.attempt_count == 1
    assert "unavailable" in job.last_error.lower()
    assert job.next_attempt_at > utc_now_naive()


def test_sync_job_for_missing_document_is_cancelled(
    worker_session, monkeypatch
):
    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)

    job = add_job(worker_session)

    assert worker.process_due_jobs() == 1

    worker_session.refresh(job)
    assert job.status == "cancelled"
    assert job.last_error is None

def test_stale_processing_job_is_recovered(
    worker_session, monkeypatch
):
    from datetime import timedelta

    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)

    job = add_job(worker_session)
    job.status = "processing"
    job.updated_at = utc_now_naive() - timedelta(minutes=31)
    worker_session.commit()

    recovered = worker.recover_stale_jobs(worker_session)

    assert recovered == 1
    worker_session.refresh(job)
    assert job.status == "pending"
    assert job.last_error is not None


def test_recent_processing_job_is_not_recovered(
    worker_session, monkeypatch
):
    from datetime import timedelta

    monkeypatch.setattr(worker, "NEO4J_ENABLED", True)

    job = add_job(worker_session)
    job.status = "processing"
    job.updated_at = utc_now_naive() - timedelta(minutes=2)
    worker_session.commit()

    recovered = worker.recover_stale_jobs(worker_session)

    assert recovered == 0
    worker_session.refresh(job)
    assert job.status == "processing"