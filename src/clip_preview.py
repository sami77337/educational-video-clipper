"""Temporary preview clip helpers.

This module is intentionally separate from final project processing. It creates
short preview files in a temporary folder only and does not classify, ZIP, or
write processing reports.
"""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.clip_padding import ClipPadding, calculate_effective_clip_range
from src.video.ffmpeg_commands import build_ffmpeg_command
from src.video.ffmpeg_runner import AR_FFMPEG_NOT_FOUND, FfmpegRunnerError, run_ffmpeg_command


START_PREVIEW_BEFORE_SECONDS = 10
START_PREVIEW_AFTER_SECONDS = 20
END_PREVIEW_BEFORE_SECONDS = 20
END_PREVIEW_AFTER_SECONDS = 10
MAX_FULL_CLIP_PREVIEW_SECONDS = 10 * 60
PREVIEW_FOLDER_NAME = "temp_preview"


class ClipPreviewKind(str, Enum):
    """Supported preview modes for a selected clip row."""

    START = "start"
    END = "end"
    FULL = "full"


@dataclass(frozen=True)
class PreviewRange:
    """Temporary preview range in seconds."""

    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        duration = self.end_seconds - self.start_seconds
        if duration <= 0:
            raise ValueError("Preview end time must be after start time.")
        return duration


class ClipPreviewError(RuntimeError):
    """Raised when a temporary preview cannot be created."""


def calculate_preview_range(
    preview_kind: ClipPreviewKind | str,
    clip_start_seconds: int | float,
    clip_end_seconds: int | float,
    *,
    video_duration_seconds: int | float | None = None,
    clip_padding: ClipPadding | None = None,
) -> PreviewRange:
    """Calculate a safe temporary preview range for a selected clip."""

    kind = ClipPreviewKind(preview_kind)
    clip_start = float(clip_start_seconds)
    clip_end = float(clip_end_seconds)
    if clip_end <= clip_start:
        raise ValueError("Clip end time must be after start time.")

    if kind is ClipPreviewKind.START:
        start = max(0.0, clip_start - START_PREVIEW_BEFORE_SECONDS)
        end = clip_start + START_PREVIEW_AFTER_SECONDS
    elif kind is ClipPreviewKind.END:
        start = max(0.0, clip_end - END_PREVIEW_BEFORE_SECONDS)
        end = clip_end + END_PREVIEW_AFTER_SECONDS
    else:
        effective_range = calculate_effective_clip_range(
            clip_start,
            clip_end,
            clip_padding or ClipPadding(),
            video_duration_seconds,
        )
        start = effective_range.start_seconds
        end = effective_range.end_seconds

    if video_duration_seconds is not None:
        duration = float(video_duration_seconds)
        if duration >= 0:
            end = min(end, duration)

    preview_range = PreviewRange(start, end)
    preview_range.duration_seconds
    return preview_range


def default_preview_folder() -> Path:
    """Return a system temp preview folder outside the project output tree."""

    return Path(tempfile.gettempdir()) / "AlmiqsAlBaseet" / PREVIEW_FOLDER_NAME


def create_preview_clip(
    input_video_path: str | Path,
    preview_range: PreviewRange,
    *,
    preview_folder: str | Path | None = None,
    clip_number: int | str = "selected",
    preview_kind: ClipPreviewKind | str = ClipPreviewKind.FULL,
    runner=subprocess.run,
) -> Path:
    """Create a temporary mp4 preview and return its path."""

    source_path = Path(input_video_path)
    if not source_path.is_file():
        raise ClipPreviewError("يجب اختيار فيديو محلي أو تنزيل الفيديو أولًا")

    target_folder = Path(preview_folder) if preview_folder is not None else default_preview_folder()
    target_folder.mkdir(parents=True, exist_ok=True)
    kind = ClipPreviewKind(preview_kind)
    output_path = target_folder / f"preview_{clip_number}_{kind.value}_{uuid.uuid4().hex}.mp4"
    command = build_ffmpeg_command(
        source_path,
        output_path,
        preview_range.start_seconds,
        preview_range.duration_seconds,
    )

    try:
        run_ffmpeg_command(command, output_path, runner)
    except FileNotFoundError as error:
        raise ClipPreviewError(AR_FFMPEG_NOT_FOUND) from error
    except FfmpegRunnerError as error:
        raise ClipPreviewError(str(error)) from error

    return output_path
