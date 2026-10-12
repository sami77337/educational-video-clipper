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


def parse_timestamp(value: str) -> int | float:
    """Parse HH:MM:SS or MM:SS, optionally with millisecond precision."""
    hours, minutes, seconds = normalize_timestamp_text(value).split(":")
    total_ms = (int(hours) * 3600 + int(minutes) * 60) * 1000
    if "." in seconds:
        whole, fractional = seconds.split(".")
        total_ms += int(whole) * 1000 + int(fractional)
    else:
        total_ms += int(seconds) * 1000
    if total_ms % 1000 == 0:
        return total_ms // 1000
    return total_ms / 1000


def normalize_timestamp_text(value: str) -> str:
    """Normalize Arabic/Western digits and preserve optional milliseconds."""
    text = normalize_time_symbols(value)
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(AR_INVALID_TIME_FORMAT)
    if not re.fullmatch(r"\d{1,3}", parts[0]):
        raise ValueError(AR_INVALID_TIME_FORMAT)
    if not re.fullmatch(r"\d{1,2}", parts[1]):
        raise ValueError(AR_INVALID_TIME_FORMAT)

    if len(parts) == 2:
        minutes = int(parts[0])
        seconds_part = parts[1]
        hours = 0
    else:
        hours, minutes = int(parts[0]), int(parts[1])
        seconds_part = parts[2]
        if minutes > 59:
            raise ValueError(AR_INVALID_TIME_FORMAT)
    if not re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?", seconds_part):
        raise ValueError(AR_INVALID_TIME_FORMAT)
    whole, _, fraction = seconds_part.partition(".")
    seconds = int(whole)
    if seconds > 59:
        raise ValueError(AR_INVALID_TIME_FORMAT)
    total_ms = ((hours * 60 + minutes) * 60 + seconds) * 1000
    if fraction:
        total_ms += int(fraction.ljust(3, "0"))
    return format_seconds(total_ms / 1000)


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


def format_seconds(total_seconds: int | float) -> str:
    """Format seconds, preserving non-zero fractions to three decimals."""
    import math

    value = float(total_seconds)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Seconds must be finite and non-negative.")
    total_ms = round(value * 1000)
    hours, rem = divmod(total_ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, ms = divmod(rem, 1000)
    basic = f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{basic}.{ms:03}" if ms else basic


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
