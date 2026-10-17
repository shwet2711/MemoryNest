
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OCRQuality:
    score: float
    is_reliable: bool
    reasons: tuple[str, ...]


MIN_TEXT_CHARACTERS = 40
MIN_READABLE_WORD_RATIO = 0.70
MIN_ALPHABETIC_WORD_RATIO = 0.50

# Unicode escapes avoid source-file encoding problems in PowerShell
# and match common UTF-8 decoding errors.


MOJIBAKE_MARKERS = (
    "Ã",
    "Â",
    "â€",
    "ï¿½",
    "\uFFFD",
)



WORD_PATTERN = re.compile(
    r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*"
)


def assess_ocr_text(text: str) -> OCRQuality:
    """Flag suspicious OCR text without modifying its contents."""
    if not isinstance(text, str) or not text.strip():
        return OCRQuality(
            score=0.0,
            is_reliable=False,
            reasons=("empty_text",),
        )

    reasons: list[str] = []
    stripped = text.strip()
    words = WORD_PATTERN.findall(stripped)

    if len(stripped) < MIN_TEXT_CHARACTERS:
        reasons.append("too_little_text")

    if any(marker in stripped for marker in MOJIBAKE_MARKERS):
        reasons.append("possible_encoding_corruption")

    if not words:
        reasons.append("no_readable_words")
        return OCRQuality(
            score=0.0,
            is_reliable=False,
            reasons=tuple(dict.fromkeys(reasons)),
        )

    readable_words = [
        word for word in words
        if len(word) >= 2 or word.lower() in {"a", "i"}
    ]
    readable_ratio = len(readable_words) / len(words)

    if readable_ratio < MIN_READABLE_WORD_RATIO:
        reasons.append("many_fragmented_words")

    alphabetic_characters = sum(
        character.isalpha() for character in stripped
    )
    visible_characters = sum(
        not character.isspace() for character in stripped
    )
    alphabetic_ratio = (
        alphabetic_characters / visible_characters
        if visible_characters
        else 0.0
    )

    if alphabetic_ratio < MIN_ALPHABETIC_WORD_RATIO:
        reasons.append("low_alphabetic_ratio")

    score = max(
        0.0,
        min(1.0, 0.5 * readable_ratio + 0.5 * alphabetic_ratio),
    )

    unique_reasons = tuple(dict.fromkeys(reasons))

    return OCRQuality(
        score=round(score, 3),
        is_reliable=not unique_reasons,
        reasons=unique_reasons,
    )
