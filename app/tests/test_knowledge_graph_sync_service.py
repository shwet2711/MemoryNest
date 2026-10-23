from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.knowledge_graph_sync_model import (
    KnowledgeGraphSyncJob,
    utc_now_naive,
)
from app.services.knowledge_graph_sync_service import (
    enqueue_delete_job,
    enqueue_sync_job,
    retry_delay_minutes,
    schedule_job_retry,
)


@pytest.fixture
def queue_session(tmp_path):
    database_file = tmp_path / "knowledge_graph_queue.sqlite"
    engine = create_engine(
        f"sqlite:///{database_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    KnowledgeGraphSyncJob.__table__.create(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


def test_enqueue_sync_job_creates_pending_job(queue_session):
    job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
    )
    queue_session.commit()

    assert job.id is not None
    assert job.operation == "sync"
    assert job.status == "pending"
    assert job.attempt_count == 0
    assert job.last_error is None


def test_backfill_style_enqueue_preserves_existing_retry_state(
    queue_session,
):
    job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
    )
    job.attempt_count = 3
    job.last_error = "Neo4j unavailable"
    scheduled_time = utc_now_naive() + timedelta(minutes=15)
    job.next_attempt_at = scheduled_time
    queue_session.commit()

    reused_job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
        reset_completed=False,
    )

    assert reused_job.id == job.id
    assert reused_job.status == "pending"
    assert reused_job.attempt_count == 3
    assert reused_job.last_error == "Neo4j unavailable"
    assert reused_job.next_attempt_at == scheduled_time


def test_backfill_style_enqueue_preserves_completed_job(queue_session):
    job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
    )
    job.status = "completed"
    job.attempt_count = 2
    queue_session.commit()

    reused_job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
        reset_completed=False,
    )

    assert reused_job.id == job.id
    assert reused_job.status == "completed"
    assert reused_job.attempt_count == 2


def test_enqueue_delete_cancels_sync_job(queue_session):
    sync_job = enqueue_sync_job(
        queue_session,
        user_id=1,
        document_id=10,
    )
    queue_session.commit()

    delete_job = enqueue_delete_job(
        queue_session,
        user_id=1,
        document_id=10,
    )
    queue_session.commit()

    assert sync_job.status == "cancelled"
    assert delete_job.operation == "delete"
    assert delete_job.status == "pending"
    assert delete_job.attempt_count == 0


@pytest.mark.parametrize(
    ("attempt_count", "expected_minutes"),
    [
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 4),
        (4, 8),
        (5, 16),
        (6, 32),
        (7, 60),
        (20, 60),
    ],
)
def test_retry_delay_minutes(attempt_count, expected_minutes):
    assert retry_delay_minutes(attempt_count) == expected_minutes


def test_schedule_job_retry_records_error_and_delay():
    job = KnowledgeGraphSyncJob(
        user_id=1,
        document_id=10,
        operation="sync",
        status="processing",
        attempt_count=2,
        next_attempt_at=utc_now_naive(),
    )
    before = utc_now_naive()

    schedule_job_retry(job, "Neo4j unavailable")

    after = utc_now_naive()

    assert job.status == "pending"
    assert job.last_error == "Neo4j unavailable"
    assert before + timedelta(minutes=2) <= job.next_attempt_at
    assert job.next_attempt_at <= after + timedelta(minutes=2)
