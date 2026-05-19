"""Pure FFmpeg command builders."""

from __future__ import annotations

from pathlib import Path


def build_ffmpeg_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int,
    duration_seconds: int,
) -> list[str]:
    """Build the ffmpeg command used to cut a clip."""

    return [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-t",
        str(duration_seconds),
        "-i",
        str(input_video_path),
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
