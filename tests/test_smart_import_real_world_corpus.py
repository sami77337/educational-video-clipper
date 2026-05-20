from __future__ import annotations

import pytest

from src.smart_paste_parser import format_smart_paste_debug_report, parse_smart_paste_message
from tests.fixtures.smart_import_real_messages import SMART_IMPORT_REAL_MESSAGES


@pytest.mark.parametrize("sample", SMART_IMPORT_REAL_MESSAGES, ids=lambda sample: sample["name"])
def test_real_world_smart_import_corpus(sample: dict) -> None:
    result = parse_smart_paste_message(sample["input_text"])

    expected_url = sample["expected_url"]
    if expected_url:
        assert result.video_urls
        assert result.video_urls[0] == expected_url
    else:
        assert result.video_urls == []

    assert result.project_title == sample["expected_project_title"]
    assert [(clip.start, clip.end, clip.title) for clip in result.clips] == sample["expected_clips"]

    for clip_index, expected_ranges in sample.get("expected_exclusions", {}).items():
        clip = result.clips[clip_index]
        assert [(exclusion.start, exclusion.end) for exclusion in clip.exclusions] == expected_ranges

    warning_text = "\n".join(warning.message_ar for warning in result.warnings)
    for expected_warning in sample.get("expected_warnings", []):
        assert expected_warning in warning_text


def test_multiple_urls_warn_and_first_url_remains_first() -> None:
    result = parse_smart_paste_message(
        "https://youtu.be/first123\n"
        "1:00 - 2:00 عنوان\n"
        "https://www.youtube.com/watch?v=second456"
    )

    assert result.video_urls[0] == "https://youtu.be/first123"
    assert len(result.video_urls) == 2
    assert any("تم العثور على أكثر من رابط" in warning.message_ar for warning in result.warnings)


def test_persian_digits_and_mixed_digits_are_normalized() -> None:
    result = parse_smart_paste_message("۱:٠٣:29 - ۱:۰۴:۳۱ عنوان مختلط")

    assert result.clips[0].start == "01:03:29"
    assert result.clips[0].end == "01:04:31"
    assert result.clips[0].title == "عنوان مختلط"


def test_copyable_debug_report_contains_parser_evidence() -> None:
    result = parse_smart_paste_message("عنوان المشروع\nhttps://youtu.be/abc123\n1:00 - 2:00 عنوان")

    report = format_smart_paste_debug_report(result, "النص الأصلي")

    assert "تقرير فحص الاستيراد الذكي" in report
    assert "عنوان المشروع" in report
    assert "https://youtu.be/abc123" in report
    assert "00:01:00 - 00:02:00 | عنوان" in report
    assert "النص الأصلي" in report
