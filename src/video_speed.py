"""Helpers for optional final clip speed control."""

from __future__ import annotations

import math


DEFAULT_VIDEO_SPEED = 1.0
MIN_VIDEO_SPEED = 0.01
MAX_VIDEO_SPEED = 4.0
AR_INVALID_VIDEO_SPEED = "قيمة سرعة الفيديو غير صحيحة"
AR_VIDEO_SPEED_APPLIED = "تم تطبيق سرعة الفيديو"


class VideoSpeedError(ValueError):
    """Raised when a video speed value cannot be used safely."""


def normalize_video_speed(value: float | int | str | None) -> float:
    """Return a validated positive speed factor."""

    if value is None:
        raise VideoSpeedError(AR_INVALID_VIDEO_SPEED)

    try:
        speed = float(str(value).strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError) as error:
        raise VideoSpeedError(AR_INVALID_VIDEO_SPEED) from error

    if not math.isfinite(speed) or speed < MIN_VIDEO_SPEED or speed > MAX_VIDEO_SPEED:
        raise VideoSpeedError(AR_INVALID_VIDEO_SPEED)

    return speed


def video_speed_is_default(speed: float | int | str | None) -> bool:
    """Return True when the speed should preserve the old output behavior."""

    return math.isclose(normalize_video_speed(speed), DEFAULT_VIDEO_SPEED, rel_tol=0, abs_tol=1e-9)


def speed_adjusted_duration(duration_seconds: float | int, speed: float | int | str | None) -> float:
    """Return the expected output duration after applying speed."""

    normalized_speed = normalize_video_speed(speed)
    return float(duration_seconds) / normalized_speed


def format_video_speed(speed: float | int | str | None) -> str:
    """Format a speed factor for commands and reports."""

    normalized_speed = normalize_video_speed(speed)
    return f"{normalized_speed:.3f}".rstrip("0").rstrip(".")


def build_video_speed_filter(speed: float | int | str | None) -> str:
    """Build the FFmpeg video filter for a speed factor."""

    return f"setpts=PTS/{format_video_speed(speed)}"


def build_audio_speed_filter(speed: float | int | str | None) -> str:
    """Build an FFmpeg atempo chain that keeps audio synchronized."""

    remaining = normalize_video_speed(speed)
    factors: list[float] = []

    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0

    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5

    factors.append(remaining)
    return ",".join(f"atempo={format_video_speed(factor)}" for factor in factors)
