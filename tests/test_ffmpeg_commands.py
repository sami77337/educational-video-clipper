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


def test_build_ffmpeg_command_keeps_paths_as_plain_strings(tmp_path) -> None:
    input_path = tmp_path / "input video.mp4"
    output_path = tmp_path / "فوائد طويلة" / "2_مقطع فيه مسافات.mp4"

    command = build_ffmpeg_command(input_path, output_path, start_seconds=65, duration_seconds=185)

    assert command[command.index("-i") + 1] == str(input_path)
    assert command[-1] == str(output_path)


def test_build_ffmpeg_command_applies_speed_filters_when_requested(tmp_path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"

    command = build_ffmpeg_command(input_path, output_path, 10, 30, video_speed=1.05)

    assert command[command.index("-filter:v") + 1] == "setpts=PTS/1.05"
    assert command[command.index("-filter:a") + 1] == "atempo=1.05"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


def test_build_ffmpeg_command_accepts_precise_speed_values(tmp_path) -> None:
    command = build_ffmpeg_command(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        0,
        10,
        video_speed=1.10,
    )

    assert command[command.index("-filter:v") + 1] == "setpts=PTS/1.1"
    assert command[command.index("-filter:a") + 1] == "atempo=1.1"


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
