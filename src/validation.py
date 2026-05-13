"""Validation helpers for user-provided clip settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.exclusions import ExclusionError, format_exclusions, validate_exclusions
from src.time_utils import AR_INVALID_TIME_FORMAT, parse_timestamp


@dataclass(frozen=True)
class ClipRowInput:
    """User-entered clip row values."""

    row_number: int
    title: str
    start: str
    end: str
    exclusions: str = ""


@dataclass(frozen=True)
class ValidationErrorDetail:
    """A validation error with an Arabic message for the UI."""

    row_number: int | None
    field: str
    message: str
    message_ar: str


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


def validate_clip_rows(rows: Iterable[ClipRowInput]) -> list[ValidationErrorDetail]:
    """Validate all clip table rows and return display-ready errors."""

    row_list = list(rows)
    if not row_list:
        return [
            ValidationErrorDetail(
                row_number=None,
                field="table",
                message="At least one clip row is required.",
                message_ar="أضف مقطعًا واحدًا على الأقل قبل المتابعة.",
            )
        ]

    errors: list[ValidationErrorDetail] = []
    for row in row_list:
        errors.extend(_validate_clip_row(row))

    return errors


def _validate_clip_row(row: ClipRowInput) -> list[ValidationErrorDetail]:
    errors: list[ValidationErrorDetail] = []

    title = row.title.strip() if row.title else ""
    start = row.start.strip() if row.start else ""
    end = row.end.strip() if row.end else ""

    if not title:
        errors.append(
            ValidationErrorDetail(
                row_number=row.row_number,
                field="title",
                message="Clip title is required.",
                message_ar=f"أدخل عنوان المقطع في الصف {row.row_number}.",
            )
        )

    start_seconds = _parse_row_timestamp(
        value=start,
        row_number=row.row_number,
        field="start",
        field_name_ar="البداية",
        errors=errors,
    )
    end_seconds = _parse_row_timestamp(
        value=end,
        row_number=row.row_number,
        field="end",
        field_name_ar="النهاية",
        errors=errors,
    )

    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        errors.append(
            ValidationErrorDetail(
                row_number=row.row_number,
                field="end",
                message="End time must be after start time.",
                message_ar=f"وقت النهاية يجب أن يكون بعد وقت البداية في الصف {row.row_number}.",
            )
        )

    if start_seconds is not None and end_seconds is not None and end_seconds > start_seconds:
        exclusions_text = row.exclusions.strip() if row.exclusions else ""
        if exclusions_text:
            try:
                exclusion_errors = validate_exclusions(start, end, exclusions_text)
            except (ExclusionError, ValueError) as error:
                exclusion_errors = [str(error)]

            for error in exclusion_errors:
                errors.append(
                    ValidationErrorDetail(
                        row_number=row.row_number,
                        field="exclusions",
                        message="Clip exclusions are invalid.",
                        message_ar=f"{error} في الصف {row.row_number}.",
                    )
                )

    return errors


def normalize_clip_exclusions(start: str, end: str, exclusions: str | None) -> str:
    """Normalize optional exclusions after validating against a clip range."""

    if exclusions is None or not exclusions.strip():
        return ""

    errors = validate_exclusions(start, end, exclusions)
    if errors:
        raise ValueError("\n".join(errors))

    return format_exclusions(exclusions)


def _parse_row_timestamp(
    value: str,
    row_number: int,
    field: str,
    field_name_ar: str,
    errors: list[ValidationErrorDetail],
) -> int | None:
    if not value:
        errors.append(
            ValidationErrorDetail(
                row_number=row_number,
                field=field,
                message=f"{field} time is required.",
                message_ar=f"أدخل وقت {field_name_ar} في الصف {row_number}.",
            )
        )
        return None

    try:
        return parse_timestamp(value)
    except ValueError:
        errors.append(
            ValidationErrorDetail(
                row_number=row_number,
                field=field,
                message=f"{field} time is invalid.",
                message_ar=f"{AR_INVALID_TIME_FORMAT} (وقت {field_name_ar} في الصف {row_number}).",
            )
        )
        return None
