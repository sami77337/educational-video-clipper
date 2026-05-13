"""Validation helpers for user-provided clip settings."""

from __future__ import annotations

from src.time_utils import parse_timestamp


def validate_clip_range(start: str, end: str) -> tuple[int, int]:
    """Validate a clip range and return start/end seconds."""

    start_seconds = parse_timestamp(start)
    end_seconds = parse_timestamp(end)

    if end_seconds <= start_seconds:
        raise ValueError("End time must be after start time.")

    return start_seconds, end_seconds


def validate_required_text(value: str, field_name: str) -> str:
    """Validate that a text field contains a non-empty value."""

    if value is None or not value.strip():
        raise ValueError(f"{field_name} is required.")

    return value.strip()
