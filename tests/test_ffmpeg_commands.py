import pytest

from src.video.ffmpeg_commands import build_ffmpeg_command, build_ffmpeg_concat_command


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
