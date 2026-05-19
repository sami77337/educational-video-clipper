from __future__ import annotations

from src.smart_paste_parser import parse_smart_paste_message


def test_smart_paste_extracts_youtube_urls_from_anywhere() -> None:
    result = parse_smart_paste_message(
        "الرابط: https://www.youtube.com/watch?v=abc123\n"
        "بث: https://youtube.com/live/live123\n"
        "قصير: https://youtu.be/short123\n"
        "شورتس: https://www.youtube.com/shorts/shorts123"
    )

    assert result.video_urls == [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtube.com/live/live123",
        "https://youtu.be/short123",
        "https://www.youtube.com/shorts/shorts123",
    ]
    assert result.clips == []


def test_smart_paste_detects_project_title_text() -> None:
    result = parse_smart_paste_message(
        "درس أسماء الله الحسنى - اسم الله الوهاب\n"
        "20:10 - 26:11 اسم الله الوهاب"
    )

    assert result.project_title == "درس أسماء الله الحسنى - اسم الله الوهاب"
    assert len(result.clips) == 1


def test_smart_paste_parses_english_numeral_timestamps() -> None:
    result = parse_smart_paste_message("01:41 - 03:12 : اسم الله الوهاب")

    assert result.warnings == []
    assert result.unparsed_lines == []
    assert result.clips[0].start == "00:01:41"
    assert result.clips[0].end == "00:03:12"
    assert result.clips[0].title == "اسم الله الوهاب"


def test_smart_paste_parses_arabic_numeral_timestamps() -> None:
    result = parse_smart_paste_message("١:٠٢ - ١:٠٣:٢٥ عنوان عربي")

    assert result.warnings == []
    assert result.clips[0].start == "00:01:02"
    assert result.clips[0].end == "01:03:25"
    assert result.clips[0].title == "عنوان عربي"


def test_smart_paste_parses_title_before_time_range() -> None:
    result = parse_smart_paste_message("اسم الله الوهاب 20:10 - 26:11")

    assert result.clips[0].title == "اسم الله الوهاب"
    assert result.clips[0].start == "00:20:10"
    assert result.clips[0].end == "00:26:11"


def test_smart_paste_parses_title_after_time_range() -> None:
    result = parse_smart_paste_message("20:10 - 26:11 اسم الله الوهاب")

    assert result.clips[0].title == "اسم الله الوهاب"
    assert result.clips[0].start == "00:20:10"
    assert result.clips[0].end == "00:26:11"


def test_smart_paste_parses_numbered_arabic_list_format() -> None:
    result = parse_smart_paste_message("١- ١:٣٩ - ٢:٤٩ (تجارة العلماء)")

    assert len(result.clips) == 1
    assert result.clips[0].number == 1
    assert result.clips[0].title == "تجارة العلماء"
    assert result.clips[0].start == "00:01:39"
    assert result.clips[0].end == "00:02:49"


def test_smart_paste_parses_beginning_end_format() -> None:
    result = parse_smart_paste_message("البداية: 0:32 ما حكم نعي الميت النهاية: 2:44")

    assert result.clips[0].title == "ما حكم نعي الميت"
    assert result.clips[0].start == "00:00:32"
    assert result.clips[0].end == "00:02:44"


def test_smart_paste_parses_from_minute_to_minute_format() -> None:
    result = parse_smart_paste_message("من الدقيقة 22:09 الى الدقيقة 25:36")

    assert result.clips[0].title == "مقطع 01"
    assert result.clips[0].start == "00:22:09"
    assert result.clips[0].end == "00:25:36"


def test_smart_paste_strips_whatsapp_metadata_before_parsing() -> None:
    result = parse_smart_paste_message("[4/30/2026 12:06 PM] Abu: 01:41 - 03:12 : اسم الله الوهاب")

    assert result.clips[0].title == "اسم الله الوهاب"
    assert result.clips[0].start == "00:01:41"
    assert result.clips[0].end == "00:03:12"
    assert result.unparsed_lines == []


def test_smart_paste_parses_parenthesized_internal_exclusion() -> None:
    result = parse_smart_paste_message("26:56 - 29:14 (27:40 - 28:20)")

    assert len(result.clips) == 1
    assert result.clips[0].start == "00:26:56"
    assert result.clips[0].end == "00:29:14"
    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"
    assert any("تم العثور على استثناء داخل المقطع" in warning.message_ar for warning in result.warnings)


