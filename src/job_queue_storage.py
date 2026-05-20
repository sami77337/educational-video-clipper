"""JSON storage helpers for queue state.

This module is intentionally limited to safe data serialization. It does not
start downloads, cutting, FFmpeg, yt-dlp, or any queue execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.job_queue import ClipJob, JobSettings, JobStatus, VideoJob, VideoSourceType
from src.video_volume import DEFAULT_VOLUME_PERCENT, VideoVolumeError, normalize_volume_percent


QUEUE_STATE_VERSION = 1
SENSITIVE_QUERY_MARKERS = (
    "token",
    "cookie",
    "secret",
    "password",
    "passwd",
    "auth",
    "session",
    "credential",
    "key",
)
VOLATILE_STATUSES = {
    JobStatus.VALIDATING,
    JobStatus.DOWNLOADING,
    JobStatus.CUTTING,
    JobStatus.VERIFYING,
}


class QueueStorageError(ValueError):
    """Raised when queue JSON cannot be saved or loaded safely."""


def save_queue_jobs(jobs: list[VideoJob], file_path: str | Path) -> None:
    """Save queue jobs to a UTF-8 JSON file."""

    try:
        path = Path(file_path)
        path.write_text(queue_jobs_to_json(jobs), encoding="utf-8")
    except OSError as exc:
        raise QueueStorageError("فشل حفظ قائمة الانتظار") from exc


def load_queue_jobs(file_path: str | Path) -> list[VideoJob]:
    """Load queue jobs from a UTF-8 JSON file."""

    try:
        raw_text = Path(file_path).read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueStorageError("ملف قائمة الانتظار غير صالح أو غير متوافق") from exc

    return queue_jobs_from_data(data)


def queue_jobs_to_json(jobs: list[VideoJob]) -> str:
    """Serialize queue jobs to a stable JSON string."""

    return json.dumps(queue_jobs_to_data(jobs), ensure_ascii=False, indent=2)


def queue_jobs_to_data(jobs: list[VideoJob]) -> dict[str, Any]:
    """Convert queue jobs to JSON-compatible data."""

    return {
        "schema_version": QUEUE_STATE_VERSION,
        "jobs": [_video_job_to_data(job) for job in jobs],
    }


def queue_jobs_from_data(data: Any) -> list[VideoJob]:
    """Build queue jobs from JSON-compatible data."""

    if not isinstance(data, dict) or data.get("schema_version") != QUEUE_STATE_VERSION:
        raise QueueStorageError("ملف قائمة الانتظار غير صالح أو غير متوافق")

    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, list):
        raise QueueStorageError("ملف قائمة الانتظار غير صالح أو غير متوافق")

    try:
        return [_video_job_from_data(raw_job) for raw_job in raw_jobs]
    except (TypeError, ValueError) as exc:
        raise QueueStorageError("ملف قائمة الانتظار غير صالح أو غير متوافق") from exc


def _video_job_to_data(job: VideoJob) -> dict[str, Any]:
    return {
        "source_type": job.source_type.value,
        "source": _strip_sensitive_url_parts(job.source),
        "title": job.title,
        "clips": [_clip_job_to_data(clip) for clip in job.clips],
        "settings": _settings_to_data(job.settings),
        "high_priority": job.settings.high_priority,
        "status": _safe_status(job.status).value,
        "warnings": list(job.warnings),
        "errors": list(job.errors),
    }


def _video_job_from_data(data: Any) -> VideoJob:
    if not isinstance(data, dict):
        raise TypeError("job must be an object")

    settings = _settings_from_data(data.get("settings"), high_priority=data.get("high_priority"))
    return VideoJob(
        source_type=VideoSourceType(data["source_type"]),
        source=str(data.get("source", "")),
        title=str(data.get("title", "")),
        clips=[_clip_job_from_data(raw_clip) for raw_clip in _list_of_dicts(data.get("clips"))],
        settings=settings,
        status=_safe_status(JobStatus(data.get("status", JobStatus.DRAFT.value))),
        warnings=_list_of_strings(data.get("warnings")),
        errors=_list_of_strings(data.get("errors")),
    )


def _clip_job_to_data(clip: ClipJob) -> dict[str, Any]:
    return {
        "title": clip.title,
        "start": clip.start,
        "end": clip.end,
        "exclusions": clip.exclusions,
        "notes": list(clip.notes),
        "status": _safe_status(clip.status).value,
        "warnings": list(clip.warnings),
        "errors": list(clip.errors),
    }


def _clip_job_from_data(data: Any) -> ClipJob:
    if not isinstance(data, dict):
        raise TypeError("clip must be an object")

    return ClipJob(
        title=str(data.get("title", "")),
        start=str(data.get("start", "")),
        end=str(data.get("end", "")),
        exclusions=str(data.get("exclusions", "")),
        notes=_list_of_strings(data.get("notes")),
        status=_safe_status(JobStatus(data.get("status", JobStatus.DRAFT.value))),
        warnings=_list_of_strings(data.get("warnings")),
        errors=_list_of_strings(data.get("errors")),
    )


def _settings_to_data(settings: JobSettings) -> dict[str, Any]:
    return {
        "pre_roll_seconds": settings.pre_roll_seconds,
        "post_roll_seconds": settings.post_roll_seconds,
        "quality_preset": settings.quality_preset,
        "speed": settings.speed,
        "volume_percent": settings.volume_percent,
        "watermark_enabled": settings.watermark_enabled,
        "silence_reduction_enabled": settings.silence_reduction_enabled,
        "high_priority": settings.high_priority,
    }


def _settings_from_data(data: Any, *, high_priority: Any = None) -> JobSettings:
    if not isinstance(data, dict):
        data = {}

    high_priority_value = data.get("high_priority", high_priority)
    return JobSettings(
        pre_roll_seconds=_float_or_default(data.get("pre_roll_seconds"), 0.0),
        post_roll_seconds=_float_or_default(data.get("post_roll_seconds"), 0.0),
        quality_preset=str(data.get("quality_preset") or "default"),
        speed=_float_or_default(data.get("speed"), 1.0),
        volume_percent=_volume_or_default(data.get("volume_percent"), DEFAULT_VOLUME_PERCENT),
        watermark_enabled=bool(data.get("watermark_enabled", False)),
        silence_reduction_enabled=bool(data.get("silence_reduction_enabled", False)),
        high_priority=bool(high_priority_value) if high_priority_value is not None else False,
    )


def _safe_status(status: JobStatus) -> JobStatus:
    return JobStatus.DRAFT if status in VOLATILE_STATUSES else status


def _strip_sensitive_url_parts(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value

    safe_query_items = [
        (key, query_value)
        for key, query_value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_sensitive_key(key)
    ]
    safe_fragment = "" if _contains_sensitive_marker(parts.fragment) else parts.fragment
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(safe_query_items, doseq=True),
            safe_fragment,
        )
    )


def _is_sensitive_key(key: str) -> bool:
    return _contains_sensitive_marker(key)


def _contains_sensitive_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in SENSITIVE_QUERY_MARKERS)


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    if not all(isinstance(item, dict) for item in value):
        raise TypeError("expected a list of objects")
    return value


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _volume_or_default(value: Any, default: int) -> int:
    try:
        return normalize_volume_percent(value)
    except VideoVolumeError:
        return default
