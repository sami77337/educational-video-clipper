"""Helpers for optional black video fade-in/fade-out effects."""

from __future__ import annotations

import math
from dataclasses import dataclass


DEFAULT_FADE_IN_SECONDS = 0.5
DEFAULT_FADE_OUT_SECONDS = 0.5
ALLOWED_FADE_DURATIONS = (0.25, 0.5, 1.0, 1.5, 2.0)
AR_FADE_DURATION_CLAMPED = "مدة المقطع قصيرة، تم تقليل مدة التدرج تلقائيًا"


class VideoFadeError(ValueError):
    """Raised when fade settings are outside the supported safe values."""


@dataclass(frozen=True)
class ClipFade:
    """Optional black fade settings for one exported clip."""

    enabled: bool = False
    fade_in_seconds: float = DEFAULT_FADE_IN_SECONDS
    fade_out_seconds: float = DEFAULT_FADE_OUT_SECONDS


@dataclass(frozen=True)
class ResolvedFadeDurations:
    """Fade durations adjusted to a concrete output duration."""

    fade_in_seconds: float
    fade_out_seconds: float
    clamped: bool = False


def normalize_fade_duration(value: float | int | str | None) -> float:
    """Return a supported fade duration in seconds."""

    try:
        duration = float(value)
    except (TypeError, ValueError):
        raise VideoFadeError("قيمة مدة التدرج غير صحيحة") from None

    for allowed in ALLOWED_FADE_DURATIONS:
        if math.isclose(duration, allowed, rel_tol=0, abs_tol=1e-9):
            return allowed
    raise VideoFadeError("قيمة مدة التدرج غير صحيحة")


def normalize_clip_fade(
    enabled: bool = False,
    fade_in_seconds: float | int | str | None = DEFAULT_FADE_IN_SECONDS,
    fade_out_seconds: float | int | str | None = DEFAULT_FADE_OUT_SECONDS,
) -> ClipFade:
    """Normalize fade settings while preserving disabled safe defaults."""

    if not enabled:
        return ClipFade()
    return ClipFade(
        enabled=True,
        fade_in_seconds=normalize_fade_duration(fade_in_seconds),
        fade_out_seconds=normalize_fade_duration(fade_out_seconds),
    )


def resolve_fade_durations(clip_fade: ClipFade, output_duration_seconds: float | int) -> ResolvedFadeDurations:
    """Clamp fade durations so they always fit inside the final output duration."""

    if not clip_fade.enabled:
        return ResolvedFadeDurations(0.0, 0.0, False)

    fade_in = normalize_fade_duration(clip_fade.fade_in_seconds)
    fade_out = normalize_fade_duration(clip_fade.fade_out_seconds)
    duration = max(0.0, float(output_duration_seconds))
    total_fade = fade_in + fade_out
    if duration <= 0:
        return ResolvedFadeDurations(0.0, 0.0, True)
    if total_fade <= duration:
        return ResolvedFadeDurations(fade_in, fade_out, False)

    scale = duration / total_fade
    return ResolvedFadeDurations(fade_in * scale, fade_out * scale, True)


def build_video_fade_filters(clip_fade: ClipFade, output_duration_seconds: float | int) -> tuple[list[str], bool]:
    """Build FFmpeg video fade filters for an already-trimmed output duration."""

    resolved = resolve_fade_durations(clip_fade, output_duration_seconds)
    filters: list[str] = []
    if resolved.fade_in_seconds > 0:
        filters.append(f"fade=t=in:st=0:d={_format_filter_seconds(resolved.fade_in_seconds)}")
    if resolved.fade_out_seconds > 0:
        fade_out_start = max(0.0, float(output_duration_seconds) - resolved.fade_out_seconds)
        filters.append(
            "fade=t=out:"
            f"st={_format_filter_seconds(fade_out_start)}:"
            f"d={_format_filter_seconds(resolved.fade_out_seconds)}"
        )
    return filters, resolved.clamped


def _format_filter_seconds(value: float | int) -> str:
    seconds = float(value)
    if seconds.is_integer():
        return str(int(seconds))
    return f"{seconds:.3f}".rstrip("0").rstrip(".")
