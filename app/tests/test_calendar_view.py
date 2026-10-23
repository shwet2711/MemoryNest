
from datetime import date
from types import SimpleNamespace

import pytest

from app.ui.calendar_view import (
    _change_month,
    _event_sort_key,
    _event_timeline_label,
    event_occurs_on,
)


def make_event(
    *,
    event_date=None,
    event_end_date=None,
    status="confirmed",
    title="Test event",
):
    return SimpleNamespace(
        event_date=event_date,
        event_end_date=event_end_date,
        status=status,
        title=title,
    )


def test_event_occurs_on_single_date():
    event = make_event(event_date=date(2026, 10, 25))

    assert event_occurs_on(event, date(2026, 10, 25))
    assert not event_occurs_on(event, date(2026, 10, 24))
    assert not event_occurs_on(event, date(2026, 10, 26))


def test_event_occurs_on_inclusive_date_range():
    event = make_event(
        event_date=date(2026, 10, 25),
        event_end_date=date(2026, 10, 27),
    )

    assert event_occurs_on(event, date(2026, 10, 25))
    assert event_occurs_on(event, date(2026, 10, 26))
    assert event_occurs_on(event, date(2026, 10, 27))
    assert not event_occurs_on(event, date(2026, 10, 28))


def test_event_without_date_does_not_appear_on_calendar():
    event = make_event()

    assert not event_occurs_on(event, date(2026, 10, 25))


@pytest.mark.parametrize(
    ("current", "offset", "expected"),
    [
        (date(2026, 10, 19), -1, date(2026, 9, 1)),
        (date(2026, 10, 19), 1, date(2026, 11, 1)),
        (date(2026, 1, 15), -1, date(2025, 12, 1)),
        (date(2026, 12, 15), 1, date(2027, 1, 1)),
    ],
)
def test_change_month(current, offset, expected):
    assert _change_month(current, offset) == expected


def test_future_confirmed_event_is_upcoming():
    event = make_event(
        event_date=date(2026, 10, 25),
        status="confirmed",
    )

    assert _event_timeline_label(event, date(2026, 10, 19)) == "Upcoming"


def test_pending_future_event_needs_review():
    event = make_event(
        event_date=date(2026, 10, 25),
        status="pending_review",
    )

    assert (
        _event_timeline_label(event, date(2026, 10, 19))
        == "Upcoming · Needs review"
    )


def test_past_pending_event_is_overdue_for_review():
    event = make_event(
        event_date=date(2026, 10, 10),
        status="pending_review",
    )

    assert (
        _event_timeline_label(event, date(2026, 10, 19))
        == "Overdue review"
    )


def test_past_confirmed_event_is_past():
    event = make_event(
        event_date=date(2026, 10, 10),
        status="confirmed",
    )

    assert _event_timeline_label(event, date(2026, 10, 19)) == "Past"


def test_event_ending_today_is_not_past():
    event = make_event(
        event_date=date(2026, 10, 17),
        event_end_date=date(2026, 10, 19),
        status="confirmed",
    )

    assert (
        _event_timeline_label(event, date(2026, 10, 19))
        == "In progress"
    )


def test_rejected_status_is_preserved():
    event = make_event(
        event_date=date(2026, 10, 25),
        status="rejected",
    )

    assert _event_timeline_label(event, date(2026, 10, 19)) == "Rejected"


def test_undated_event_needs_date():
    event = make_event(status="pending_review")

    assert _event_timeline_label(event, date(2026, 10, 19)) == "Needs date"


def test_event_sort_key_sorts_by_date_then_title():
    earlier = make_event(
        event_date=date(2026, 10, 20),
        title="Zebra meeting",
    )
    same_date_first = make_event(
        event_date=date(2026, 10, 20),
        title="Alpha meeting",
    )
    later = make_event(
        event_date=date(2026, 10, 21),
        title="Earlier alphabetically",
    )

    events = sorted(
        [later, earlier, same_date_first],
        key=_event_sort_key,
    )

    assert events == [same_date_first, earlier, later]
