"""Clip pre/post padding helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClipPadding:
    """Optional seconds added around requested clip boundaries."""

    pre_seconds: float = 0.0
    post_seconds: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "pre_seconds", normalize_padding_seconds(self.pre_seconds))
        object.__setattr__(self, "post_seconds", normalize_padding_seconds(self.post_seconds))

    @property
    def has_padding(self) -> bool:
        return self.pre_seconds > 0 or self.post_seconds > 0


@dataclass(frozen=True)
class EffectiveClipRange:
    """Actual cut range after applying padding and duration clamping."""

    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        duration = self.end_seconds - self.start_seconds
        if duration <= 0:
            raise ValueError("Effective clip end time must be after start time.")
        return duration


def normalize_padding_seconds(value: int | float | str | None) -> float:
    """Return a non-negative padding value in seconds."""

    try:
        seconds = float(value if value is not None else 0)
    except (TypeError, ValueError):
        return 0.0

    if seconds < 0:
        return 0.0
    return seconds


def calculate_effective_clip_range(
    start_seconds: int | float,
    end_seconds: int | float,
    padding: ClipPadding | None = None,
    video_duration_seconds: int | float | None = None,
) -> EffectiveClipRange:
    """Return the actual cut range after safe pre/post padding."""

    active_padding = padding or ClipPadding()
    original_start = float(start_seconds)
    original_end = float(end_seconds)
    if original_end <= original_start:
        raise ValueError("Clip end time must be after start time.")

    effective_start = max(0.0, original_start - active_padding.pre_seconds)
    effective_end = original_end + active_padding.post_seconds

    if video_duration_seconds is not None:
        duration = float(video_duration_seconds)
        if duration >= 0:
            effective_end = min(effective_end, duration)

    effective_range = EffectiveClipRange(effective_start, effective_end)
    effective_range.duration_seconds
    return effective_range
