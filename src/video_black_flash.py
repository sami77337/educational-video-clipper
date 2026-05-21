"""Helpers for optional black flash markers at exclusion join points."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


DEFAULT_BLACK_FLASH_SECONDS = 0.20
ALLOWED_BLACK_FLASH_DURATIONS = (0.10, 0.20, 0.30, 0.50)

AR_BLACK_FLASH_APPLIED = "تم تطبيق وميض أسود عند الاستثناءات"
AR_BLACK_FLASH_FAILED = "تعذر إضافة الوميض الأسود لهذا المقطع"


class VideoBlackFlashError(ValueError):
    """Raised when black flash settings are invalid."""


@dataclass(frozen=True)
class ClipBlackFlash:
    """Optional black flash marker settings for exclusion joins."""

    enabled: bool = False
    duration_seconds: float = DEFAULT_BLACK_FLASH_SECONDS


def normalize_black_flash_duration(value: float | int | str | None) -> float:
    """Return one of the allowed black flash durations."""

    try:
        duration = float(value)
    except (TypeError, ValueError) as error:
        raise VideoBlackFlashError("Invalid black flash duration") from error

    if not isfinite(duration) or duration <= 0:
        raise VideoBlackFlashError("Invalid black flash duration")

    for allowed in ALLOWED_BLACK_FLASH_DURATIONS:
        if abs(duration - allowed) < 1e-9:
            return allowed

    raise VideoBlackFlashError("Invalid black flash duration")


def normalize_clip_black_flash(
    enabled: bool = False,
    duration_seconds: float | int | str | None = DEFAULT_BLACK_FLASH_SECONDS,
) -> ClipBlackFlash:
    """Normalize flash settings and preserve safe defaults when disabled."""

    if not enabled:
        return ClipBlackFlash()
    return ClipBlackFlash(
        enabled=True,
        duration_seconds=normalize_black_flash_duration(duration_seconds),
    )


def build_black_flash_filters(
    clip_black_flash: ClipBlackFlash,
    join_times_seconds: list[float] | tuple[float, ...],
    output_duration_seconds: float | int,
) -> list[str]:
    """Build drawbox filters that make the video black at exclusion joins."""

    normalized_flash = normalize_clip_black_flash(
        clip_black_flash.enabled,
        clip_black_flash.duration_seconds,
    )
    if not normalized_flash.enabled:
        return []

    output_duration = float(output_duration_seconds)
    if output_duration <= 0:
        return []

    filters: list[str] = []
    for join_time in join_times_seconds:
        start = float(join_time)
        if start <= 0 or start >= output_duration:
            continue

        end = min(output_duration, start + normalized_flash.duration_seconds)
        if end <= start:
            continue

        filters.append(
            "drawbox="
            "x=0:y=0:w=iw:h=ih:"
            "color=black:t=fill:"
            f"enable='between(t,{_format_filter_seconds(start)},{_format_filter_seconds(end)})'"
        )

    return filters


def _format_filter_seconds(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")
