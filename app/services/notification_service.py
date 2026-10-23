
from datetime import date, timedelta


def build_event_notifications(
    rows: list[tuple[object, str]],
    today: date | None = None,
    upcoming_days: int = 7,
) -> list[dict[str, str]]:
    """Build in-app notifications from user-scoped event records."""

    if today is None:
        today = date.today()

    if upcoming_days < 0:
        raise ValueError("upcoming_days cannot be negative.")

    upcoming_limit = today + timedelta(days=upcoming_days)

    priority = {"warning": 0, "info": 1, "success": 2}
    scheduled = []

    for event, filename in rows:
        status = event.status

        if status not in {"pending_review", "confirmed"}:
            continue

        event_date = event.event_date
        end_date = event.event_end_date or event_date

        if event_date is None:
            if status == "pending_review":
                item = {
                    "level": "warning",
                    "title": event.title or "Untitled event",
                    "message": (
                        "This event needs a date review before "
                        "it can be scheduled."
                    ),
                    "date": "Date not set",
                    "source": filename or "Unknown document",
                }
                scheduled.append(
                    (date.max, priority["warning"], item["title"].casefold(), item)
                )
            continue

        if end_date < event_date:
            continue

        date_label = event_date.strftime("%d %b %Y")
        if end_date != event_date:
            date_label += f" – {end_date.strftime('%d %b %Y')}"

        level = None
        message = ""

        if end_date < today:
            if status == "pending_review":
                level = "warning"
                message = (
                    "This event's date has passed, but it still "
                    "needs your review."
                )
            else:
                continue
        elif event_date <= today <= end_date:
            if status == "pending_review":
                level = "warning"
                message = (
                    "This event is happening today or is in progress "
                    "and still needs your review."
                )
            else:
                level = "info"
                message = (
                    "This confirmed event is happening today "
                    "or is currently in progress."
                )
        elif event_date <= upcoming_limit:
            if status == "pending_review":
                level = "warning"
                message = (
                    "An upcoming event needs your review before "
                    "it can be confirmed."
                )
            else:
                level = "success"
                message = (
                    "Upcoming confirmed event. Make sure "
                    "you are prepared."
                )

        if level is None:
            continue

        item = {
            "level": level,
            "title": event.title or "Untitled event",
            "message": message,
            "date": date_label,
            "source": filename or "Unknown document",
        }
        scheduled.append(
            (event_date, priority[level], item["title"].casefold(), item)
        )

    scheduled.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in scheduled]
