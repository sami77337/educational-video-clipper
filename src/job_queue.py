"""Data models for future multi-video job queue support.

This module is intentionally independent from UI, download, and cutting code.
It provides a safe internal representation that future queue execution can
consume without changing the current single-video workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle state for video and clip jobs."""

    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    VALIDATION_ERROR = "validation_error"
    WARNING = "warning"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CUTTING = "cutting"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class VideoSourceType(str, Enum):
    """Supported source kinds for queued video jobs."""

    LOCAL = "local"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"


@dataclass
class JobSettings:
    """Current and future-safe processing options for a queued job."""

    pre_roll_seconds: float = 0.0
    post_roll_seconds: float = 0.0
    quality_preset: str = "default"
    speed: float = 1.0
    volume_percent: int = 100
    use_browser_login: bool = False
    browser_name: str = "chrome"
    watermark_enabled: bool = False
    silence_reduction_enabled: bool = False
    high_priority: bool = False


@dataclass
class ClipJob:
    """One clip request inside a queued video job."""

    title: str
    start: str
    end: str
    exclusions: str = ""
    notes: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.DRAFT
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = JobStatus(self.status)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.errors) or self.status in {
            JobStatus.VALIDATION_ERROR,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }

    def mark_status(self, status: JobStatus | str) -> None:
        self.status = JobStatus(status)


@dataclass
class VideoJob:
    """A future queue item representing one source video and its clips."""

    source_type: VideoSourceType | str
    source: str
    title: str
    clips: list[ClipJob] = field(default_factory=list)
    settings: JobSettings = field(default_factory=JobSettings)
    status: JobStatus = JobStatus.DRAFT
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.source_type = VideoSourceType(self.source_type)
        self.status = JobStatus(self.status)

    @property
    def clip_count(self) -> int:
        return len(self.clips)

    @property
    def warning_count(self) -> int:
        return len(self.warnings) + sum(clip.warning_count for clip in self.clips)

    @property
    def error_count(self) -> int:
        return len(self.errors) + sum(clip.error_count for clip in self.clips)

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.errors) or self.status in {
            JobStatus.VALIDATION_ERROR,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        } or any(clip.has_blocking_errors for clip in self.clips)

    @property
    def can_start(self) -> bool:
        return (
            self.status in {JobStatus.READY, JobStatus.WARNING, JobStatus.QUEUED}
            and bool(self.clips)
            and not self.has_blocking_errors
        )

    def mark_status(self, status: JobStatus | str) -> None:
        self.status = JobStatus(status)

    def add_clip(self, clip: ClipJob) -> None:
        self.clips.append(clip)
