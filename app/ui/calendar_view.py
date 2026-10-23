
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

import streamlit as st

from app.db.session import SessionLocal
from app.services.event_service import get_user_events
from app.services.notification_service import (
    build_event_notifications,
)


logger = logging.getLogger(__name__)

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

UPCOMING_WINDOW_DAYS = 30


def event_occurs_on(event, selected_date: date) -> bool:
    """Return whether a dated event includes the selected day."""

    if event.event_date is None:
        return False

    end_date = event.event_end_date or event.event_date

    return event.event_date <= selected_date <= end_date


def _change_month(current: date, offset: int) -> date:
    """Return the first day of a month relative to the current month."""

    month_index = current.year * 12 + current.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)

    return date(year, zero_based_month + 1, 1)


def _event_end_date(event) -> date | None:
    """Return an event's effective end date."""

    if event.event_date is None:
        return None

    return event.event_end_date or event.event_date


def _event_timeline_label(event, today: date) -> str:
    """Describe an event's date position without changing its review status."""

    if event.status == "rejected":
        return "Rejected"

    if event.event_date is None:
        return "Needs date"

    end_date = _event_end_date(event)

    if end_date < today:
        if event.status == "pending_review":
            return "Overdue review"
        return "Past"

    if event.event_date <= today <= end_date:
        if event.event_date < today:
            return "In progress"
        return "Today"

    if event.status == "pending_review":
        return "Upcoming · Needs review"

    return "Upcoming"


def _event_sort_key(event) -> tuple[date, str]:
    """Sort dated events by start date, then title."""

    return (
        event.event_date or date.max,
        (event.title or "").casefold(),
    )


def _render_event_card(
    event,
    filename: str,
    today: date,
    *,
    show_evidence: bool = True,
) -> None:
    """Render an event and its source details."""

    with st.container(border=True):
        st.markdown(f"**{event.title}**")

        timeline_label = _event_timeline_label(event, today)
        status_label = event.status.replace("_", " ").title()
        category = event.event_type or "Uncategorized"

        st.caption(
            f"{timeline_label} · Status: {status_label} · "
            f"Category: {category}"
        )

        if event.event_date:
            end_date = _event_end_date(event)

            if end_date and end_date != event.event_date:
                st.write(
                    f"**Duration:** "
                    f"{event.event_date.strftime('%d %b %Y')} – "
                    f"{end_date.strftime('%d %b %Y')}"
                )
            else:
                st.write(
                    f"**Date:** "
                    f"{event.event_date.strftime('%d %b %Y')}"
                )
        else:
            st.write("**Date:** Not set")

        st.write(f"**Source document:** {filename}")

        if show_evidence and event.source_excerpt:
            with st.expander("View source evidence"):
                st.write(event.source_excerpt)

        if event.status == "pending_review":
            if timeline_label == "Overdue review":
                st.warning(
                    "This event's date has passed, but it is still awaiting "
                    "review. Verify it on the Events page."
                )
            else:
                st.info(
                    "This event has not been confirmed. Verify its details "
                    "on the Events page."
                )
        elif event.status == "confirmed" and timeline_label == "Past":
            st.caption("This confirmed event has ended.")
        elif event.status == "confirmed":
            st.success("This event is confirmed.")
        elif event.status == "rejected":
            st.caption("This event was rejected during review.")


def _render_notifications(
    rows: list[tuple[object, str]],
    today: date,
) -> None:
    """Display event notifications for the signed-in user."""

    st.divider()
    st.subheader("Notifications")

    notifications = build_event_notifications(
        rows,
        today=today,
        upcoming_days=7,
    )

    if not notifications:
        st.success(
            "You're all caught up. No event notifications right now."
        )
        return

    st.caption(
        f"{len(notifications)} event notification(s)"
    )

    for notification in notifications:
        with st.container(border=True):
            st.markdown(f"**{notification['title']}**")
            st.caption(notification["date"])
            st.write(notification["message"])
            st.caption(
                f"Source document: {notification['source']}"
            )

            if notification["level"] == "warning":
                st.warning("Review needed")
            elif notification["level"] == "success":
                st.success("Confirmed")
            else:
                st.info("In progress")


