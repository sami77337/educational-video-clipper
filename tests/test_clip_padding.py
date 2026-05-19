import pytest

from src.clip_padding import ClipPadding, calculate_effective_clip_range, normalize_padding_seconds


def test_no_padding_preserves_original_range() -> None:
    effective_range = calculate_effective_clip_range(10, 20, ClipPadding())

    assert effective_range.start_seconds == 10
    assert effective_range.end_seconds == 20
    assert effective_range.duration_seconds == 10


def test_pre_padding_clamps_to_zero() -> None:
    effective_range = calculate_effective_clip_range(1, 8, ClipPadding(pre_seconds=2))

    assert effective_range.start_seconds == 0
    assert effective_range.end_seconds == 8
    assert effective_range.duration_seconds == 8


def test_post_padding_extends_end() -> None:
    effective_range = calculate_effective_clip_range(5, 15, ClipPadding(post_seconds=1.5))

    assert effective_range.start_seconds == 5
    assert effective_range.end_seconds == 16.5
    assert effective_range.duration_seconds == 11.5


def test_post_padding_clamps_to_known_video_duration() -> None:
    effective_range = calculate_effective_clip_range(
        10,
        20,
        ClipPadding(post_seconds=10),
        video_duration_seconds=25,
    )

    assert effective_range.start_seconds == 10
    assert effective_range.end_seconds == 25
    assert effective_range.duration_seconds == 15


def test_negative_padding_is_normalized_safely() -> None:
    padding = ClipPadding(pre_seconds=-2, post_seconds=-1)

    assert padding.pre_seconds == 0
    assert padding.post_seconds == 0
    assert normalize_padding_seconds("-4") == 0


def test_invalid_negative_padding_does_not_crash() -> None:
    effective_range = calculate_effective_clip_range(5, 15, ClipPadding(pre_seconds="-1"))

    assert effective_range.start_seconds == 5
    assert effective_range.end_seconds == 15


def test_invalid_clip_range_still_fails() -> None:
    with pytest.raises(ValueError):
        calculate_effective_clip_range(10, 10, ClipPadding(post_seconds=1))
