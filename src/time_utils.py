"""Utilities for parsing and formatting timestamps."""

from __future__ import annotations

import re


AR_INVALID_TIME_FORMAT = "صيغة الوقت غير صحيحة. أمثلة صحيحة: 4:15 أو 00:04:15"

_DIGIT_TRANSLATION = str.maketrans(
    {
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
)
_SEPARATOR_TRANSLATION = str.maketrans(
    {
        "：": ":",
        "﹕": ":",
        "︓": ":",
        "꞉": ":",
        "∶": ":",
        "؛": ":",
    }
)


def parse_timestamp(value: str) -> int:
    """Parse a flexible timestamp into total seconds.

    Raises:
        ValueError: If the timestamp is empty or not in a supported format.
    """

    normalized = normalize_timestamp_text(value)
    hours, minutes, seconds = (int(part) for part in normalized.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def normalize_timestamp_text(value: str) -> str:
    """Normalize natural timestamp input to HH:MM:SS."""

    text = normalize_time_symbols(value)
    parts = text.split(":")
    if len(parts) == 2:
        minutes, seconds = _parse_parts(parts)
        _validate_seconds(seconds)
        return format_seconds(minutes * 60 + seconds)

    if len(parts) == 3:
        hours, minutes, seconds = _parse_parts(parts)
        _validate_minute_second_parts(minutes, seconds)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    raise ValueError(AR_INVALID_TIME_FORMAT)


def normalize_time_symbols(value: str) -> str:
    """Normalize digits and colon-like separators in a time string."""

    if value is None or not str(value).strip():
        raise ValueError(AR_INVALID_TIME_FORMAT)

    normalized = normalize_digits(str(value).strip()).translate(_SEPARATOR_TRANSLATION)
    normalized = re.sub(r"\s*:\s*", ":", normalized)
    return normalized


def normalize_digits(text: str) -> str:
    """Convert Arabic-Indic and Persian digits to ASCII digits."""

    return str(text).translate(_DIGIT_TRANSLATION)


def format_seconds(total_seconds: int) -> str:
    """Format seconds as HH:MM:SS."""

    if total_seconds < 0:
        raise ValueError("Seconds cannot be negative.")

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _validate_minute_second_parts(minutes: int, seconds: int) -> None:
    if minutes > 59 or seconds > 59:
        raise ValueError(AR_INVALID_TIME_FORMAT)


def _validate_seconds(seconds: int) -> None:
    if seconds > 59:
        raise ValueError(AR_INVALID_TIME_FORMAT)


def _parse_parts(parts: list[str]) -> list[int]:
    if not all(part.isdigit() for part in parts):
        raise ValueError(AR_INVALID_TIME_FORMAT)

    return [int(part) for part in parts]
