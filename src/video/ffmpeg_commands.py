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
from src.video_black_flash import ClipBlackFlash, build_black_flash_filters, normalize_clip_black_flash
from src.video_fade import ClipFade, build_video_fade_filters, normalize_clip_fade
from src.video_export_quality import (
    ExportQualitySettings,
    build_resolution_limit_filter,
    export_quality_encoding_arguments,
    normalize_export_quality_settings,
)


def build_ffmpeg_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int | float,
    duration_seconds: int | float,
    video_speed: int | float = DEFAULT_VIDEO_SPEED,
    volume_percent: int | float = DEFAULT_VOLUME_PERCENT,
    clip_fade: ClipFade | None = None,
    export_quality: ExportQualitySettings | None = None,
) -> list[str]:
    """Build the ffmpeg command used to cut a clip."""

    normalized_speed = normalize_video_speed(video_speed)
    normalized_volume = normalize_volume_percent(volume_percent)
    normalized_fade = (
        normalize_clip_fade(clip_fade.enabled, clip_fade.fade_in_seconds, clip_fade.fade_out_seconds)
        if clip_fade is not None
        else normalize_clip_fade(False)
    )
    normalized_quality = (
        normalize_export_quality_settings(
            export_quality.enabled,
            export_quality.quality_preset,
            export_quality.resolution_limit,
        )
        if export_quality is not None
        else normalize_export_quality_settings(False)
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

    video_filters = _build_video_filters(normalized_speed, normalized_fade, duration_seconds, normalized_quality)
    if video_filters:
        command.extend(["-filter:v", video_filters])

    audio_filters = _build_audio_filters(normalized_speed, normalized_volume)
    if audio_filters:
        command.extend(["-filter:a", audio_filters])

    command.extend(_encoding_arguments(output_video_path, normalized_quality))
    return command


def build_ffmpeg_video_fade_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    duration_seconds: int | float,
    clip_fade: ClipFade,
) -> list[str]:
    """Build an ffmpeg command that applies only final video fade to an existing clip."""

    return build_ffmpeg_video_effects_command(
        input_video_path,
        output_video_path,
        duration_seconds,
        clip_fade=clip_fade,
    )


def build_ffmpeg_video_effects_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    duration_seconds: int | float,
    clip_fade: ClipFade | None = None,
    clip_black_flash: ClipBlackFlash | None = None,
    black_flash_times_seconds: list[float] | tuple[float, ...] | None = None,
    export_quality: ExportQualitySettings | None = None,
) -> list[str]:
    """Build an ffmpeg command for final video-only effects on an existing clip."""

    normalized_fade = (
        normalize_clip_fade(clip_fade.enabled, clip_fade.fade_in_seconds, clip_fade.fade_out_seconds)
        if clip_fade is not None
        else normalize_clip_fade(False)
    )
    normalized_flash = (
        normalize_clip_black_flash(clip_black_flash.enabled, clip_black_flash.duration_seconds)
        if clip_black_flash is not None
        else normalize_clip_black_flash(False)
    )
    normalized_quality = (
        normalize_export_quality_settings(
            export_quality.enabled,
            export_quality.quality_preset,
            export_quality.resolution_limit,
        )
        if export_quality is not None
        else normalize_export_quality_settings(False)
    )
    video_filters: list[str] = []
    video_filters.extend(
        build_black_flash_filters(
            normalized_flash,
            black_flash_times_seconds or (),
            duration_seconds,
        )
    )
    fade_filters, _clamped = build_video_fade_filters(normalized_fade, duration_seconds)
    video_filters.extend(fade_filters)
    resolution_filter = build_resolution_limit_filter(normalized_quality)
    if resolution_filter:
        video_filters.append(resolution_filter)
    command = ["ffmpeg", "-y", "-i", str(input_video_path)]
    if video_filters:
        command.extend(["-filter:v", ",".join(video_filters)])
    command.extend(_encoding_arguments(output_video_path, normalized_quality, audio_copy=True))
    return command


def _build_video_filters(
    video_speed: float,
    clip_fade: ClipFade,
    duration_seconds: int | float,
    export_quality: ExportQualitySettings,
) -> str:
    filters: list[str] = []
    if video_speed != DEFAULT_VIDEO_SPEED:
        filters.append(build_video_speed_filter(video_speed))

    if clip_fade.enabled:
        fade_filters, _clamped = build_video_fade_filters(
            clip_fade,
            speed_adjusted_duration(duration_seconds, video_speed),
        )
        filters.extend(fade_filters)
    resolution_filter = build_resolution_limit_filter(export_quality)
    if resolution_filter:
        filters.append(resolution_filter)
    return ",".join(filters)


def _build_audio_filters(video_speed: float, volume_percent: int) -> str:
    filters: list[str] = []
    if video_speed != DEFAULT_VIDEO_SPEED:
        filters.append(build_audio_speed_filter(video_speed))
    if volume_percent != DEFAULT_VOLUME_PERCENT:
        filters.append(build_audio_volume_filter(volume_percent))
    return ",".join(filters)


def _encoding_arguments(
    output_video_path: str | Path,
    export_quality: ExportQualitySettings,
    *,
    audio_copy: bool = False,
) -> list[str]:
    return export_quality_encoding_arguments(export_quality, str(output_video_path), audio_copy=audio_copy)


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
