from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.document_model import Document
from app.db.event_model import DetectedEvent
from app.services.notification_scheduler_service import schedule_event_reminders


ALLOWED_EVENT_STATUSES = {
    "pending_review",
    "confirmed",
    "rejected",
}


def parse_optional_iso_date(
    value: str,
    field_name: str = "Date",
) -> date | None:
    """Parse a YYYY-MM-DD date, allowing an empty value."""

    cleaned = value.strip()

    if not cleaned:
        return None

    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format."
        ) from exc


def update_event_review(
    db: Session,
    user_id: int,
    event_id: int,
    *,
    title: str,
    event_type: str,
    event_date_text: str,
    event_end_date_text: str,
    status: str,
    original_date_text: str,
) -> DetectedEvent:
    """Validate and save a user's event review."""

    event = (
        db.query(DetectedEvent)
        .join(
            Document,
            DetectedEvent.document_id == Document.id,
        )
        .filter(
            DetectedEvent.id == event_id,
            DetectedEvent.user_id == user_id,
            Document.user_id == user_id,
        )
        .first()
    )

    if event is None:
        raise ValueError("Event not found or access denied.")

    cleaned_title = title.strip()
    cleaned_type = event_type.strip()

    if not cleaned_title:
        raise ValueError("Event title cannot be empty.")

    if len(cleaned_title) > 255:
        raise ValueError("Event title cannot exceed 255 characters.")

    if not cleaned_type:
        raise ValueError("Event category cannot be empty.")

    if len(cleaned_type) > 50:
        raise ValueError("Event category cannot exceed 50 characters.")

    if status not in ALLOWED_EVENT_STATUSES:
        raise ValueError("Select a valid event review status.")

    event_date = parse_optional_iso_date(
        event_date_text,
        "Event date",
    )
    event_end_date = parse_optional_iso_date(
        event_end_date_text,
        "Event end date",
    )

    if status == "confirmed" and event_date is None:
        raise ValueError(
            "A valid event date is required before confirming an event."
        )

    if event_end_date is not None and event_date is None:
        raise ValueError(
            "Enter the event start date before its end date."
        )

    if (
        event_date is not None
        and event_end_date is not None
        and event_end_date < event_date
    ):
        raise ValueError(
            "The event end date cannot be earlier than its start date."
        )

    event.title = cleaned_title
    event.event_type = cleaned_type
    event.event_date = event_date
    event.event_end_date = event_end_date
    event.status = status

    if event_date is not None:
        event.date_text = event_date.isoformat()
        event.date_confidence = "user_confirmed"
    else:
        # Preserve the original document wording for unresolved dates.
        event.date_text = original_date_text.strip() or event.date_text

    try:
        schedule_event_reminders(db, event)
        db.commit()
        db.refresh(event)
        return event
    except Exception:
        db.rollback()
        raise


def _escape_ics_text(value: str | None) -> str:
    """Escape text values according to iCalendar text rules."""

    if not value:
        return ""

    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def build_ics_calendar(
    events: Iterable[DetectedEvent],
) -> str:
    """Create an iCalendar file containing confirmed, dated events.

    Calendar end dates are exclusive in iCalendar. MemoryNest treats a
    stored event_end_date as inclusive, so one day is added when exporting.
    """

    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MemoryNest//Calendar Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    exported_count = 0

    for event in events:
        if event.status != "confirmed":
            continue

        if event.event_date is None:
            continue

        start_date = event.event_date
        inclusive_end_date = event.event_end_date or start_date

        if inclusive_end_date < start_date:
            raise ValueError(
                f"Event {event.id} has an end date before its start date."
            )

        exclusive_end_date = inclusive_end_date + timedelta(days=1)

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:memorynest-event-{event.id}@memorynest.local",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{start_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{exclusive_end_date.strftime('%Y%m%d')}",
                f"SUMMARY:{_escape_ics_text(event.title)}",
                (
                    "DESCRIPTION:"
                    f"{_escape_ics_text(event.source_excerpt)}"
                ),
                f"CATEGORIES:{_escape_ics_text(event.event_type)}",
                "END:VEVENT",
            ]
        )

        exported_count += 1

    if exported_count == 0:
        raise ValueError(
            "There are no confirmed events with valid dates to export."
        )

    lines.append("END:VCALENDAR")

    # iCalendar files use CRLF line endings.
    return "\r\n".join(lines) + "\r\n"
