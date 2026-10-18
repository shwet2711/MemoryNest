
from datetime import date

from app.services.event_detection_service import (
    detect_event_candidates,
    parse_event_date,
)


def test_detects_iso_date_for_a_deadline():
    candidates = detect_event_candidates(
        "The assignment deadline is 2026-10-25."
    )

    assert len(candidates) == 1
    assert candidates[0].event_date == date(2026, 10, 25)
    assert candidates[0].event_type == "deadline"


def test_detects_written_date_for_an_exam():
    candidates = detect_event_candidates(
        "The final exam will take place on 17 October 2026."
    )

    assert len(candidates) == 1
    assert candidates[0].event_date == date(2026, 10, 17)
    assert candidates[0].event_type == "exam"


def test_ambiguous_numeric_date_requires_review():
    parsed_date, confidence = parse_event_date("03/04/2027")

    assert parsed_date is None
    assert confidence == "needs_review"


def test_relative_date_requires_review():
    parsed_date, confidence = parse_event_date("tomorrow")

    assert parsed_date is None
    assert confidence == "needs_review"


def test_ignores_unrelated_dates_without_event_keywords():
    candidates = detect_event_candidates(
        "The report was written on 2026-10-25."
    )

    assert candidates == []


def test_empty_text_returns_no_candidates():
    assert detect_event_candidates("") == []


def test_invalid_iso_date_requires_review():
    parsed_date, confidence = parse_event_date("2026-02-30")

    assert parsed_date is None
    assert confidence == "needs_review"



def test_indian_dotted_date_is_parsed_day_first():
    parsed_date, confidence = parse_event_date("12.10.2026")

    assert parsed_date == date(2026, 10, 12)
    assert confidence == "high"


def test_detects_three_exam_fee_periods_from_ocr_table():
    text = """
    Sr. L Exam Fee Late Fee Super Late Fee
    No. Class 12.10.2026 | 19.10.2026 26.10.2026
    to 17.10.2026 | to 25.10.2026 to 31.10.2026
    Second Year (Engg.) 1800/- 1800/- + 100/-
    """

    candidates = detect_event_candidates(text)

    assert len(candidates) == 3

    assert [candidate.title for candidate in candidates] == [
        "Regular Exam Fee Period",
        "Late Fee Period",
        "Super-Late Fee Period",
    ]

    assert [candidate.event_date for candidate in candidates] == [
        date(2026, 10, 12),
        date(2026, 10, 19),
        date(2026, 10, 26),
    ]

    assert [candidate.date_text for candidate in candidates] == [
        "12.10.2026 to 17.10.2026",
        "19.10.2026 to 25.10.2026",
        "26.10.2026 to 31.10.2026",
    ]


def test_invalid_dotted_date_requires_review():
    parsed_date, confidence = parse_event_date("31.02.2026")

    assert parsed_date is None
    assert confidence == "needs_review"