def calendar_page() -> None:
    """Display a navigable month calendar and event timeline."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        st.warning("Please sign in to view your calendar.")
        return

    st.title("Calendar")
    st.caption(
        "Explore deadlines, examinations, meetings, and other events "
        "detected in your MemoryNest documents."
    )

    today = date.today()

    if "calendar_view_month" not in st.session_state:
        st.session_state["calendar_view_month"] = date(
            today.year, today.month, 1
        )

    if "calendar_selected_date" not in st.session_state:
        st.session_state["calendar_selected_date"] = today.isoformat()

    current_month = st.session_state["calendar_view_month"]

    # Load only events belonging to the signed-in user.
    db = SessionLocal()

    try:
        rows = get_user_events(db, int(user_id))
        events = [event for event, _filename in rows]
        filename_by_event_id = {
            event.id: filename for event, filename in rows
        }
    except Exception:
        logger.exception(
            "Could not load calendar events for user %s", user_id
        )
        st.error(
            "Could not load your calendar events. "
            "Check the application logs for details."
        )
        return
    finally:
        db.close()

    # Notifications are generated from the same user-scoped event records.
    _render_notifications(rows, today)

    dated_events = sorted(
        [event for event in events if event.event_date is not None],
        key=_event_sort_key,
    )

    undated_events = sorted(
        [event for event in events if event.event_date is None],
        key=lambda event: (event.title or "").casefold(),
    )

    confirmed_count = sum(
        event.status == "confirmed" for event in events
    )
    pending_count = sum(
        event.status == "pending_review" for event in events
    )
    rejected_count = sum(
        event.status == "rejected" for event in events
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Total events", len(events))
    metric_cols[1].metric("Confirmed", confirmed_count)
    metric_cols[2].metric("Pending review", pending_count)
    metric_cols[3].metric("Rejected", rejected_count)

    st.divider()

    # Month navigation.
    nav_left, nav_center, nav_right = st.columns([1, 4, 1])

    with nav_left:
        if st.button(
            "← Previous",
            key="calendar_previous_month",
            width="stretch",
        ):
            st.session_state["calendar_view_month"] = _change_month(
                current_month, -1
            )
            st.session_state["calendar_selected_date"] = (
                st.session_state["calendar_view_month"].isoformat()
            )
            st.rerun()

    with nav_center:
        st.subheader(current_month.strftime("%B %Y"))

    with nav_right:
        if st.button(
            "Next →",
            key="calendar_next_month",
            width="stretch",
        ):
            st.session_state["calendar_view_month"] = _change_month(
                current_month, 1
            )
            st.session_state["calendar_selected_date"] = (
                st.session_state["calendar_view_month"].isoformat()
            )
            st.rerun()

    if st.button("Today", key="calendar_today", width="stretch"):
        st.session_state["calendar_view_month"] = date(
            today.year, today.month, 1
        )
        st.session_state["calendar_selected_date"] = today.isoformat()
        st.rerun()

    selected_date = date.fromisoformat(
        st.session_state["calendar_selected_date"]
    )

    # Weekday headings.
    heading_cols = st.columns(7)

    for index, weekday in enumerate(WEEKDAYS):
        heading_cols[index].markdown(f"**{weekday[:3]}**")

    # Month grid, including adjacent-month days needed to complete weeks.
    month_calendar = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = month_calendar.monthdatescalendar(
        current_month.year, current_month.month
    )

    for week in weeks:
        day_cols = st.columns(7)

        for day_index, day in enumerate(week):
            day_events = [
                event
                for event in dated_events
                if event_occurs_on(event, day)
            ]

            with day_cols[day_index]:
                if st.button(
                    str(day.day),
                    key=f"calendar_day_{day.isoformat()}",
                    type=(
                        "primary"
                        if day == selected_date
                        else "secondary"
                    ),
                    width="stretch",
                ):
                    st.session_state["calendar_selected_date"] = (
                        day.isoformat()
                    )
                    st.session_state["calendar_view_month"] = date(
                        day.year, day.month, 1
                    )
                    st.rerun()

                if day.month != current_month.month:
                    st.caption(" ")
                elif day_events:
                    st.caption(f"{len(day_events)} event(s)")
                elif day == today:
                    st.caption("Today")
                else:
                    st.caption(" ")

    st.divider()

    # Selected-day details.
    selected_date = date.fromisoformat(
        st.session_state["calendar_selected_date"]
    )

    st.subheader(selected_date.strftime("%A, %d %B %Y"))

    selected_events = sorted(
        [
            event
            for event in dated_events
            if event_occurs_on(event, selected_date)
        ],
        key=_event_sort_key,
    )

    if not selected_events:
        st.info("No dated events are scheduled for this day.")
    else:
        for event in selected_events:
            _render_event_card(
                event,
                filename_by_event_id.get(event.id, "Unknown document"),
                today,
            )

    # Upcoming events include today and events currently in progress.
    upcoming_limit = today + timedelta(days=UPCOMING_WINDOW_DAYS)

    upcoming_events = [
        event
        for event in dated_events
        if event.status != "rejected"
        and (_event_end_date(event) or date.min) >= today
        and event.event_date <= upcoming_limit
    ]

    overdue_review_events = [
        event
        for event in dated_events
        if event.status == "pending_review"
        and (_event_end_date(event) or date.max) < today
    ]

    past_events = [
        event
        for event in dated_events
        if event.status != "pending_review"
        and (_event_end_date(event) or date.max) < today
    ]

    st.divider()
    st.subheader(f"Upcoming Events · Next {UPCOMING_WINDOW_DAYS} Days")

    if not upcoming_events:
        st.info("No upcoming dated events in the next 30 days.")
    else:
        for event in upcoming_events:
            _render_event_card(
                event,
                filename_by_event_id.get(event.id, "Unknown document"),
                today,
            )

    st.divider()
    st.subheader(f"Overdue Review · {len(overdue_review_events)}")

    if not overdue_review_events:
        st.success("No past-dated events are waiting for review.")
    else:
        st.caption(
            "These events have dates in the past and still need your review. "
            "Review them before treating them as confirmed."
        )
        for event in overdue_review_events:
            _render_event_card(
                event,
                filename_by_event_id.get(event.id, "Unknown document"),
                today,
            )

    with st.expander(f"Past Events · {len(past_events)}"):
        if not past_events:
            st.caption("No past events to display.")
        else:
            for event in past_events:
                _render_event_card(
                    event,
                    filename_by_event_id.get(event.id, "Unknown document"),
                    today,
                )

    if undated_events:
        st.divider()

        with st.expander(
            f"Events Without Dates · {len(undated_events)}"
        ):
            st.caption(
                "These events cannot appear on the month grid until their "
                "dates have been reviewed on the Events page."
            )

            for event in undated_events:
                _render_event_card(
                    event,
                    filename_by_event_id.get(event.id, "Unknown document"),
                    today,
                )