def test_smart_paste_parses_arabic_numeral_internal_exclusion() -> None:
    result = parse_smart_paste_message("٢٦:٥٦ - ٢٩:١٤ (٢٧:٤٠ - ٢٨:٢٠)")

    assert result.clips[0].start == "00:26:56"
    assert result.clips[0].end == "00:29:14"
    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"


def test_smart_paste_keeps_title_parentheses_when_not_time_range() -> None:
    result = parse_smart_paste_message("01:00 - 02:00 (عنوان المقطع)")

    assert result.clips[0].title == "عنوان المقطع"
    assert result.clips[0].exclusions == []
    assert result.warnings == []


def test_smart_paste_detects_mabin_parentheses_cut_as_exclusion() -> None:
    result = parse_smart_paste_message("26:56 - 29:14 مابين القوسين يقطع (27:40 - 28:20)")

    assert len(result.clips) == 1
    assert result.clips[0].start == "00:26:56"
    assert result.clips[0].end == "00:29:14"
    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"
    assert any("تم العثور على استثناء داخل المقطع" in warning.message_ar for warning in result.warnings)


def test_smart_paste_detects_explicit_exclusion_cue() -> None:
    result = parse_smart_paste_message("26:56 - 29:14 استثناء: 27:40 - 28:20")

    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"


def test_smart_paste_detects_delete_cue_for_internal_cut() -> None:
    result = parse_smart_paste_message("26:56 - 29:14 حذف: 27:40 - 28:20")

    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"


def test_smart_paste_preserves_internal_cut_note() -> None:
    result = parse_smart_paste_message("26:56 - 29:14 يحتاج قص من الداخل (27:40 - 28:20)")

    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"
    assert "يحتاج قص من الداخل" in result.clips[0].general_notes


def test_smart_paste_warns_about_invalid_exclusion_range() -> None:
    result = parse_smart_paste_message("10:00 - 12:00 (11:30 - 11:00)")

    assert len(result.clips) == 1
    assert result.clips[0].exclusions == []
    assert any("وقت الاستثناء غير صحيح" in warning.message_ar for warning in result.warnings)


def test_smart_paste_warns_about_exclusion_outside_clip_boundaries() -> None:
    result = parse_smart_paste_message("10:00 - 12:00 (12:30 - 13:00)")

    assert len(result.clips) == 1
    assert result.clips[0].exclusions == []
    assert any("الاستثناء خارج حدود المقطع" in warning.message_ar for warning in result.warnings)


def test_smart_paste_warns_about_plus_joined_ranges_and_leaves_line_unparsed() -> None:
    result = parse_smart_paste_message("1:00 - 2:00 + 3:00 - 4:00 عنوان")

    assert result.clips == []
    assert len(result.unparsed_lines) == 1
    assert any("هذا المقطع يحتوي على أكثر من جزء ويحتاج دعم الدمج لاحقًا" in warning.message_ar for warning in result.warnings)


def test_smart_paste_preserves_first_word_last_word_markers_as_notes() -> None:
    result = parse_smart_paste_message("01:00 - 02:00 عنوان اول كلمة: كذا اخر كلمة: كذا")

    assert len(result.clips) == 1
    assert result.clips[0].start_note == "كذا"
    assert result.clips[0].end_note == "كذا"
    assert any("ملاحظة بداية المقطع" in warning.message_ar for warning in result.warnings)
    assert any("ملاحظة نهاية المقطع" in warning.message_ar for warning in result.warnings)


def test_smart_paste_returns_unparsed_lines() -> None:
    result = parse_smart_paste_message("هذا سطر غير مفهوم")

    assert result.clips == []
    assert result.project_title == "هذا سطر غير مفهوم"
    assert result.unparsed_lines == []


def test_smart_paste_keeps_second_unknown_text_line_as_unparsed() -> None:
    result = parse_smart_paste_message(
        "عنوان المشروع\n"
        "هذا سطر غير مفهوم آخر"
    )

    assert result.project_title == "عنوان المشروع"
    assert len(result.unparsed_lines) == 1
    assert result.unparsed_lines[0].raw_line == "هذا سطر غير مفهوم آخر"
