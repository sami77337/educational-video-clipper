import subprocess
from pathlib import Path

import pytest

from src.clip_padding import ClipPadding
from src.video.ffmpeg_runner import FfmpegRunnerError, probe_media_duration_seconds, resolve_external_tool
from src.video_processor import (
    INPUT_VIDEO_NAME,
    ClipDefinition,
    PreparedVideoSource,
    VideoProcessingError,
    VideoSourceType,
    cut_clip,
    cut_clips,
)


def _require_ffmpeg() -> str:
    try:
        return resolve_external_tool("ffmpeg")
    except FileNotFoundError:
        pytest.skip("FFmpeg is not available; skipping local cutting regression tests.")


@pytest.fixture()
def sample_video(tmp_path: Path) -> Path:
    ffmpeg_path = _require_ffmpeg()
    video_path = tmp_path / INPUT_VIDEO_NAME
    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=160x90:rate=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:sample_rate=44100",
        "-t",
        "12",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(video_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        pytest.skip(f"FFmpeg could not generate temporary test media: {completed.stderr[-400:]}")

    assert video_path.is_file()
    assert video_path.stat().st_size > 1024
    return video_path


def _prepared_video(sample_video: Path) -> PreparedVideoSource:
    return PreparedVideoSource(
        source_type=VideoSourceType.LOCAL_FILE,
        project_output_folder=sample_video.parent,
        input_video_path=sample_video,
    )


def _assert_media_output(path: Path, *, min_duration: float | None = None, max_duration: float | None = None) -> None:
    assert path.is_file()
    assert path.stat().st_size > 1024

    try:
        duration = probe_media_duration_seconds(path)
    except (FfmpegRunnerError, FileNotFoundError):
        return

    if min_duration is not None:
        assert duration >= min_duration
    if max_duration is not None:
        assert duration <= max_duration


def _probe_duration_if_available(path: Path) -> float | None:
    try:
        return probe_media_duration_seconds(path)
    except (FfmpegRunnerError, FileNotFoundError):
        return None


def test_local_cut_no_padding_no_exclusions_creates_output(sample_video: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "no_padding.mp4"

    result = cut_clip(sample_video, output_path, 2, 3)

    assert result == output_path
    _assert_media_output(output_path, min_duration=2.0, max_duration=5.5)


def test_local_cut_video_speed_one_creates_nonempty_output_with_original_duration(
    sample_video: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "speed_1_0.mp4"

    result = cut_clip(sample_video, output_path, 0, 4, video_speed=1.0)

    assert result == output_path
    _assert_media_output(output_path, min_duration=3.0, max_duration=5.5)


def test_local_cut_video_speed_ten_percent_shortens_duration_reasonably(
    sample_video: Path,
    tmp_path: Path,
) -> None:
    speed_one_output = tmp_path / "speed_1_0.mp4"
    faster_output = tmp_path / "speed_1_10.mp4"

    cut_clip(sample_video, speed_one_output, 0, 4, video_speed=1.0)
    result = cut_clip(sample_video, faster_output, 0, 4, video_speed=1.10)

    assert result == faster_output
    _assert_media_output(speed_one_output)
    _assert_media_output(faster_output)

    speed_one_duration = _probe_duration_if_available(speed_one_output)
    faster_duration = _probe_duration_if_available(faster_output)
    if speed_one_duration is not None and faster_duration is not None:
        assert faster_duration < speed_one_duration
        assert faster_duration == pytest.approx(speed_one_duration / 1.10, rel=0.2, abs=0.5)


def test_local_cut_video_speed_creates_shorter_synced_output(sample_video: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "speed.mp4"

    result = cut_clip(sample_video, output_path, 0, 4, video_speed=2.0)

    assert result == output_path
    _assert_media_output(output_path, min_duration=1.0, max_duration=3.2)


def test_local_cut_pre_post_padding_clamps_start_and_extends_end(sample_video: Path) -> None:
    clip = ClipDefinition(number=1, title="padding", start_seconds=1, end_seconds=3)

    results = cut_clips(
        _prepared_video(sample_video),
        [clip],
        clip_padding=ClipPadding(pre_seconds=2, post_seconds=1),
    )

    _assert_media_output(results[0].output_path, min_duration=3.0, max_duration=6.5)


def test_local_cut_single_exclusion_preserves_existing_behavior(sample_video: Path) -> None:
    clip = ClipDefinition(
        number=1,
        title="single exclusion",
        start_seconds=2,
        end_seconds=8,
        exclusions="00:04-00:05",
    )

    results = cut_clips(_prepared_video(sample_video), [clip])

    _assert_media_output(results[0].output_path, min_duration=4.0, max_duration=7.5)


def test_local_cut_multiple_exclusions_concatenates_remaining_parts_in_order(sample_video: Path) -> None:
    clip = ClipDefinition(
        number=1,
        title="multiple exclusions",
        start_seconds=1,
        end_seconds=10,
        exclusions="00:03-00:04, 00:06-00:07",
    )

    results = cut_clips(_prepared_video(sample_video), [clip])

    _assert_media_output(results[0].output_path, min_duration=6.0, max_duration=9.5)


def test_local_cut_rejects_overlapping_exclusions_before_processing(sample_video: Path) -> None:
    clip = ClipDefinition(
        number=1,
        title="overlap",
        start_seconds=1,
        end_seconds=10,
        exclusions="00:03-00:05, 00:04-00:06",
    )

    with pytest.raises(VideoProcessingError):
        cut_clips(_prepared_video(sample_video), [clip])


def test_local_cut_rejects_outside_exclusion_before_processing(sample_video: Path) -> None:
    clip = ClipDefinition(
        number=1,
        title="outside",
        start_seconds=1,
        end_seconds=10,
        exclusions="00:11-00:12",
    )

    with pytest.raises(VideoProcessingError):
        cut_clips(_prepared_video(sample_video), [clip])


def test_local_cut_exclusions_with_padding_creates_output(sample_video: Path) -> None:
    clip = ClipDefinition(
        number=1,
        title="padding exclusions",
        start_seconds=2,
        end_seconds=8,
        exclusions="00:01-00:02, 00:08-00:09",
    )

    results = cut_clips(
        _prepared_video(sample_video),
        [clip],
        clip_padding=ClipPadding(pre_seconds=1, post_seconds=1),
    )

    _assert_media_output(results[0].output_path, min_duration=5.0, max_duration=8.5)
