from __future__ import annotations

from src.smart_paste_parser import parse_smart_paste_message


REAL_ARABIC_STRUCTURE_SAMPLE = """مقاطع من لمعة الإعتقاد ، الدرس الثاني
https://youtu.be/05spuILAwrQ

6:20 - 8:50
, إثبات صحة النبوة

9:26 - 27:33
, تاريخ ظهور البدع

27:35 - 38:59
, النجاة من البدع

38:05 - 46:13
(الكتب في العقيدة)

46:16 - 47:44
, (ميزات كتب اهل السنة)

58:03- 1:00:02
، ميزات كتاب اللمعة

1:03:29 - 1:10:03
، رجل يقول أنا أعتقد أني مسلم على صواب و النصراني يعتقد أنه على صواب ، كيف ترد عليه؟(ما عنه الذكر الحكمي)

1:14:09 - 1:16:09
(مبتدعا أو ضالاً) ، عن التعصب

1:17:24 - 1:18:27
، الهداية هدايتان إطلبهما من الله الآن

1:18:51 - 1:20:51
, فضل البسملة

1:21:35 - 1:23:52
, تسبيح الضفادع

1:24:04 - 1:25:13
(المعبود في كل زمان)

1:25:14 - 1:26:04
"""


EXPECTED_REAL_ARABIC_STRUCTURE_CLIPS = [
    ("00:06:20", "00:08:50", "إثبات صحة النبوة"),
    ("00:09:26", "00:27:33", "تاريخ ظهور البدع"),
    ("00:27:35", "00:38:59", "النجاة من البدع"),
    ("00:38:05", "00:46:13", "الكتب في العقيدة"),
    ("00:46:16", "00:47:44", "ميزات كتب اهل السنة"),
    ("00:58:03", "01:00:02", "ميزات كتاب اللمعة"),
    (
        "01:03:29",
        "01:10:03",
        "رجل يقول أنا أعتقد أني مسلم على صواب و النصراني يعتقد أنه على صواب ، كيف ترد عليه؟(ما عنه الذكر الحكمي)",
    ),
    ("01:14:09", "01:16:09", "مبتدعا أو ضالاً ، عن التعصب"),
    ("01:17:24", "01:18:27", "الهداية هدايتان إطلبهما من الله الآن"),
    ("01:18:51", "01:20:51", "فضل البسملة"),
    ("01:21:35", "01:23:52", "تسبيح الضفادع"),
    ("01:24:04", "01:25:13", "المعبود في كل زمان"),
    ("01:25:14", "01:26:04", "مقطع 13"),
]


def test_smart_paste_parses_real_arabic_title_structure_sample() -> None:
    result = parse_smart_paste_message(REAL_ARABIC_STRUCTURE_SAMPLE)

    assert result.project_title == "مقاطع من لمعة الإعتقاد ، الدرس الثاني"
    assert result.video_urls == ["https://youtu.be/05spuILAwrQ"]
    assert result.unparsed_lines == []
    assert [
        (clip.start, clip.end, clip.title)
        for clip in result.clips
    ] == EXPECTED_REAL_ARABIC_STRUCTURE_CLIPS


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


def test_smart_paste_treats_following_range_as_exclusion_after_clear_cue() -> None:
    result = parse_smart_paste_message(
        "26:56 - 29:14 عنوان المقطع\n"
        "قص داخل المقطع\n"
        "27:40 - 28:20"
    )

    assert len(result.clips) == 1
    assert result.clips[0].title == "عنوان المقطع"
    assert result.clips[0].exclusions_text == "00:27:40-00:28:20"
    assert any("تم اكتشاف وقت قد يكون استثناء داخل المقطع" in warning.message_ar for warning in result.warnings)


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


def test_smart_paste_parses_english_plus_joined_multi_part_clip() -> None:
    result = parse_smart_paste_message("10:12 - 11:35 + 12:33 - 17:51 (title)")

    assert result.unparsed_lines == []
    assert len(result.clips) == 1
    clip = result.clips[0]
    assert clip.multi_part
    assert clip.title == "title"
    assert [(part.start, part.end) for part in clip.parts] == [
        ("00:10:12", "00:11:35"),
        ("00:12:33", "00:17:51"),
    ]
    assert any("تم العثور على مقطع مركب من أكثر من جزء" in warning.message_ar for warning in result.warnings)
    assert any("هذا المقطع يحتوي على أكثر من جزء. سيتم دعمه في القص لاحقًا." in warning.message_ar for warning in result.warnings)


def test_smart_paste_parses_arabic_numeral_plus_joined_multi_part_clip() -> None:
    result = parse_smart_paste_message("١٠:١٢ - ١١:٣٥ + ١٢:٣٣ - ١٧:٥١ (العنوان)")

    assert len(result.clips) == 1
    clip = result.clips[0]
    assert clip.multi_part
    assert clip.title == "العنوان"
    assert [(part.start, part.end) for part in clip.parts] == [
        ("00:10:12", "00:11:35"),
        ("00:12:33", "00:17:51"),
    ]


def test_smart_paste_parses_compact_plus_joined_separator() -> None:
    result = parse_smart_paste_message("10:12-11:35 + 12:33-17:51")

    assert result.clips[0].multi_part
    assert result.clips[0].parts_text == "الجزء 1: 00:10:12 - 00:11:35 | الجزء 2: 00:12:33 - 00:17:51"


def test_smart_paste_parses_arabic_plus_joined_separator() -> None:
    result = parse_smart_paste_message("10:12 إلى 11:35 + 12:33 إلى 17:51")

    assert result.clips[0].multi_part
    assert [(part.start, part.end) for part in result.clips[0].parts] == [
        ("00:10:12", "00:11:35"),
        ("00:12:33", "00:17:51"),
    ]


def test_smart_paste_warns_about_invalid_multi_part_second_part() -> None:
    result = parse_smart_paste_message("10:12 - 11:35 + 12:33 - 12:00")

    assert result.clips[0].multi_part
    assert any("أحد أجزاء المقطع المركب غير صحيح" in warning.message_ar for warning in result.warnings)


def test_smart_paste_warns_about_overlapping_multi_part_ranges() -> None:
    result = parse_smart_paste_message("10:12 - 12:00 + 11:50 - 13:00")

    assert result.clips[0].multi_part
    assert any("يوجد تداخل بين أجزاء المقطع المركب" in warning.message_ar for warning in result.warnings)


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
