from datetime import date
from types import SimpleNamespace

import pytest

from app.services.calendar_service import (
    build_ics_calendar,
    parse_optional_iso_date,
)


def make_event(
    *,
    event_id=1,
    title="Midterm Examination",
    event_type="exam",
    event_date=date(2026, 10, 20),
    event_end_date=None,
    source_excerpt="Midterm examination on 20 October 2026.",
    status="confirmed",
):
    return SimpleNamespace(
        id=event_id,
        title=title,
        event_type=event_type,
        event_date=event_date,
        event_end_date=event_end_date,
        source_excerpt=source_excerpt,
        status=status,
    )


def test_parse_optional_iso_date():
    assert parse_optional_iso_date("2026-10-20") == date(2026, 10, 20)
    assert parse_optional_iso_date("") is None
    assert parse_optional_iso_date("   ") is None


def test_parse_optional_iso_date_rejects_invalid_date():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_optional_iso_date("2026-02-30")


def test_calendar_contains_confirmed_event():
    calendar = build_ics_calendar([make_event()])

    assert "BEGIN:VCALENDAR" in calendar
    assert "BEGIN:VEVENT" in calendar
    assert "SUMMARY:Midterm Examination" in calendar
    assert "DTSTART;VALUE=DATE:20261020" in calendar
    # iCalendar DTEND is exclusive for all-day events.
    assert "DTEND;VALUE=DATE:20261021" in calendar
    assert "END:VEVENT" in calendar
    assert calendar.endswith("END:VCALENDAR\r\n")


def test_calendar_excludes_pending_and_rejected_events():
    events = [
        make_event(event_id=1, status="confirmed"),
        make_event(event_id=2, status="pending_review"),
        make_event(event_id=3, status="rejected"),
    ]

    calendar = build_ics_calendar(events)

    assert "memorynest-event-1@" in calendar
    assert "memorynest-event-2@" not in calendar
    assert "memorynest-event-3@" not in calendar


def test_calendar_excludes_confirmed_events_without_dates():
    event = make_event(event_date=None)

    with pytest.raises(ValueError, match="no confirmed events"):
        build_ics_calendar([event])


def test_calendar_uses_inclusive_end_date():
    event = make_event(
        event_date=date(2026, 10, 20),
        event_end_date=date(2026, 10, 22),
    )

    calendar = build_ics_calendar([event])

    assert "DTSTART;VALUE=DATE:20261020" in calendar
    assert "DTEND;VALUE=DATE:20261023" in calendar


def test_calendar_escapes_special_text():
    event = make_event(
        title="Exam, Mathematics; Final",
        source_excerpt="Bring a pen, pencil; and ID.",
    )

    calendar = build_ics_calendar([event])

    assert r"SUMMARY:Exam\, Mathematics\; Final" in calendar
    assert r"DESCRIPTION:Bring a pen\, pencil\; and ID." in calendar


def test_calendar_rejects_end_date_before_start_date():
    event = make_event(
        event_date=date(2026, 10, 22),
        event_end_date=date(2026, 10, 20),
    )

    with pytest.raises(ValueError, match="end date before"):
        build_ics_calendar([event])