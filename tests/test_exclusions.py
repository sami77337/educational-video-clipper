import pytest

from src.exclusions import (
    AR_EXCLUSION_OUTSIDE_MAIN_RANGE,
    AR_EXCLUSION_REMOVES_ENTIRE_CLIP,
    AR_EXCLUSION_START_AFTER_END,
    AR_EXCLUSIONS_OVERLAP,
    calculate_kept_segments,
    format_exclusions,
    normalize_exclusion_range,
    parse_exclusions,
    validate_exclusions,
)


def test_empty_exclusions_field_returns_no_ranges() -> None:
    assert parse_exclusions("") == []
    assert format_exclusions("") == ""


def test_whitespace_only_exclusions_field_returns_no_ranges() -> None:
    assert parse_exclusions("   \n\t  ") == []


def test_english_digit_exclusion_is_normalized() -> None:
    assert normalize_exclusion_range("27:40-28:20") == "00:27:40-00:28:20"


def test_arabic_indic_digit_exclusion_is_normalized() -> None:
    assert normalize_exclusion_range("٢٧:٤٠ - ٢٨:٢٠") == "00:27:40-00:28:20"


def test_spaces_around_colon_and_dash_are_normalized() -> None:
    assert normalize_exclusion_range("٢٧ : ٤٠ - ٢٨ : ٢٠") == "00:27:40-00:28:20"


def test_one_exclusion_parses() -> None:
    assert parse_exclusions("00:27:40 - 00:28:20") == ["00:27:40-00:28:20"]


def test_multiple_exclusions_parse() -> None:
    assert parse_exclusions("27:40-28:20, 28:55-29:05") == [
        "00:27:40-00:28:20",
        "00:28:55-00:29:05",
    ]


def test_exclusion_outside_main_range_returns_error() -> None:
    errors = validate_exclusions("00:26:56", "00:29:14", ["00:25:00-00:27:00"])

    assert AR_EXCLUSION_OUTSIDE_MAIN_RANGE in errors


def test_exclusion_start_after_end_returns_error() -> None:
    errors = validate_exclusions("00:26:56", "00:29:14", ["00:28:20-00:27:40"])

    assert AR_EXCLUSION_START_AFTER_END in errors


def test_overlapping_exclusions_return_error() -> None:
    errors = validate_exclusions(
        "00:10:00",
        "00:15:00",
        ["00:11:00-00:11:40", "00:11:30-00:12:00"],
    )

    assert AR_EXCLUSIONS_OVERLAP in errors


def test_exclusion_removing_entire_clip_returns_error() -> None:
    errors = validate_exclusions("00:10:00", "00:15:00", ["00:10:00-00:15:00"])

    assert AR_EXCLUSION_REMOVES_ENTIRE_CLIP in errors


def test_kept_segment_calculation_for_one_exclusion() -> None:
    assert calculate_kept_segments("00:26:56", "00:29:14", ["00:27:40-00:28:20"]) == [
        ("00:26:56", "00:27:40"),
        ("00:28:20", "00:29:14"),
    ]


def test_kept_segment_calculation_for_multiple_exclusions() -> None:
    assert calculate_kept_segments(
        "00:10:00",
        "00:15:00",
        ["00:11:00-00:11:30", "00:13:00-00:13:20"],
    ) == [
        ("00:10:00", "00:11:00"),
        ("00:11:30", "00:13:00"),
        ("00:13:20", "00:15:00"),
    ]


def test_touching_exclusions_are_allowed() -> None:
    assert validate_exclusions(
        "00:10:00",
        "00:15:00",
        ["00:11:00-00:11:30", "00:11:30-00:12:00"],
    ) == []


def test_calculate_kept_segments_raises_for_invalid_exclusion() -> None:
    with pytest.raises(ValueError):
        calculate_kept_segments("00:10:00", "00:15:00", ["00:10:00-00:15:00"])
