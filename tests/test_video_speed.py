import pytest

from src.video_speed import (
    AR_INVALID_VIDEO_SPEED,
    DEFAULT_VIDEO_SPEED,
    VideoSpeedError,
    build_audio_speed_filter,
    build_video_speed_filter,
    normalize_video_speed,
    speed_adjusted_duration,
)


def test_default_video_speed_is_one() -> None:
    assert DEFAULT_VIDEO_SPEED == 1.0
    assert normalize_video_speed(1.0) == 1.0


@pytest.mark.parametrize("value", [0.75, 0.90, 1.05, "1.10", 1.25, 1.5, 2.0])
def test_common_video_speed_values_are_valid(value) -> None:
    assert normalize_video_speed(value) == float(value)


@pytest.mark.parametrize("value", [0, -1, 4.01, "", "abc", None, float("nan"), float("inf")])
def test_invalid_video_speed_values_are_rejected(value) -> None:
    with pytest.raises(VideoSpeedError, match=AR_INVALID_VIDEO_SPEED):
        normalize_video_speed(value)


@pytest.mark.parametrize(
    ("speed", "formatted_speed"),
    [
        (1.05, "1.05"),
        (1.10, "1.1"),
        (1.25, "1.25"),
        (0.75, "0.75"),
    ],
)
def test_common_speed_filters_keep_video_and_audio_in_sync(speed: float, formatted_speed: str) -> None:
    assert build_video_speed_filter(speed) == f"setpts=PTS/{formatted_speed}"
    assert build_audio_speed_filter(speed) == f"atempo={formatted_speed}"


def test_audio_speed_filter_chains_large_values_safely() -> None:
    assert build_audio_speed_filter(4.0) == "atempo=2,atempo=2"


def test_speed_adjusted_duration_shortens_output_when_speeding_up() -> None:
    assert speed_adjusted_duration(60, 1.5) == 40
