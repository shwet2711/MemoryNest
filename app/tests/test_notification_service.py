
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.notification_service import (
    build_event_notifications,
)


TODAY = date(2026, 10, 19)


def make_event(
    title="Test event",
    event_date=date(2026, 10, 25),
    event_end_date=None,
    status="confirmed",
):
    return SimpleNamespace(
        title=title,
        event_date=event_date,
        event_end_date=event_end_date,
        status=status,
    )


def test_upcoming_confirmed_event_generates_notification():
    rows = [(make_event(title="Project review"), "project.txt")]

    result = build_event_notifications(rows, today=TODAY)

    assert len(result) == 1
    assert result[0]["title"] == "Project review"
    assert result[0]["level"] == "success"
    assert result[0]["date"] == "25 Oct 2026"
    assert result[0]["source"] == "project.txt"


def test_event_happening_today_generates_notification():
    rows = [(make_event(event_date=TODAY), "today.txt")]

    result = build_event_notifications(rows, today=TODAY)

    assert len(result) == 1
    assert result[0]["level"] == "info"
    assert "today" in result[0]["message"].lower()


def test_past_pending_event_generates_review_warning():
    rows = [
        (
            make_event(
                event_date=date(2026, 10, 15),
                status="pending_review",
            ),
            "past.txt",
        )
    ]

    result = build_event_notifications(rows, today=TODAY)

    assert len(result) == 1
    assert result[0]["level"] == "warning"
    assert "date has passed" in result[0]["message"]


def test_undated_pending_event_needs_review():
    rows = [
        (
            make_event(event_date=None, status="pending_review"),
            "undated.txt",
        )
    ]

    result = build_event_notifications(rows, today=TODAY)

    assert len(result) == 1
    assert result[0]["date"] == "Date not set"
    assert result[0]["level"] == "warning"


def test_rejected_event_does_not_generate_notification():
    rows = [(make_event(status="rejected"), "rejected.txt")]

    assert build_event_notifications(rows, today=TODAY) == []


def test_invalid_event_date_range_is_ignored():
    rows = [
        (
            make_event(
                event_date=date(2026, 10, 25),
                event_end_date=date(2026, 10, 20),
            ),
            "invalid.txt",
        )
    ]

    assert build_event_notifications(rows, today=TODAY) == []


def test_notifications_are_sorted_chronologically():
    rows = [
        (
            make_event(
                title="Later event",
                event_date=date(2026, 10, 26),
            ),
            "later.txt",
        ),
        (
            make_event(
                title="Earlier event",
                event_date=date(2026, 10, 21),
            ),
            "earlier.txt",
        ),
    ]

    result = build_event_notifications(rows, today=TODAY)

    assert [item["title"] for item in result] == [
        "Earlier event",
        "Later event",
    ]


def test_confirmed_event_outside_window_is_ignored():
    rows = [
        (
            make_event(event_date=date(2026, 11, 15)),
            "future.txt",
        )
    ]

    result = build_event_notifications(
        rows,
        today=TODAY,
        upcoming_days=7,
    )

    assert result == []


def test_negative_upcoming_window_is_rejected():
    with pytest.raises(ValueError, match="upcoming_days"):
        build_event_notifications([], today=TODAY, upcoming_days=-1)
