import pytest

from src.video_volume import (
    AR_INVALID_VOLUME_PERCENT,
    DEFAULT_VOLUME_PERCENT,
    VideoVolumeError,
    build_audio_volume_filter,
    format_volume_percent,
    normalize_volume_percent,
    volume_is_default,
)


def test_default_volume_is_one_hundred_percent() -> None:
    assert DEFAULT_VOLUME_PERCENT == 100
    assert normalize_volume_percent(100) == 100
    assert volume_is_default(100) is True


@pytest.mark.parametrize("value", [75, "100", 125, 150, 200])
def test_common_volume_values_are_valid(value) -> None:
    assert normalize_volume_percent(value) == int(value)


@pytest.mark.parametrize("value", [0, -1, "", "abc", None, float("nan"), float("inf")])
def test_invalid_volume_values_are_rejected(value) -> None:
    with pytest.raises(VideoVolumeError, match=AR_INVALID_VOLUME_PERCENT):
        normalize_volume_percent(value)


@pytest.mark.parametrize(
    ("percent", "filter_value"),
    [
        (75, "volume=0.75"),
        (150, "volume=1.5"),
        (200, "volume=2"),
    ],
)
def test_audio_volume_filter_uses_safe_audio_only_volume_factor(percent: int, filter_value: str) -> None:
    assert build_audio_volume_filter(percent) == filter_value


def test_format_volume_percent_for_report() -> None:
    assert format_volume_percent(150) == "150%"
