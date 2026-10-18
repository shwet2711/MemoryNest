from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.models.user import User
from app.services import event_service


@pytest.fixture
def event_setup(tmp_path, monkeypatch):
    """Create an isolated database and extracted document."""

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'events.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    # Importing the models registers their tables in Base.metadata.
    Base.metadata.create_all(engine)

    SessionFactory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = SessionFactory()

    extracted_file = tmp_path / "events.txt"
    extracted_file.write_text(
        "Midterm examination on 20 October 2026.",
        encoding="utf-8",
    )

    # Use the existing database schema without assuming User's required fields.
    # Create a valid user using the required database fields.
    user = User(
        username="event_test_user",
        email="event_test_user@example.com",
        password_hash="test-only-password-hash",
    )
    db.add(user)
    db.flush()

    document = Document(
    user_id=user.id,
    original_filename="exam_schedule.txt",
    stored_filename="event_test_exam_schedule.txt",
    file_path=str(tmp_path / "event_test_exam_schedule.txt"),
    file_type="txt",
    file_size=42,
    extracted_text_path=str(extracted_file),
    extraction_status="completed",
    extraction_method="text",
)
    db.add(document)
    db.commit()
    db.refresh(document)

    yield {
        "db": db,
        "user_id": user.id,
        "document_id": document.id,
        "extracted_file": extracted_file,
    }

    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_candidate(
    *,
    title="Midterm examination",
    event_type="exam",
    event_date=None,
    event_end_date=None,
    date_text="20 October 2026",
    source_excerpt="Midterm examination on 20 October 2026.",
    date_confidence="high",
):
    """Build a candidate with the fields used by event_service."""

    from datetime import date

    from app.services.event_detection_service import EventCandidate

    return EventCandidate(
        title=title,
        event_type=event_type,
        event_date=event_date or date(2026, 10, 20),
        event_end_date=event_end_date,
        date_text=date_text,
        source_excerpt=source_excerpt,
        date_confidence=date_confidence,
    )


def test_repeated_scan_does_not_create_duplicate_events(
    event_setup,
    monkeypatch,
):
    setup = event_setup
    db = setup["db"]

    monkeypatch.setattr(
        event_service,
        "detect_event_candidates",
        lambda text: [make_candidate()],
    )

    first_scan = event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )
    second_scan = event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )

    stored_events = (
        db.query(DetectedEvent)
        .filter(
            DetectedEvent.user_id == setup["user_id"],
            DetectedEvent.document_id == setup["document_id"],
        )
        .all()
    )

    assert len(first_scan) == 1
    assert len(second_scan) == 1
    assert len(stored_events) == 1
    assert stored_events[0].title == "Midterm examination"


def test_rescan_preserves_reviewed_event(
    event_setup,
    monkeypatch,
):
    setup = event_setup
    db = setup["db"]

    monkeypatch.setattr(
        event_service,
        "detect_event_candidates",
        lambda text: [make_candidate()],
    )

    detected = event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )[0]

    detected.status = "confirmed"
    detected.title = "My confirmed examination"
    db.commit()

    # Rescanning must not overwrite a user's reviewed decision.
    monkeypatch.setattr(
        event_service,
        "detect_event_candidates",
        lambda text: [
            make_candidate(title="Midterm examination updated")
        ],
    )

    event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )

    stored = db.query(DetectedEvent).filter_by(id=detected.id).one()

    assert stored.status == "confirmed"
    assert stored.title == "My confirmed examination"


def test_rescan_removes_stale_pending_events(
    event_setup,
    monkeypatch,
):
    setup = event_setup
    db = setup["db"]

    monkeypatch.setattr(
        event_service,
        "detect_event_candidates",
        lambda text: [make_candidate()],
    )

    event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )

    monkeypatch.setattr(
        event_service,
        "detect_event_candidates",
        lambda text: [],
    )

    result = event_service.scan_document_for_events(
        db, setup["user_id"], setup["document_id"]
    )

    remaining = (
        db.query(DetectedEvent)
        .filter(
            DetectedEvent.user_id == setup["user_id"],
            DetectedEvent.document_id == setup["document_id"],
        )
        .all()
    )

    assert result == []
    assert remaining == []


def test_scan_rejects_document_owned_by_another_user(event_setup):
    setup = event_setup

    with pytest.raises(ValueError, match="access denied"):
        event_service.scan_document_for_events(
            setup["db"],
            setup["user_id"] + 999,
            setup["document_id"],
        )


def test_scan_rejects_missing_extracted_text(event_setup):
    setup = event_setup
    document = setup["db"].query(Document).filter_by(
        id=setup["document_id"]
    ).one()

    document.extracted_text_path = str(
        Path(setup["extracted_file"].parent) / "missing.txt"
    )
    setup["db"].commit()

    with pytest.raises(ValueError, match="could not be found"):
        event_service.scan_document_for_events(
            setup["db"],
            setup["user_id"],
            setup["document_id"],
        )
