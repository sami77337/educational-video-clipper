import pytest

from src.validation import ClipRowInput, validate_clip_range, validate_clip_rows, validate_required_text


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


def test_validate_clip_rows_accepts_valid_rows() -> None:
    rows = [ClipRowInput(row_number=1, title="مقدمة الدرس", start="00:10", end="00:30")]

    assert validate_clip_rows(rows) == []


def test_validate_clip_rows_requires_at_least_one_row() -> None:
    errors = validate_clip_rows([])

    assert len(errors) == 1
    assert errors[0].field == "table"
    assert "مقطعًا واحدًا" in errors[0].message_ar


def test_validate_clip_rows_reports_missing_title_in_arabic() -> None:
    rows = [ClipRowInput(row_number=2, title=" ", start="00:10", end="00:30")]

    errors = validate_clip_rows(rows)

    assert errors[0].field == "title"
    assert "الصف 2" in errors[0].message_ar


def test_validate_clip_rows_reports_invalid_start_time() -> None:
    rows = [ClipRowInput(row_number=1, title="درس", start="1:99", end="00:30")]

    errors = validate_clip_rows(rows)

    assert errors[0].field == "start"
    assert "أمثلة صحيحة: 4:15 أو 00:04:15" in errors[0].message_ar


def test_validate_clip_rows_reports_end_before_start() -> None:
    rows = [ClipRowInput(row_number=1, title="درس", start="00:30", end="00:10")]

    errors = validate_clip_rows(rows)

    assert errors[0].field == "end"
    assert "بعد وقت البداية" in errors[0].message_ar


def test_validate_clip_rows_accepts_empty_exclusions() -> None:
    rows = [ClipRowInput(row_number=1, title="درس", start="00:10", end="00:30", exclusions="   ")]

    assert validate_clip_rows(rows) == []


def test_validate_clip_rows_reports_invalid_exclusions() -> None:
    rows = [ClipRowInput(row_number=1, title="درس", start="00:10", end="00:30", exclusions="00:05-00:06")]

    errors = validate_clip_rows(rows)

    assert errors[0].field == "exclusions"
    assert "الاستثناء خارج حدود المقطع" in errors[0].message_ar
