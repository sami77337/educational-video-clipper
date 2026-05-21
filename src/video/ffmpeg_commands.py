"""Pure FFmpeg command builders."""

from __future__ import annotations

from pathlib import Path

from src.video_speed import (
    DEFAULT_VIDEO_SPEED,
    build_audio_speed_filter,
    build_video_speed_filter,
    normalize_video_speed,
    speed_adjusted_duration,
)
from src.video_volume import (
    DEFAULT_VOLUME_PERCENT,
    build_audio_volume_filter,
    normalize_volume_percent,
)
from src.video_fade import ClipFade, build_video_fade_filters, normalize_clip_fade


def build_ffmpeg_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int | float,
    duration_seconds: int | float,
    video_speed: int | float = DEFAULT_VIDEO_SPEED,
    volume_percent: int | float = DEFAULT_VOLUME_PERCENT,
    clip_fade: ClipFade | None = None,
) -> list[str]:
    """Build the ffmpeg command used to cut a clip."""

    normalized_speed = normalize_video_speed(video_speed)
    normalized_volume = normalize_volume_percent(volume_percent)
    normalized_fade = (
        normalize_clip_fade(clip_fade.enabled, clip_fade.fade_in_seconds, clip_fade.fade_out_seconds)
        if clip_fade is not None
        else normalize_clip_fade(False)
    )
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        _format_ffmpeg_seconds(start_seconds),
        "-t",
        _format_ffmpeg_seconds(duration_seconds),
        "-i",
        str(input_video_path),
    ]

    video_filters = _build_video_filters(normalized_speed, normalized_fade, duration_seconds)
    if video_filters:
        command.extend(["-filter:v", video_filters])

    audio_filters = _build_audio_filters(normalized_speed, normalized_volume)
    if audio_filters:
        command.extend(["-filter:a", audio_filters])

    command.extend(_encoding_arguments(output_video_path))
    return command


def build_ffmpeg_video_fade_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    duration_seconds: int | float,
    clip_fade: ClipFade,
) -> list[str]:
    """Build an ffmpeg command that applies only final video fade to an existing clip."""

    normalized_fade = normalize_clip_fade(
        clip_fade.enabled,
        clip_fade.fade_in_seconds,
        clip_fade.fade_out_seconds,
    )
    video_filters, _clamped = build_video_fade_filters(normalized_fade, duration_seconds)
    command = ["ffmpeg", "-y", "-i", str(input_video_path)]
    if video_filters:
        command.extend(["-filter:v", ",".join(video_filters)])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            str(output_video_path),
        ]
    )
    return command


def _build_video_filters(video_speed: float, clip_fade: ClipFade, duration_seconds: int | float) -> str:
    filters: list[str] = []
    if video_speed != DEFAULT_VIDEO_SPEED:
        filters.append(build_video_speed_filter(video_speed))

    if clip_fade.enabled:
        fade_filters, _clamped = build_video_fade_filters(
            clip_fade,
            speed_adjusted_duration(duration_seconds, video_speed),
        )
        filters.extend(fade_filters)
    return ",".join(filters)


def _build_audio_filters(video_speed: float, volume_percent: int) -> str:
    filters: list[str] = []
    if video_speed != DEFAULT_VIDEO_SPEED:
        filters.append(build_audio_speed_filter(video_speed))
    if volume_percent != DEFAULT_VOLUME_PERCENT:
        filters.append(build_audio_volume_filter(volume_percent))
    return ",".join(filters)


def _encoding_arguments(output_video_path: str | Path) -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_video_path),
    ]


def build_ffmpeg_concat_command(
    file_list_path: str | Path,
    output_video_path: str | Path,
) -> list[str]:
    """Build the ffmpeg concat command used to merge kept segments."""

    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(file_list_path),
        "-c",
        "copy",
        str(output_video_path),
    ]


def _format_ffmpeg_seconds(value: int | float) -> str:
    seconds = float(value)
    if seconds.is_integer():
        return str(int(seconds))
    return f"{seconds:.3f}".rstrip("0").rstrip(".")
