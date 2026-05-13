"""Utilities for parsing and formatting timestamps."""

from __future__ import annotations

import re


_MM_SS_PATTERN = re.compile(r"^(?P<minutes>\d{2}):(?P<seconds>\d{2})$")
_HH_MM_SS_PATTERN = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})$"
)


def parse_timestamp(value: str) -> int:
    """Parse MM:SS or HH:MM:SS into total seconds.

    Raises:
        ValueError: If the timestamp is empty or not in a supported format.
    """

    if value is None or not value.strip():
        raise ValueError("Timestamp is required.")

    timestamp = value.strip()
    match = _MM_SS_PATTERN.fullmatch(timestamp)
    if match:
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        _validate_minute_second_parts(minutes, seconds)
        return minutes * 60 + seconds

    match = _HH_MM_SS_PATTERN.fullmatch(timestamp)
    if match:
        hours = int(match.group("hours"))
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        _validate_minute_second_parts(minutes, seconds)
        return hours * 3600 + minutes * 60 + seconds

    raise ValueError("Timestamp must use MM:SS or HH:MM:SS format.")


def format_seconds(total_seconds: int) -> str:
    """Format seconds as HH:MM:SS."""

    if total_seconds < 0:
        raise ValueError("Seconds cannot be negative.")

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _validate_minute_second_parts(minutes: int, seconds: int) -> None:
    if minutes > 59 or seconds > 59:
        raise ValueError("Minutes and seconds must be between 00 and 59.")
