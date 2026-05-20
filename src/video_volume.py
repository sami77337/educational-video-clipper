"""Helpers for optional final clip audio volume control."""

from __future__ import annotations

import math


DEFAULT_VOLUME_PERCENT = 100
MIN_VOLUME_PERCENT = 1
MAX_VOLUME_PERCENT = 400
AR_INVALID_VOLUME_PERCENT = "قيمة مستوى الصوت غير صحيحة"
AR_VOLUME_APPLIED = "تم تطبيق مستوى الصوت"


class VideoVolumeError(ValueError):
    """Raised when an audio volume value cannot be used safely."""


def normalize_volume_percent(value: float | int | str | None) -> int:
    """Return a validated integer audio volume percent."""

    if value is None:
        raise VideoVolumeError(AR_INVALID_VOLUME_PERCENT)

    try:
        volume = float(str(value).strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError) as error:
        raise VideoVolumeError(AR_INVALID_VOLUME_PERCENT) from error

    if not math.isfinite(volume) or volume < MIN_VOLUME_PERCENT or volume > MAX_VOLUME_PERCENT:
        raise VideoVolumeError(AR_INVALID_VOLUME_PERCENT)

    return int(round(volume))


def volume_is_default(volume_percent: float | int | str | None) -> bool:
    """Return True when the volume should preserve the old output behavior."""

    return normalize_volume_percent(volume_percent) == DEFAULT_VOLUME_PERCENT


def format_volume_percent(volume_percent: float | int | str | None) -> str:
    """Format a volume percent for reports."""

    return f"{normalize_volume_percent(volume_percent)}%"


def build_audio_volume_filter(volume_percent: float | int | str | None) -> str:
    """Build the FFmpeg audio volume filter for a percent value."""

    ratio = normalize_volume_percent(volume_percent) / 100
    return f"volume={_format_filter_number(ratio)}"


def _format_filter_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
