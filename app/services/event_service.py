
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.services.event_detection_service import detect_event_candidates


def _event_key(
    title: str,
    event_type: str,
    date_text: str,
) -> tuple[str, str, str]:
    """Build a stable key for matching a previously detected event."""
    return (
        " ".join(title.casefold().split()),
        event_type.casefold().strip(),
        " ".join(date_text.casefold().split()),
    )


def scan_document_for_events(
    db: Session,
    user_id: int,
    document_id: int,
) -> list[DetectedEvent]:
    """Detect and synchronize events for a document owned by the user."""

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .first()
    )

    if document is None:
        raise ValueError("Document not found or access denied.")

    if document.extraction_status != "completed":
        raise ValueError("This document has not been extracted successfully.")

    if not document.extracted_text_path:
        raise ValueError("No extracted text is available for this document.")

    extracted_path = Path(document.extracted_text_path)

    if not extracted_path.is_file():
        raise ValueError("The extracted text file could not be found.")

    text = extracted_path.read_text(encoding="utf-8")
    candidates = detect_event_candidates(text)

    try:
        existing_events = (
            db.query(DetectedEvent)
            .filter(
                DetectedEvent.user_id == user_id,
                DetectedEvent.document_id == document_id,
            )
            .all()
        )

        existing_by_key: dict[
            tuple[str, str, str],
            list[DetectedEvent],
        ] = {}

        for event in existing_events:
            key = _event_key(
                event.title,
                event.event_type,
                event.date_text,
            )
            existing_by_key.setdefault(key, []).append(event)

        seen_candidate_keys: set[tuple[str, str, str]] = set()
        matched_existing_ids: set[int] = set()
        synchronized_events: list[DetectedEvent] = []

        for candidate in candidates:
            key = _event_key(
                candidate.title,
                candidate.event_type,
                candidate.date_text,
            )

            # Avoid duplicate candidates returned during one scan.
            if key in seen_candidate_keys:
                continue

            seen_candidate_keys.add(key)
            matches = existing_by_key.get(key, [])

            if matches:
                # Prefer an existing reviewed event when one exists.
                event = next(
                    (
                        item
                        for item in matches
                        if item.status != "pending_review"
                    ),
                    matches[0],
                )

                if event.id is not None:
                    matched_existing_ids.add(event.id)

                # Never overwrite a reviewed event automatically.
                if event.status == "pending_review":
                    event.title = candidate.title
                    event.event_type = candidate.event_type
                    event.event_date = candidate.event_date
                    event.event_end_date = candidate.event_end_date
                    event.date_text = candidate.date_text
                    event.date_confidence = candidate.date_confidence
                    event.source_excerpt = candidate.source_excerpt

                synchronized_events.append(event)
                continue

            event = DetectedEvent(
                user_id=user_id,
                document_id=document_id,
                title=candidate.title,
                event_type=candidate.event_type,
                event_date=candidate.event_date,
                event_end_date=candidate.event_end_date,
                date_text=candidate.date_text,
                date_confidence=candidate.date_confidence,
                source_excerpt=candidate.source_excerpt,
                status="pending_review",
            )

            db.add(event)
            synchronized_events.append(event)

        # Remove obsolete pending detections, but preserve reviewed events.
        # This keeps rescans synchronized with the current extracted text.
        for event in existing_events:
            if (
                event.status == "pending_review"
                and event.id not in matched_existing_ids
            ):
                db.delete(event)

        db.commit()

        for event in synchronized_events:
            db.refresh(event)

        return synchronized_events

    except Exception:
        db.rollback()
        raise


def get_user_events(
    db: Session,
    user_id: int,
) -> list[tuple[DetectedEvent, str]]:
    """Return a user's events together with their source filenames."""

    rows = (
        db.query(DetectedEvent, Document.original_filename)
        .join(
            Document,
            DetectedEvent.document_id == Document.id,
        )
        .filter(
            DetectedEvent.user_id == user_id,
            Document.user_id == user_id,
        )
        .order_by(
            DetectedEvent.status.asc(),
            DetectedEvent.event_date.asc(),
            DetectedEvent.created_at.desc(),
        )
        .all()
    )

    return [(event, filename) for event, filename in rows]
