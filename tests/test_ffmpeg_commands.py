import pytest

from src.video.ffmpeg_commands import (
    build_ffmpeg_command,
    build_ffmpeg_concat_command,
    build_ffmpeg_video_effects_command,
)
from src.video_black_flash import ClipBlackFlash
from src.video_export_quality import ExportQualitySettings
from src.video_fade import ClipFade


def test_build_ffmpeg_command_preserves_current_single_cut_arguments(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "ريلز" / "1_عنوان عربي.mp4"

    command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)

    assert command == [
        "ffmpeg",
        "-y",
        "-ss",
        "10",
        "-t",
        "30",
        "-i",
        str(input_path),
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
        str(output_path),
    ]


def test_build_ffmpeg_command_speed_one_preserves_old_behavior(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    default_command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)
    speed_one_command = build_ffmpeg_command(
        input_path,
        output_path,
        start_seconds=10,
        duration_seconds=30,
        video_speed=1.0,
    )

    assert speed_one_command == default_command
    assert "-filter:v" not in speed_one_command
    assert "-filter:a" not in speed_one_command


def test_build_ffmpeg_command_volume_one_hundred_preserves_old_behavior(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    default_command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)
    volume_default_command = build_ffmpeg_command(
        input_path,
        output_path,
        start_seconds=10,
        duration_seconds=30,
        volume_percent=100,
    )

    assert volume_default_command == default_command
    assert "-filter:v" not in volume_default_command
    assert "-filter:a" not in volume_default_command


def test_build_ffmpeg_command_disabled_fade_preserves_old_behavior(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    default_command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)
    disabled_fade_command = build_ffmpeg_command(
        input_path,
        output_path,
        start_seconds=10,
        duration_seconds=30,
        clip_fade=ClipFade(enabled=False, fade_in_seconds=2.0, fade_out_seconds=2.0),
    )

    assert disabled_fade_command == default_command
    assert "-filter:v" not in disabled_fade_command


def test_disabled_export_quality_preserves_old_behavior(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    default_command = build_ffmpeg_command(input_path, output_path, start_seconds=10, duration_seconds=30)
    disabled_quality_command = build_ffmpeg_command(
        input_path,
        output_path,
        start_seconds=10,
        duration_seconds=30,
        export_quality=ExportQualitySettings(enabled=False, quality_preset="high", resolution_limit="720p"),
    )

    assert disabled_quality_command == default_command
    assert "-filter:v" not in disabled_quality_command
    assert disabled_quality_command[disabled_quality_command.index("-preset") + 1] == "veryfast"
    assert disabled_quality_command[disabled_quality_command.index("-crf") + 1] == "20"


@pytest.mark.parametrize(
    ("quality_preset", "ffmpeg_preset", "crf"),
    [
        ("high", "slow", "18"),
        ("balanced", "medium", "22"),
        ("small", "veryfast", "26"),
    ],
)
def test_enabled_export_quality_applies_selected_encoding_preset(
    tmp_path,
    quality_preset: str,
    ffmpeg_preset: str,
    crf: str,
) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        export_quality=ExportQualitySettings(enabled=True, quality_preset=quality_preset),
    )

    assert command[command.index("-preset") + 1] == ffmpeg_preset
    assert command[command.index("-crf") + 1] == crf


def test_original_resolution_limit_applies_no_scale_filter(tmp_path) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        export_quality=ExportQualitySettings(enabled=True, quality_preset="balanced", resolution_limit="original"),
    )

    assert "-filter:v" not in command


@pytest.mark.parametrize("resolution_limit", ["1080p", "720p"])
def test_resolution_limit_adds_downscale_only_filter(tmp_path, resolution_limit: str) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        export_quality=ExportQualitySettings(enabled=True, quality_preset="balanced", resolution_limit=resolution_limit),
    )

    limit = resolution_limit.removesuffix("p")
    video_filter = command[command.index("-filter:v") + 1]
    assert "scale=" in video_filter
    assert f"gt(ih,{limit})" in video_filter
    assert f",{limit},ih" in video_filter


