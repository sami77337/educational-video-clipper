from __future__ import annotations

import pytest

from src.smart_paste_parser import SmartPastePreview, parse_smart_paste_message


def _warnings(preview: SmartPastePreview) -> list[str]:
    return [warning.message_ar for warning in preview.warnings]


def _warning_text(preview: SmartPastePreview) -> str:
    return "\n".join(_warnings(preview))


def _clip_ranges(preview: SmartPastePreview) -> list[tuple[str, str, str]]:
    return [(clip.start, clip.end, clip.title) for clip in preview.clips]


def _exclusion_ranges(preview: SmartPastePreview, clip_index: int = 0) -> list[tuple[str, str]]:
    return [(exclusion.start, exclusion.end) for exclusion in preview.clips[clip_index].exclusions]


def _parts(preview: SmartPastePreview, clip_index: int = 0) -> list[tuple[str, str]]:
    return [(part.start, part.end) for part in preview.clips[clip_index].parts]


_FULL_ARABIC_INDIC_WHATSAPP_MESSAGE = """
https://www.youtube.com/watch?v=ZmvFF2XN4lA&list=PLooSZvOk5-rcxSjdgK9I5AK0_UdZwhW_d&index=9
تاسيس اسألة دروس تأسيس ١:
(المجلس الثامن و الاربعون)
١- ٠:٥٢ - ٣:٢٠ (متى يبدأ طالب العلم كتب الحديث)
٢- ٩:٠٣ - ٩:٥١ (حكم قراءة الفلسفة و المنطق)
٣- ٩:٥٢ - ١١:٤٦ (متى يجوز نقل الفتوى)
٤- ١١:٤٧ - ١٢:٤٠ (تعظيم الله سبب ام نتيجة)
٥- ١٩:٥٤ - ٢١:٠٤ (حكم اكل جوزة الطيب)
٦- ٢١:٠٥ - ٢٣:٢٣ (حكم اداء صلاة الظهر احتياطا بعد اداء الجمعة)
٧- ٢٣:٢٤ - ٢٤:٥٣ (حكم رفع الصوت جماعة في الاذكار بعد الصلاة)
٨- ٢٧:٠٥ - ٣١:٠١ (النصح للقريب)
- ارى حذف الدقيقة ٢٩-٣٠ لتكون الفائدة افضل و يقصر المقطع
٩- ٣١:٣٠ - ٣٦:٠٠ (التدرج في قراءة التفسير لطالب العلم)
١٠- ٣٦:١٠ - ٣٨:٠٠ (اتقان فن الفتوى)
""".strip()


def test_phase2_full_arabic_indic_whatsapp_message_core_fields() -> None:
    preview = parse_smart_paste_message(
        _FULL_ARABIC_INDIC_WHATSAPP_MESSAGE
    )

    assert preview.video_urls == [
        "https://www.youtube.com/watch?v=ZmvFF2XN4lA&list=PLooSZvOk5-rcxSjdgK9I5AK0_UdZwhW_d&index=9"
    ]
    assert preview.project_title == "تاسيس اسألة دروس تأسيس 1 - المجلس الثامن و الاربعون"
    assert len(preview.clips) == 10
    clip_8 = preview.clips[7]
    assert (clip_8.title, clip_8.start, clip_8.end) == ("النصح للقريب", "00:27:05", "00:31:01")
    assert "نهاية المقطع قبل بدايته" not in _warning_text(preview)


def test_phase3_full_arabic_indic_whatsapp_following_line_exclusion_note() -> None:
    preview = parse_smart_paste_message(_FULL_ARABIC_INDIC_WHATSAPP_MESSAGE)

    assert _exclusion_ranges(preview, 7) == [("00:29:00", "00:30:00")]


def test_phase1_title_on_two_lines_metadata_before_clips() -> None:
    preview = parse_smart_paste_message(
        """
https://www.youtube.com/watch?v=example
تأسيس أسئلة دروس تأسيس 1
المجلس الثامن والأربعون

1) 00:00:52 - 00:03:20 | متى يبدأ طالب العلم كتب الحديث
""".strip()
    )

    assert preview.video_urls == ["https://www.youtube.com/watch?v=example"]
    assert preview.project_title == "تأسيس أسئلة دروس تأسيس 1 - المجلس الثامن والأربعون"
    assert _clip_ranges(preview) == [
        ("00:00:52", "00:03:20", "متى يبدأ طالب العلم كتب الحديث")
    ]


