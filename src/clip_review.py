"""Non-destructive per-clip timing review, independent of the Qt interface."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from src.time_utils import format_seconds, parse_timestamp


@dataclass(frozen=True)
class ReviewedClip:
    number: int
    title: str
    start: str
    end: str
    original_start: str = ""
    original_end: str = ""

    @property
    def modified(self) -> bool:
        return (
            parse_timestamp(self.start) != parse_timestamp(self.original_start or self.start)
            or parse_timestamp(self.end) != parse_timestamp(self.original_end or self.end)
        )


def update_clip_bounds(
    clip: ReviewedClip,
    start: str,
    end: str,
    *,
    source_duration: float | None = None,
) -> ReviewedClip:
    """Apply a validated edit, keeping Gemini's original timestamps unchanged."""
    start_seconds = parse_timestamp(start)
    end_seconds = parse_timestamp(end)
    if end_seconds <= start_seconds:
        raise ValueError("نهاية المقطع يجب أن تكون بعد بدايته.")
    if source_duration is not None:
        if start_seconds >= source_duration or end_seconds > source_duration + 0.001:
            raise ValueError("أحد التوقيتات يتجاوز مدة الفيديو الأصلي.")
    return replace(
        clip,
        start=format_seconds(start_seconds),
        end=format_seconds(end_seconds),
        original_start=clip.original_start or clip.start,
        original_end=clip.original_end or clip.end,
    )


def boundary_warnings(
    clips: Sequence[ReviewedClip],
    index: int,
    start: str,
    end: str,
    *,
    pre_padding: float = 0.0,
    post_padding: float = 0.0,
) -> tuple[str, ...]:
    """Explain potential overlap with adjacent questions including global padding."""
    warnings: list[str] = []
    start_seconds = parse_timestamp(start)
    end_seconds = parse_timestamp(end)
    if not 0 <= index < len(clips):
        raise IndexError(index)

    if index > 0:
        previous = clips[index - 1]
        prev_end = parse_timestamp(previous.end) + post_padding
        if max(0.0, start_seconds - pre_padding) < prev_end - 0.001:
            warnings.append(
                f"البداية الجديدة قد تتداخل مع المقطع السابق رقم {previous.number}."
            )

    if index + 1 < len(clips):
        following = clips[index + 1]
        next_start = max(0.0, parse_timestamp(following.start) - pre_padding)
        if end_seconds + post_padding > next_start + 0.001:
            warnings.append(
                f"النهاية الجديدة قد تتداخل مع المقطع التالي رقم {following.number}."
            )
    return tuple(warnings)