def test_build_ffmpeg_command_volume_one_hundred_preserves_speed_behavior(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    speed_command = build_ffmpeg_command(input_path, output_path, 10, 30, video_speed=1.10)
    speed_with_default_volume_command = build_ffmpeg_command(
        input_path,
        output_path,
        10,
        30,
        video_speed=1.10,
        volume_percent=100,
    )

    assert speed_with_default_volume_command == speed_command


def test_build_ffmpeg_command_keeps_paths_as_plain_strings(tmp_path) -> None:
    input_path = tmp_path / "input video.mp4"
    output_path = tmp_path / "فوائد طويلة" / "2_مقطع فيه مسافات.mp4"

    command = build_ffmpeg_command(input_path, output_path, start_seconds=65, duration_seconds=185)

    assert command[command.index("-i") + 1] == str(input_path)
    assert command[-1] == str(output_path)


@pytest.mark.parametrize(
    ("speed", "formatted_speed"),
    [
        (1.05, "1.05"),
        (1.10, "1.1"),
        (1.25, "1.25"),
    ],
)
def test_build_ffmpeg_command_applies_synced_speed_filters(tmp_path, speed: float, formatted_speed: str) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    command = build_ffmpeg_command(input_path, output_path, 10, 30, video_speed=speed)

    assert command[command.index("-filter:v") + 1] == f"setpts=PTS/{formatted_speed}"
    assert command[command.index("-filter:a") + 1] == f"atempo={formatted_speed}"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


@pytest.mark.parametrize(
    ("volume_percent", "audio_filter"),
    [
        (75, "volume=0.75"),
        (150, "volume=1.5"),
        (200, "volume=2"),
    ],
)
def test_build_ffmpeg_command_applies_audio_volume_filter(
    tmp_path,
    volume_percent: int,
    audio_filter: str,
) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    command = build_ffmpeg_command(input_path, output_path, 10, 30, volume_percent=volume_percent)

    assert "-filter:v" not in command
    assert command[command.index("-filter:a") + 1] == audio_filter
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


def test_build_ffmpeg_command_combines_speed_and_volume_audio_filters(tmp_path) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        video_speed=1.10,
        volume_percent=150,
    )

    assert command[command.index("-filter:v") + 1] == "setpts=PTS/1.1"
    assert command[command.index("-filter:a") + 1] == "atempo=1.1,volume=1.5"


def test_build_ffmpeg_command_applies_black_fade_filters(tmp_path) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=1.0),
    )

    assert command[command.index("-filter:v") + 1] == "fade=t=in:st=0:d=0.5,fade=t=out:st=29:d=1"
    assert "-filter:a" not in command


def test_build_ffmpeg_command_combines_speed_and_black_fade_filters(tmp_path) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        10,
        30,
        video_speed=1.10,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
    )

    video_filter = command[command.index("-filter:v") + 1]
    assert video_filter.startswith("setpts=PTS/1.1,fade=t=in:st=0:d=0.5,fade=t=out:st=")
    assert command[command.index("-filter:a") + 1] == "atempo=1.1"


def test_build_ffmpeg_video_effects_command_applies_black_flash_at_join_times(tmp_path) -> None:
    command = build_ffmpeg_video_effects_command(
        tmp_path / "merged.mp4",
        tmp_path / "output.mp4",
        duration_seconds=20,
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.2),
        black_flash_times_seconds=[8.0, 14.5],
    )

    video_filter = command[command.index("-filter:v") + 1]
    assert "drawbox" in video_filter
    assert "between(t,8,8.2)" in video_filter
    assert "between(t,14.5,14.7)" in video_filter
    assert command[command.index("-c:a") + 1] == "copy"


def test_build_ffmpeg_video_effects_command_combines_black_flash_and_fade(tmp_path) -> None:
    command = build_ffmpeg_video_effects_command(
        tmp_path / "merged.mp4",
        tmp_path / "output.mp4",
        duration_seconds=20,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
        clip_black_flash=ClipBlackFlash(enabled=True, duration_seconds=0.1),
        black_flash_times_seconds=[8.0],
    )

    video_filter = command[command.index("-filter:v") + 1]
    assert video_filter.startswith("drawbox=")
    assert "between(t,8,8.1)" in video_filter
    assert video_filter.endswith("fade=t=in:st=0:d=0.5,fade=t=out:st=19.5:d=0.5")


def test_video_effects_command_uses_custom_quality_and_resolution_when_enabled(tmp_path) -> None:
    command = build_ffmpeg_video_effects_command(
        tmp_path / "merged.mp4",
        tmp_path / "output.mp4",
        duration_seconds=20,
        clip_fade=ClipFade(enabled=True, fade_in_seconds=0.5, fade_out_seconds=0.5),
        export_quality=ExportQualitySettings(enabled=True, quality_preset="high", resolution_limit="720p"),
    )

    video_filter = command[command.index("-filter:v") + 1]
    assert video_filter.endswith("h='if(gt(ih,720),720,ih)'")
    assert command[command.index("-preset") + 1] == "slow"
    assert command[command.index("-crf") + 1] == "18"
    assert command[command.index("-c:a") + 1] == "copy"


def test_build_ffmpeg_concat_command_preserves_current_concat_arguments(tmp_path) -> None:
    file_list = tmp_path / "segments list.txt"
    output_path = tmp_path / "فوائد" / "final clip.mp4"

    assert build_ffmpeg_concat_command(file_list, output_path) == [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(file_list),
        "-c",
        "copy",
        str(output_path),
    ]