def test_phase1_title_before_time_format_on_previous_line() -> None:
    preview = parse_smart_paste_message(
        """
مقطع الفرق بين المداهنة والمداراة والمجاملة وجزء من النفاق
من 1:02:25 الى 1:18:17
""".strip()
    )

    assert _clip_ranges(preview) == [
        ("01:02:25", "01:18:17", "الفرق بين المداهنة والمداراة والمجاملة وجزء من النفاق")
    ]


def test_phase1_beginning_end_block_with_nearby_minute_lines() -> None:
    preview = parse_smart_paste_message(
        """
مقطع الدنيا مقياس لإيمان العبد
البداية : النبي صلى الله عليه وسلم
الدقيقة 4:15
النهاية: يخاف عليه
الدقيقة 6:35
""".strip()
    )

    assert _clip_ranges(preview) == [
        ("00:04:15", "00:06:35", "الدنيا مقياس لإيمان العبد")
    ]


def test_phase1_time_inside_parentheses_with_title_label_prefix() -> None:
    preview = parse_smart_paste_message("فائدة : لماذا نتعلم السنة (3:09-19:01)")

    assert _clip_ranges(preview) == [("00:03:09", "00:19:01", "لماذا نتعلم السنة")]


def test_phase1_same_line_exclusion_after_title_parentheses() -> None:
    preview = parse_smart_paste_message(
        "26:56 - 29:14 (بقدر ما في قلبك من صلاح فإنه يتسع للخير) (27:40 - 28:20 يقطع)"
    )

    assert _clip_ranges(preview) == [
        ("00:26:56", "00:29:14", "بقدر ما في قلبك من صلاح فإنه يتسع للخير")
    ]
    assert _exclusion_ranges(preview) == [("00:27:40", "00:28:20")]


def test_phase2_following_line_exclusion_sample_keeps_basic_clip() -> None:
    preview = parse_smart_paste_message(
        """
٨- ٢٧:٠٥ - ٣١:٠١ (النصح للقريب)
- ارى حذف الدقيقة ٢٩-٣٠ لتكون الفائدة افضل و يقصر المقطع
""".strip()
    )

    assert _clip_ranges(preview) == [("00:27:05", "00:31:01", "النصح للقريب")]


def test_phase3_following_line_exclusion_with_arabic_indic_digits() -> None:
    preview = parse_smart_paste_message(
        """
٨- ٢٧:٠٥ - ٣١:٠١ (النصح للقريب)
- ارى حذف الدقيقة ٢٩-٣٠ لتكون الفائدة افضل و يقصر المقطع
""".strip()
    )

    assert _exclusion_ranges(preview) == [("00:29:00", "00:30:00")]


def test_phase1_multiple_exclusions_after_one_clip() -> None:
    preview = parse_smart_paste_message(
        """
1) 00:10:00 - 00:20:00 | عنوان
- حذف 12-13
- حذف 15:30 - 16:00
""".strip()
    )

    assert _clip_ranges(preview) == [("00:10:00", "00:20:00", "عنوان")]
    assert _exclusion_ranges(preview) == [
        ("00:12:00", "00:13:00"),
        ("00:15:30", "00:16:00"),
    ]


def test_phase1_compound_range_one_clip_with_internal_gap() -> None:
    preview = parse_smart_paste_message(
        """
10:12 - 11:35 + 12:33 - 17:51 (السلامة من الذنوب + محاسبة النفس)
يحتاج قص من الداخل
اعملوه مقطع واحد مش مقطعين
""".strip()
    )

    assert _clip_ranges(preview) == [
        ("00:10:12", "00:17:51", "السلامة من الذنوب + محاسبة النفس")
    ]
    assert _exclusion_ranges(preview) == [("00:11:35", "00:12:33")]
    assert any("تم اكتشاف مقطع مركب مع حذف داخلي" in warning for warning in _warnings(preview))


def test_phase1_compound_range_currently_is_not_split_into_two_independent_clips() -> None:
    preview = parse_smart_paste_message(
        """
10:12 - 11:35 + 12:33 - 17:51 (السلامة من الذنوب + محاسبة النفس)
يحتاج قص من الداخل
اعملوه مقطع واحد مش مقطعين
""".strip()
    )

    assert len(preview.clips) == 1
    assert not preview.clips[0].multi_part
    assert _exclusion_ranges(preview) == [("00:11:35", "00:12:33")]
    assert any("تم اكتشاف مقطع مركب مع حذف داخلي" in warning for warning in _warnings(preview))


