from __future__ import annotations

from src.smart_validation import (
    format_smart_validation_report_ar,
    validate_clips_before_cutting,
)
from src.validation import ClipRowInput


def _row(
    number: int = 1,
    title: str = "مقطع",
    start: str = "00:00:10",
    end: str = "00:00:20",
    exclusions: str = "",
) -> ClipRowInput:
    return ClipRowInput(
        row_number=number,
        title=title,
        start=start,
        end=end,
        exclusions=exclusions,
    )


def test_smart_validation_accepts_valid_clip_rows() -> None:
    report = validate_clips_before_cutting([_row()])

    assert report.total_clips_count == 1
    assert report.can_start_cutting
    assert report.errors == []
    assert report.warnings == []
    assert "النتيجة: يمكن بدء القص" in format_smart_validation_report_ar(report)


def test_smart_validation_reports_missing_start_and_end_times() -> None:
    report = validate_clips_before_cutting([_row(start="", end="")])

    assert not report.can_start_cutting
    messages = [issue.message_ar for issue in report.errors]
    assert any("وقت البداية مفقود" in message for message in messages)
    assert any("وقت النهاية مفقود" in message for message in messages)


def test_smart_validation_reports_end_before_start() -> None:
    report = validate_clips_before_cutting([_row(start="00:00:20", end="00:00:10")])

    assert not report.can_start_cutting
    assert any("وقت النهاية قبل وقت البداية" in issue.message_ar for issue in report.errors)


def test_smart_validation_reports_time_outside_known_video_duration() -> None:
    report = validate_clips_before_cutting(
        [_row(start="00:01:50", end="00:02:10")],
        known_video_duration_seconds=120,
    )

    assert not report.can_start_cutting
    assert any("الوقت خارج مدة الفيديو" in issue.message_ar for issue in report.errors)


def test_smart_validation_warns_for_very_short_clip() -> None:
    report = validate_clips_before_cutting([_row(start="00:00:10", end="00:00:12")])

    assert report.can_start_cutting
    assert any("المقطع قصير جدًا" in issue.message_ar for issue in report.warnings)


def test_smart_validation_warns_for_very_long_clip() -> None:
    report = validate_clips_before_cutting([_row(start="00:00:00", end="00:31:00")])

    assert report.can_start_cutting
    assert any("المقطع طويل جدًا" in issue.message_ar for issue in report.warnings)


def test_smart_validation_warns_for_suspicious_time_values() -> None:
    report = validate_clips_before_cutting([_row(start="06:00:01", end="06:00:10")])

    assert report.can_start_cutting
    assert any("كبير بشكل غير معتاد" in issue.message_ar for issue in report.warnings)


def test_smart_validation_warns_for_overlapping_clips() -> None:
    report = validate_clips_before_cutting(
        [
            _row(number=1, start="00:00:10", end="00:00:30"),
            _row(number=2, start="00:00:20", end="00:00:40"),
        ]
    )

    assert report.can_start_cutting
    assert len([issue for issue in report.warnings if "يوجد تداخل" in issue.message_ar]) == 2


def test_smart_validation_warns_for_empty_clip_title() -> None:
    report = validate_clips_before_cutting([_row(title="  ")])

    assert report.can_start_cutting
    assert any("عنوان المقطع فارغ" in issue.message_ar for issue in report.warnings)


def test_smart_validation_reports_exclusion_outside_clip_boundaries() -> None:
    report = validate_clips_before_cutting(
        [_row(start="00:00:00", end="00:10:00", exclusions="00:11:00-00:12:00")]
    )

    assert not report.can_start_cutting
    assert any("الاستثناء خارج حدود المقطع" in issue.message_ar for issue in report.errors)


def test_smart_validation_reports_invalid_exclusion_start_end() -> None:
    report = validate_clips_before_cutting(
        [_row(start="00:00:00", end="00:10:00", exclusions="00:04:00-00:03:00")]
    )

    assert not report.can_start_cutting
    assert any("بداية الاستثناء يجب أن تكون قبل نهايته" in issue.message_ar for issue in report.errors)


def test_smart_validation_summary_reports_counts_and_blocking_status() -> None:
    report = validate_clips_before_cutting(
        [
            _row(number=1, start="00:00:10", end="00:00:09"),
            _row(number=2, title="", start="00:00:00", end="00:00:02"),
        ]
    )

    summary = format_smart_validation_report_ar(report)
    assert "عدد المقاطع: 2" in summary
    assert "عدد الأخطاء: 1" in summary
    assert "عدد التحذيرات: 2" in summary
    assert "النتيجة: لا يمكن بدء القص قبل إصلاح الأخطاء" in summary
