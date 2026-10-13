import pytest

from src.clip_review import ReviewedClip, boundary_warnings, update_clip_bounds


def test_review_half_second_preserves_original_timing() -> None:
    original = ReviewedClip(
        number=1, title="ما حكم الصلاة؟",
        start="00:01:20", end="00:01:48",
        original_start="00:01:20", original_end="00:01:48",
    )
    corrected = update_clip_bounds(original, "00:01:19.500", "00:01:48.500")
    assert corrected.start == "00:01:19.500"
    assert corrected.end == "00:01:48.500"
    assert corrected.original_start == "00:01:20"
    assert corrected.original_end == "00:01:48"
    assert corrected.modified
    assert not original.modified

    second_review = update_clip_bounds(corrected, "00:01:19.250", "00:01:49")
    assert second_review.original_start == "00:01:20"
    assert second_review.original_end == "00:01:48"


@pytest.mark.parametrize("start,end", [
    ("00:01:00", "00:01:00"),
    ("00:01:01", "00:01:00"),
    ("unknown", "00:01:00"),
])
def test_review_rejects_invalid_bounds(start: str, end: str) -> None:
    original = ReviewedClip(number=1, title="فتوى", start="00:01", end="00:02")
    with pytest.raises(ValueError):
        update_clip_bounds(original, start, end)


def test_review_never_exceeds_video_duration() -> None:
    clip = ReviewedClip(number=1, title="فتوى", start="00:17", end="00:20")
    with pytest.raises(ValueError, match="يتجاوز"):
        update_clip_bounds(clip, "00:17", "00:21", source_duration=20.5)


def test_review_warns_about_adjacent_overlap_before_cutting() -> None:
    clips = [
        ReviewedClip(1, "الأول", "00:05", "00:15"),
        ReviewedClip(2, "الثاني", "00:16", "00:30"),
    ]
    assert boundary_warnings(clips, 0, "00:05", "00:16.500")
    assert boundary_warnings(clips, 1, "00:14.500", "00:30")
    assert boundary_warnings(clips, 0, "00:05", "00:15") == ()


def test_review_warns_about_global_padding_overlaps() -> None:
    clips = [
        ReviewedClip(1, "الأول", "00:05", "00:15"),
        ReviewedClip(2, "الثاني", "00:16", "00:30"),
    ]
    assert boundary_warnings(
        clips, 0, "00:05", "00:15",
        pre_padding=0.5, post_padding=0.75,
    )
    assert boundary_warnings(
        clips, 0, "00:05", "00:15",
        pre_padding=0, post_padding=0,
    ) == ()


def test_manual_import_becomes_original_on_first_review() -> None:
    clip = ReviewedClip(1, "فتوى", "00:05", "00:15")
    edited = update_clip_bounds(clip, "00:05", "00:15.500")
    assert edited.original_start == "00:05"
    assert edited.original_end == "00:15"
    assert edited.modified
