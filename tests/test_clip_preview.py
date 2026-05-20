import subprocess
from pathlib import Path

import pytest

from src.clip_padding import ClipPadding
from src.clip_preview import (
    ClipPreviewError,
    ClipPreviewKind,
    calculate_preview_range,
    create_preview_clip,
)


def test_start_preview_range_clamps_to_zero() -> None:
    preview_range = calculate_preview_range(ClipPreviewKind.START, 5, 60)

    assert preview_range.start_seconds == 0
    assert preview_range.end_seconds == 25
    assert preview_range.duration_seconds == 25


def test_end_preview_range_clamps_to_known_duration() -> None:
    preview_range = calculate_preview_range(
        ClipPreviewKind.END,
        20,
        95,
        video_duration_seconds=100,
    )

    assert preview_range.start_seconds == 75
    assert preview_range.end_seconds == 100
    assert preview_range.duration_seconds == 25


def test_full_clip_preview_uses_selected_range_without_padding() -> None:
    preview_range = calculate_preview_range(ClipPreviewKind.FULL, 10, 40)

    assert preview_range.start_seconds == 10
    assert preview_range.end_seconds == 40
    assert preview_range.duration_seconds == 30


def test_full_clip_preview_uses_effective_padded_range() -> None:
    preview_range = calculate_preview_range(
        ClipPreviewKind.FULL,
        5,
        40,
        video_duration_seconds=42,
        clip_padding=ClipPadding(pre_seconds=10, post_seconds=10),
    )

    assert preview_range.start_seconds == 0
    assert preview_range.end_seconds == 42


def test_invalid_preview_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_preview_range(ClipPreviewKind.FULL, 20, 20)


def test_create_preview_clip_builds_temp_ffmpeg_command(tmp_path) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"source")
    preview_range = calculate_preview_range(ClipPreviewKind.START, 10, 40)
    commands: list[list[str]] = []

    def fake_runner(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"preview" * 200)
        return subprocess.CompletedProcess(command, 0, "", "")

    output_path = create_preview_clip(
        input_video,
        preview_range,
        preview_folder=tmp_path / "previews",
        clip_number=1,
        preview_kind=ClipPreviewKind.START,
        runner=fake_runner,
    )

    assert output_path.parent == tmp_path / "previews"
    assert output_path.name.startswith("preview_1_start_")
    assert commands[0][0] == "ffmpeg"
    assert commands[0][commands[0].index("-ss") + 1] == "0"
    assert commands[0][commands[0].index("-t") + 1] == "30"
    assert "-filter:a" not in commands[0]
    assert commands[0][-1] == str(output_path)


def test_create_preview_clip_rejects_missing_source(tmp_path) -> None:
    preview_range = calculate_preview_range(ClipPreviewKind.FULL, 10, 20)

    with pytest.raises(ClipPreviewError):
        create_preview_clip(
            tmp_path / "missing.mp4",
            preview_range,
            preview_folder=tmp_path / "previews",
        )
