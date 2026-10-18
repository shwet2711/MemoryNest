
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Pattern


MONTH_PATTERN = (
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

EVENT_KEYWORDS = {
    "deadline": ("deadline", "due date", "due by", "last date"),
    "exam": ("exam", "examination", "test", "viva"),
    "meeting": ("meeting", "appointment", "interview", "review"),
    "submission": ("submit", "submission", "assignment", "project report"),
    "registration": ("registration", "register", "enrollment", "enrolment"),
    "academic": ("lecture", "class", "presentation", "workshop", "webinar"),
    "payment": ("payment", "fee", "fees", "renewal"),
    "travel": ("flight", "trip", "departure", "reservation"),
    "personal": ("birthday", "anniversary", "doctor visit"),
    "general": ("event", "scheduled", "conference"),
}

DATE_TOKEN = (
    r"(?:"
    # ISO: 2026-10-17
    r"20\d{2}-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01])"
    r"|"
    # Day-first dotted, slash, or hyphen formats.
    r"(?:0?[1-9]|[12]\d|3[01])[-/.]"
    r"(?:0?[1-9]|1[0-2])[-/.]20\d{2}"
    r"|"
    # Month-first numeric formats.
    r"(?:0?[1-9]|1[0-2])[-/.]"
    r"(?:0?[1-9]|[12]\d|3[01])[-/.]20\d{2}"
    r"|"
    # 17 October 2026
    rf"(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+"
    rf"(?:{MONTH_PATTERN})\.?,?\s+20\d{{2}}"
    r"|"
    # October 17, 2026
    rf"(?:{MONTH_PATTERN})\.?\s+"
    rf"(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?"
    rf",?\s+20\d{{2}}"
    r")"
)

DATE_PATTERN: Pattern[str] = re.compile(
    rf"\b(?P<date>{DATE_TOKEN})\b",
    re.IGNORECASE,
)

RELATIVE_DATE_PATTERN: Pattern[str] = re.compile(
    r"\b(?P<date>"
    r"day after tomorrow|today|tomorrow|next week|next month|"
    r"next Monday|next Tuesday|next Wednesday|next Thursday|"
    r"next Friday|next Saturday|next Sunday"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EventCandidate:
    """An event candidate extracted from document text."""

    title: str
    event_type: str
    event_date: date | None
    event_end_date: date | None
    date_text: str
    source_excerpt: str
    date_confidence: str


def classify_event(text: str) -> str | None:
    """Identify an event category from keywords in the source text."""
    lowered = text.casefold()

    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return event_type

    return None


def parse_event_date(date_text: str) -> tuple[date | None, str]:
    """Parse recognizable dates without guessing ambiguous numeric formats."""
    value = date_text.strip()
    lowered = value.casefold()

    relative_dates = {
        "today",
        "tomorrow",
        "day after tomorrow",
        "next week",
        "next month",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
    }

    if lowered in relative_dates:
        return None, "needs_review"

    # ISO format: 2026-10-17.
    if re.fullmatch(r"20\d{2}-\d{1,2}-\d{1,2}", value):
        try:
            return date.fromisoformat(value), "high"
        except ValueError:
            return None, "needs_review"

    # Indian dotted format: 12.10.2026 means 12 October 2026.
    dotted_match = re.fullmatch(
        r"(\d{1,2})\.(\d{1,2})\.(20\d{2})",
        value,
    )

    if dotted_match:
        day, month, year = map(int, dotted_match.groups())

        try:
            return date(year, month, day), "high"
        except ValueError:
            return None, "needs_review"

    # Slash and hyphen formats can be ambiguous.
    numeric_match = re.fullmatch(
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",
        value,
    )

    if numeric_match:
        first, second, year = map(int, numeric_match.groups())

        if first > 12 and 1 <= second <= 12:
            day, month = first, second
        elif second > 12 and 1 <= first <= 12:
            month, day = first, second
        else:
            # Do not guess between formats such as 04/05/2026.
            return None, "needs_review"

        try:
            return date(year, month, day), "high"
        except ValueError:
            return None, "needs_review"

    # Written dates, including ordinal suffixes.
    normalized = re.sub(
        r"(\d{1,2})(st|nd|rd|th)\b",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.replace(".", "")

    formats = (
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(normalized, date_format).date()
            return parsed, "high"
        except ValueError:
            continue

    return None, "needs_review"


def split_into_sentences(text: str) -> list[str]:
    """Split extracted text into sentences and non-empty lines."""
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip()
    ]


def _date_matches(text: str) -> list[str]:
    """Extract recognizable date tokens while preserving their order."""
    return [
        match.group("date")
        for match in DATE_PATTERN.finditer(text)
    ]


def _detect_fee_periods(text: str) -> list[EventCandidate]:
    """
    Recognize the three-column exam-fee table pattern.

    Example:
        Exam Fee Late Fee Super Late Fee
        12.10.2026 | 19.10.2026 26.10.2026
        to 17.10.2026 | to 25.10.2026 to 31.10.2026
    """
    lines = [line.strip() for line in text.splitlines()]
    candidates: list[EventCandidate] = []

    for index, line in enumerate(lines):
        lowered = line.casefold()

        if not (
            "exam fee" in lowered
            and "late fee" in lowered
            and "super late fee" in lowered
        ):
            continue

        # Search the following few lines for three start dates
        # and their matching end dates.
        for start_index in range(
            index + 1,
            min(index + 5, len(lines)),
        ):
            start_line = lines[start_index]
            starts = _date_matches(start_line)

            if len(starts) < 3:
                continue

            for end_index in range(
                start_index + 1,
                min(start_index + 4, len(lines)),
            ):
                end_line = lines[end_index]
                ends = _date_matches(end_line)

                if (
                    len(ends) < 3
                    or not re.search(r"\bto\b", end_line, re.IGNORECASE)
                ):
                    continue

                period_names = (
                    ("Regular Exam Fee Period", "exam_fee"),
                    ("Late Fee Period", "late_fee"),
                    ("Super-Late Fee Period", "super_late_fee"),
                )

                excerpt = (
                    f"{line}\n{start_line}\n{end_line}"
                )[:2000]

                for position, (title, event_type) in enumerate(
                    period_names
                ):
                    start_text = starts[position]
                    end_text = ends[position]

                    start_date, start_confidence = parse_event_date(
                        start_text
                    )
                    end_date, end_confidence = parse_event_date(
                        end_text
                    )

                    # Never create an invalid or reversed date range.
                    if (
                        start_date is None
                        or end_date is None
                        or start_confidence != "high"
                        or end_confidence != "high"
                        or end_date < start_date
                    ):
                        continue

                    candidates.append(
                        EventCandidate(
                            title=title,
                            event_type=event_type,
                            event_date=start_date,
                            event_end_date=end_date,
                            date_text=f"{start_text} to {end_text}",
                            source_excerpt=excerpt,
                            date_confidence="high",
                        )
                    )

                return candidates

    return candidates


def detect_event_candidates(text: str) -> list[EventCandidate]:
    """Find event dates and recognize structured fee-period tables."""
    if not text or not text.strip():
        return []

    # Structured table detection takes priority over individual dates.
    fee_periods = _detect_fee_periods(text)

    if fee_periods:
        return fee_periods

    candidates: list[EventCandidate] = []
    seen: set[tuple[str, str]] = set()

    for sentence in split_into_sentences(text):
        # Multiple dates in a line often indicate a table row.
        if len(_date_matches(sentence)) >= 3:
            continue

        event_type = classify_event(sentence)

        if event_type is None:
            continue

        matches = list(DATE_PATTERN.finditer(sentence))
        matches.extend(RELATIVE_DATE_PATTERN.finditer(sentence))
        matches.sort(key=lambda match: match.start())

        for match in matches:
            date_text = match.group("date").strip()
            key = (sentence.casefold(), date_text.casefold())

            if key in seen:
                continue

            seen.add(key)
            parsed_date, confidence = parse_event_date(date_text)

            candidates.append(
                EventCandidate(
                    title=sentence[:255],
                    event_type=event_type,
                    event_date=parsed_date,
                    event_end_date=None,
                    date_text=date_text,
                    source_excerpt=sentence[:2000],
                    date_confidence=confidence,
                )
            )

    return candidates
