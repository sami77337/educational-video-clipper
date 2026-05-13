import pytest

from src.validation import validate_clip_range, validate_required_text


def test_validate_clip_range_returns_seconds() -> None:
    assert validate_clip_range("00:10", "00:20") == (10, 20)


def test_validate_clip_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError):
        validate_clip_range("00:20", "00:10")


def test_validate_required_text_strips_value() -> None:
    assert validate_required_text("  lesson  ", "Title") == "lesson"


def test_validate_required_text_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        validate_required_text(" ", "Title")
