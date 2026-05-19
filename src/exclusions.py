"""Helpers for internal clip cuts / exclusion ranges."""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.time_utils import format_seconds, normalize_time_symbols, parse_timestamp


AR_INVALID_EXCLUSION_FORMAT = "صيغة الاستثناء غير صحيحة"
AR_EXCLUSION_START_AFTER_END = "بداية الاستثناء يجب أن تكون قبل نهايته"
AR_EXCLUSION_OUTSIDE_MAIN_RANGE = "الاستثناء خارج حدود المقطع"
AR_EXCLUSIONS_OVERLAP = "توجد استثناءات متداخلة"
AR_EXCLUSION_REMOVES_ENTIRE_CLIP = "الاستثناء يحذف المقطع كاملًا"

_TIME_PATTERN = r"\d{1,3}:\d{1,2}(?::\d{1,2})?"
_RANGE_PATTERN = re.compile(rf"({_TIME_PATTERN})\s*[-–—]\s*({_TIME_PATTERN})")


class ExclusionError(ValueError):
    """Raised when exclusion ranges cannot be parsed or validated."""


def parse_exclusions(text: str | None) -> list[str]:
    """Parse optional exclusion text into normalized HH:MM:SS-HH:MM:SS ranges."""

    if text is None or not str(text).strip():
        return []

    normalized_text = normalize_time_symbols(str(text))
    ranges = [_normalize_match(match) for match in _RANGE_PATTERN.finditer(normalized_text)]
    if not ranges:
        raise ExclusionError(AR_INVALID_EXCLUSION_FORMAT)

    return _sort_normalized_ranges(ranges)


def normalize_exclusion_range(range_text: str) -> str:
    """Normalize one exclusion range to HH:MM:SS-HH:MM:SS."""

    ranges = parse_exclusions(range_text)
    if len(ranges) != 1:
        raise ExclusionError(AR_INVALID_EXCLUSION_FORMAT)

    return ranges[0]


def validate_exclusions(
    main_start: str,
    main_end: str,
    exclusions: Iterable[str] | str | None,
) -> list[str]:
    """Validate exclusions against a main clip range and return clear errors."""

    normalized_exclusions = _normalize_exclusions_input(exclusions)
    if not normalized_exclusions:
        return []

    errors: list[str] = []
    main_start_seconds = parse_timestamp(main_start)
    main_end_seconds = parse_timestamp(main_end)
    exclusion_ranges = [_range_to_seconds(exclusion) for exclusion in normalized_exclusions]

    for start_seconds, end_seconds in exclusion_ranges:
        if start_seconds >= end_seconds:
            errors.append(AR_EXCLUSION_START_AFTER_END)
        if start_seconds < main_start_seconds or end_seconds > main_end_seconds:
            errors.append(AR_EXCLUSION_OUTSIDE_MAIN_RANGE)

    sorted_ranges = sorted(exclusion_ranges)
    for index, current_range in enumerate(sorted_ranges[:-1]):
        next_range = sorted_ranges[index + 1]
        if current_range[1] > next_range[0]:
            errors.append(AR_EXCLUSIONS_OVERLAP)
            break

    if not errors and not _calculate_kept_segment_seconds(main_start_seconds, main_end_seconds, sorted_ranges):
        errors.append(AR_EXCLUSION_REMOVES_ENTIRE_CLIP)

    return _deduplicate_errors(errors)


def calculate_kept_segments(
    main_start: str,
    main_end: str,
    exclusions: Iterable[str] | str | None,
) -> list[tuple[str, str]]:
    """Return kept clip segments after removing internal exclusions."""

    errors = validate_exclusions(main_start, main_end, exclusions)
    if errors:
        raise ExclusionError("\n".join(errors))

    main_start_seconds = parse_timestamp(main_start)
    main_end_seconds = parse_timestamp(main_end)
    exclusion_ranges = sorted(_range_to_seconds(exclusion) for exclusion in _normalize_exclusions_input(exclusions))
    return [
        (format_seconds(start_seconds), format_seconds(end_seconds))
        for start_seconds, end_seconds in _calculate_kept_segment_seconds(
            main_start_seconds,
            main_end_seconds,
            exclusion_ranges,
        )
    ]


def format_exclusions(exclusions: Iterable[str] | str | None) -> str:
    """Format exclusions as a comma-separated normalized string."""

    return ", ".join(_normalize_exclusions_input(exclusions))


def _normalize_exclusions_input(exclusions: Iterable[str] | str | None) -> list[str]:
    if exclusions is None:
        return []
    if isinstance(exclusions, str):
        return parse_exclusions(exclusions)

    normalized: list[str] = []
    for exclusion in exclusions:
        if exclusion is None or not str(exclusion).strip():
            continue
        normalized.append(normalize_exclusion_range(str(exclusion)))

    return _sort_normalized_ranges(normalized)


def _normalize_match(match: re.Match[str]) -> str:
    start = parse_timestamp(match.group(1))
    end = parse_timestamp(match.group(2))
    return f"{format_seconds(start)}-{format_seconds(end)}"


def _range_to_seconds(exclusion: str) -> tuple[int, int]:
    match = _RANGE_PATTERN.fullmatch(normalize_time_symbols(exclusion))
    if not match:
        raise ExclusionError(AR_INVALID_EXCLUSION_FORMAT)

    return parse_timestamp(match.group(1)), parse_timestamp(match.group(2))


def _sort_normalized_ranges(ranges: list[str]) -> list[str]:
    return sorted(ranges, key=_range_to_seconds)


def _calculate_kept_segment_seconds(
    main_start_seconds: int,
    main_end_seconds: int,
    exclusion_ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    kept_segments: list[tuple[int, int]] = []
    cursor = main_start_seconds

    for exclusion_start, exclusion_end in exclusion_ranges:
        if cursor < exclusion_start:
            kept_segments.append((cursor, exclusion_start))
        cursor = max(cursor, exclusion_end)

    if cursor < main_end_seconds:
        kept_segments.append((cursor, main_end_seconds))

    return kept_segments


def _deduplicate_errors(errors: list[str]) -> list[str]:
    unique_errors: list[str] = []
    for error in errors:
        if error not in unique_errors:
            unique_errors.append(error)

    return unique_errors