def test_phase1_reversed_timing_is_blocking_error() -> None:
    preview = parse_smart_paste_message("١٠- ٢٨:٣٤ - ٢٤:٠٠ (ضابط التبديع)")

    assert preview.clips == []
    assert any("نهاية المقطع قبل بدايته" in warning for warning in _warnings(preview))


def test_phase1_short_end_time_interpreted_as_full_minute_with_warning() -> None:
    preview = parse_smart_paste_message("١٣- ٢٨:٠٨ - ٢٩ (ضابط احسان الظن بالله)")

    assert _clip_ranges(preview) == [("00:28:08", "00:29:00", "ضابط احسان الظن بالله")]
    assert any("وقت النهاية مختصر وتم تفسيره كدقيقة كاملة" in warning for warning in _warnings(preview))


def test_phase1_exclusion_word_without_time_becomes_review_note_not_exclusion() -> None:
    preview = parse_smart_paste_message(
        """
1) 00:10:00 - 00:20:00 | عنوان
- يحتاج الفيديو الاول الى بعض الاقتصاصات في اثنائه
""".strip()
    )

    assert _clip_ranges(preview) == [("00:10:00", "00:20:00", "عنوان")]
    assert _exclusion_ranges(preview) == []
    assert any("ملاحظة تحتاج مراجعة" in warning for warning in _warnings(preview))


def test_phase3_out_of_bounds_following_exclusion_warns_without_attaching() -> None:
    preview = parse_smart_paste_message(
        """
8) 27:05 - 31:01 | النصح للقريب
- حذف 32-33
""".strip()
    )

    assert _clip_ranges(preview) == [("00:27:05", "00:31:01", "النصح للقريب")]
    assert _exclusion_ranges(preview) == []
    assert any("وقت الاستثناء خارج حدود المقطع السابق" in warning for warning in _warnings(preview))


def test_phase3_reversed_following_exclusion_warns_without_auto_swap() -> None:
    preview = parse_smart_paste_message(
        """
1) 00:10:00 - 00:20:00 | عنوان
- حذف 13-12
""".strip()
    )

    assert _clip_ranges(preview) == [("00:10:00", "00:20:00", "عنوان")]
    assert _exclusion_ranges(preview) == []
    assert any("نهاية الاستثناء قبل بدايته" in warning for warning in _warnings(preview))


def test_phase3_overlapping_following_exclusions_warn() -> None:
    preview = parse_smart_paste_message(
        """
1) 00:10:00 - 00:20:00 | عنوان
- حذف 12-14
- حذف 13-15
""".strip()
    )

    assert _clip_ranges(preview) == [("00:10:00", "00:20:00", "عنوان")]
    assert _exclusion_ranges(preview) == [
        ("00:12:00", "00:14:00"),
        ("00:13:00", "00:15:00"),
    ]
    assert any("يوجد تداخل أو تكرار في الاستثناءات" in warning for warning in _warnings(preview))


def test_phase1_time_range_without_exclusion_intent_does_not_become_exclusion() -> None:
    preview = parse_smart_paste_message(
        """
1) 00:10:00 - 00:20:00 | عنوان
- هذا شرح مهم من الدقيقة 12 إلى 13
""".strip()
    )

    assert len(preview.clips) == 1
    assert _exclusion_ranges(preview) == []
    assert not any("استثناء" in warning for warning in _warnings(preview))


def test_phase1_multiple_urls_selects_first_and_uses_final_warning_copy() -> None:
    preview = parse_smart_paste_message(
        """
https://youtu.be/abc
https://www.youtube.com/watch?v=def
1) 00:01:00 - 00:02:00 | عنوان
""".strip()
    )

    assert preview.video_urls[0] == "https://youtu.be/abc"
    assert _clip_ranges(preview) == [("00:01:00", "00:02:00", "عنوان")]
    assert any("تم العثور على أكثر من رابط، سيتم استخدام الرابط الأول في هذه النسخة" in warning for warning in _warnings(preview))


def test_phase1_multiple_urls_currently_warns_and_preserves_first_url() -> None:
    preview = parse_smart_paste_message(
        """
https://youtu.be/abc
https://www.youtube.com/watch?v=def
1) 00:01:00 - 00:02:00 | عنوان
""".strip()
    )

    assert preview.video_urls[:2] == ["https://youtu.be/abc", "https://www.youtube.com/watch?v=def"]
    assert any("تم العثور على أكثر من رابط" in warning for warning in _warnings(preview))
