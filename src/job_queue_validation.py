"""Basic validation helpers for passive queue jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.job_queue import JobStatus, VideoJob, VideoSourceType
from src.readiness import WINDOWS_LONG_PATH_WARNING_LENGTH


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
YOUTUBE_URL_PATTERN = re.compile(r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE)
FACEBOOK_URL_PATTERN = re.compile(r"^(?:https?://)?(?:www\.|m\.)?(?:facebook\.com|fb\.watch)/", re.IGNORECASE)


@dataclass(frozen=True)
class JobQueueValidationResult:
    """Validation messages and resulting status for a queue job."""

    status: JobStatus
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_queue_job(job: VideoJob) -> JobQueueValidationResult:
    """Validate one queued job without downloading, cutting, or probing media."""

    if job.source_type == VideoSourceType.LOCAL:
        return _validate_local_job(job)
    return _validate_url_job(job)


def apply_queue_validation_result(job: VideoJob, result: JobQueueValidationResult) -> None:
    """Copy validation status and messages back to the mutable queue job."""

    job.status = result.status
    job.warnings = list(result.warnings)
    job.errors = list(result.errors)


def format_queue_validation_result_ar(result: JobQueueValidationResult) -> str:
    """Format queue validation output for the Arabic log area."""

    lines = list(result.messages)
    if result.errors:
        lines.append("لا يمكن بدء المهمة قبل إصلاح الأخطاء")
    return "\n".join(lines)


def _validate_local_job(job: VideoJob) -> JobQueueValidationResult:
    messages: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    source_text = job.source.strip()

    if not source_text:
        errors.append("مسار الملف فارغ")
        messages.append("مسار الملف فارغ")
        return _build_result(messages, warnings, errors)

    path = Path(source_text)
    if _is_dangerously_long_path(source_text):
        warnings.append("المسار طويل وقد يسبب مشكلة في Windows")
        messages.append("المسار طويل وقد يسبب مشكلة في Windows")

    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        errors.append("امتداد الملف لا يبدو كفيديو مدعوم")
        messages.append("امتداد الملف لا يبدو كفيديو مدعوم")

    if path.exists() and path.is_file():
        messages.append("الملف موجود")
    else:
        errors.append("لم يتم العثور على الملف")
        messages.append("لم يتم العثور على الملف")

    return _build_result(messages, warnings, errors)


def _validate_url_job(job: VideoJob) -> JobQueueValidationResult:
    messages: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    url = job.source.strip()

    if not url:
        errors.append("الرابط فارغ")
        messages.append("الرابط فارغ")
        return _build_result(messages, warnings, errors)

    if _is_dangerously_long_path(url):
        warnings.append("المسار طويل وقد يسبب مشكلة في Windows")
        messages.append("المسار طويل وقد يسبب مشكلة في Windows")

    if job.source_type == VideoSourceType.YOUTUBE and _looks_like_youtube_url(url):
        messages.append("الرابط صالح مبدئيًا")
    elif job.source_type == VideoSourceType.FACEBOOK and _looks_like_facebook_url(url):
        messages.append("الرابط صالح مبدئيًا")
    else:
        errors.append("الرابط غير مدعوم حاليًا")
        messages.append("الرابط غير مدعوم حاليًا")

    return _build_result(messages, warnings, errors)


def _looks_like_youtube_url(url: str) -> bool:
    return YOUTUBE_URL_PATTERN.search(url) is not None


def _looks_like_facebook_url(url: str) -> bool:
    return FACEBOOK_URL_PATTERN.search(url) is not None


def _is_dangerously_long_path(value: str) -> bool:
    return len(value) >= WINDOWS_LONG_PATH_WARNING_LENGTH


def _build_result(
    messages: list[str],
    warnings: list[str],
    errors: list[str],
) -> JobQueueValidationResult:
    if errors:
        status = JobStatus.VALIDATION_ERROR
    elif warnings:
        status = JobStatus.WARNING
    else:
        status = JobStatus.READY
    return JobQueueValidationResult(status=status, messages=messages, warnings=warnings, errors=errors)
