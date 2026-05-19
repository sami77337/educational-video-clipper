"""Smart pre-cut validation that warns users before video processing starts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.exclusions import ExclusionError, validate_exclusions
from src.time_utils import AR_INVALID_TIME_FORMAT, format_seconds, parse_timestamp
from src.validation import ClipRowInput


SMART_VERY_SHORT_CLIP_SECONDS = 3
SMART_VERY_LONG_CLIP_SECONDS = 30 * 60
SMART_SUSPICIOUS_TIME_SECONDS = 6 * 60 * 60
SMART_ERROR = "error"
SMART_WARNING = "warning"


@dataclass(frozen=True)
class SmartValidationIssue:
    """One smart validation error or warning."""

    severity: str
    row_number: int | None
    message_ar: str

    @property
    def is_error(self) -> bool:
        return self.severity == SMART_ERROR

    @property
    def is_warning(self) -> bool:
        return self.severity == SMART_WARNING


@dataclass(frozen=True)
class SmartValidationReport:
    """Summary of smart pre-cut validation results."""

    total_clips_count: int
    issues: list[SmartValidationIssue]

    @property
    def errors(self) -> list[SmartValidationIssue]:
        return [issue for issue in self.issues if issue.is_error]

    @property
    def warnings(self) -> list[SmartValidationIssue]:
        return [issue for issue in self.issues if issue.is_warning]

    @property
    def can_start_cutting(self) -> bool:
        return not self.errors


def validate_clips_before_cutting(
    rows: Iterable[ClipRowInput],
    *,
    known_video_duration_seconds: int | float | None = None,
) -> SmartValidationReport:
    """Validate clip rows for likely user mistakes without changing the rows."""

    row_list = list(rows)
    issues: list[SmartValidationIssue] = []
    parsed_ranges: list[tuple[int, int, int]] = []

    if not row_list:
        issues.append(_error(None, "لا توجد مقاطع للفحص. أضف مقطعًا واحدًا على الأقل."))
        return SmartValidationReport(total_clips_count=0, issues=issues)

    for row in row_list:
        start_seconds = _parse_required_time(row.row_number, row.start, "البداية", issues)
        end_seconds = _parse_required_time(row.row_number, row.end, "النهاية", issues)

        if not (row.title or "").strip():
            issues.append(_warning(row.row_number, f"تحذير في المقطع رقم {row.row_number}: عنوان المقطع فارغ"))

        if start_seconds is None or end_seconds is None:
            continue

        if end_seconds <= start_seconds:
            issues.append(_error(row.row_number, f"خطأ في المقطع رقم {row.row_number}: وقت النهاية قبل وقت البداية"))
            continue

        duration_seconds = end_seconds - start_seconds
        parsed_ranges.append((row.row_number, start_seconds, end_seconds))
        _add_duration_warnings(row.row_number, start_seconds, end_seconds, duration_seconds, issues)
        _add_known_duration_errors(
            row.row_number,
            start_seconds,
            end_seconds,
            known_video_duration_seconds,
            issues,
        )
        _add_exclusion_errors(row, start_seconds, end_seconds, issues)

    _add_overlap_warnings(parsed_ranges, issues)
    return SmartValidationReport(total_clips_count=len(row_list), issues=issues)


def format_smart_validation_report_ar(report: SmartValidationReport) -> str:
    """Format a smart validation summary for the Arabic log area."""

    lines = [
        "نتيجة الفحص الذكي قبل القص:",
        f"عدد المقاطع: {report.total_clips_count}",
        f"عدد الأخطاء: {len(report.errors)}",
        f"عدد التحذيرات: {len(report.warnings)}",
    ]

    if report.errors:
        lines.append("الأخطاء:")
        lines.extend(f"- {issue.message_ar}" for issue in report.errors)

    if report.warnings:
        lines.append("التحذيرات:")
        lines.extend(f"- {issue.message_ar}" for issue in report.warnings)

    if report.can_start_cutting:
        lines.append("النتيجة: يمكن بدء القص")
    else:
        lines.append("النتيجة: لا يمكن بدء القص قبل إصلاح الأخطاء")

    return "\n".join(lines)


def _parse_required_time(
    row_number: int,
    value: str,
    field_name_ar: str,
    issues: list[SmartValidationIssue],
) -> int | None:
    if value is None or not str(value).strip():
        issues.append(_error(row_number, f"خطأ في المقطع رقم {row_number}: وقت {field_name_ar} مفقود"))
        return None

    try:
        return parse_timestamp(str(value))
    except ValueError:
        issues.append(
            _error(
                row_number,
                f"خطأ في المقطع رقم {row_number}: {AR_INVALID_TIME_FORMAT} ({field_name_ar})",
            )
        )
        return None


def _add_duration_warnings(
    row_number: int,
    start_seconds: int,
    end_seconds: int,
    duration_seconds: int,
    issues: list[SmartValidationIssue],
) -> None:
    if duration_seconds < SMART_VERY_SHORT_CLIP_SECONDS:
        issues.append(_warning(row_number, f"تحذير في المقطع رقم {row_number}: المقطع قصير جدًا"))
    if duration_seconds > SMART_VERY_LONG_CLIP_SECONDS:
        issues.append(_warning(row_number, f"تحذير في المقطع رقم {row_number}: المقطع طويل جدًا"))
    if max(start_seconds, end_seconds) > SMART_SUSPICIOUS_TIME_SECONDS:
        issues.append(_warning(row_number, f"تحذير في المقطع رقم {row_number}: وقت البداية أو النهاية كبير بشكل غير معتاد"))


def _add_known_duration_errors(
    row_number: int,
    start_seconds: int,
    end_seconds: int,
    known_video_duration_seconds: int | float | None,
    issues: list[SmartValidationIssue],
) -> None:
    if known_video_duration_seconds is None:
        return

    try:
        video_duration = float(known_video_duration_seconds)
    except (TypeError, ValueError):
        return

    if video_duration <= 0:
        return

    if start_seconds > video_duration or end_seconds > video_duration:
        issues.append(_error(row_number, f"خطأ في المقطع رقم {row_number}: الوقت خارج مدة الفيديو"))


def _add_exclusion_errors(
    row: ClipRowInput,
    start_seconds: int,
    end_seconds: int,
    issues: list[SmartValidationIssue],
) -> None:
    exclusions_text = row.exclusions.strip() if row.exclusions else ""
    if not exclusions_text:
        return

    try:
        exclusion_errors = validate_exclusions(
            format_seconds(start_seconds),
            format_seconds(end_seconds),
            exclusions_text,
        )
    except (ExclusionError, ValueError) as error:
        exclusion_errors = [str(error)]

    for error in exclusion_errors:
        issues.append(_error(row.row_number, f"خطأ في المقطع رقم {row.row_number}: {error}"))


def _add_overlap_warnings(
    parsed_ranges: list[tuple[int, int, int]],
    issues: list[SmartValidationIssue],
) -> None:
    warned_pairs: set[tuple[int, int]] = set()
    sorted_ranges = sorted(parsed_ranges, key=lambda item: (item[1], item[2], item[0]))

    for index, (row_number, start_seconds, end_seconds) in enumerate(sorted_ranges):
        for other_row_number, other_start, other_end in sorted_ranges[index + 1:]:
            if other_start >= end_seconds:
                break
            if start_seconds < other_end and other_start < end_seconds:
                pair = tuple(sorted((row_number, other_row_number)))
                if pair in warned_pairs:
                    continue
                warned_pairs.add(pair)
                issues.append(
                    _warning(
                        row_number,
                        f"تحذير في المقطع رقم {row_number}: يوجد تداخل مع مقطع آخر",
                    )
                )
                issues.append(
                    _warning(
                        other_row_number,
                        f"تحذير في المقطع رقم {other_row_number}: يوجد تداخل مع مقطع آخر",
                    )
                )


def _error(row_number: int | None, message_ar: str) -> SmartValidationIssue:
    return SmartValidationIssue(SMART_ERROR, row_number, message_ar)


def _warning(row_number: int | None, message_ar: str) -> SmartValidationIssue:
    return SmartValidationIssue(SMART_WARNING, row_number, message_ar)
