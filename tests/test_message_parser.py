from src.message_parser import (
    AR_UNPARSEABLE_LINE,
    normalize_digits,
    parse_clip_line,
    parse_clip_message,
)


def test_parse_simple_numbered_lines() -> None:
    result = parse_clip_message(
        "1- 9:16 - 9:50 ما حكم نعي الميت\n"
        "2- 9:55 - 10:04 هل يجوز لبس ملابس عليها نجمة داوود"
    )

    assert result.warnings == []
    assert len(result.clips) == 2
    assert result.clips[0].number == 1
    assert result.clips[0].start == "09:16"
    assert result.clips[0].end == "09:50"
    assert result.clips[0].title == "ما حكم نعي الميت"
    assert result.clips[1].number == 2
    assert result.clips[1].title == "هل يجوز لبس ملابس عليها نجمة داوود"


def test_parse_arabic_indic_digits() -> None:
    clip = parse_clip_line("١- ٩:١٦ - ٩:٥٠ ما حكم نعي الميت")

    assert clip is not None
    assert clip.number == 1
    assert clip.start == "09:16"
    assert clip.end == "09:50"
    assert clip.title == "ما حكم نعي الميت"


def test_normalize_digits_supports_arabic_indic_digits() -> None:
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"


def test_parse_begin_end_style() -> None:
    clip = parse_clip_line("المقطع الخامس البداية: 9:16 ما حكم نعي الميت النهاية: 9:50 ولكنه مكروه")

    assert clip is not None
    assert clip.number == 5
    assert clip.start == "09:16"
    assert clip.end == "09:50"
    assert clip.title == "ما حكم نعي الميت"


def test_parse_begin_end_style_with_numeric_segment_number() -> None:
    clip = parse_clip_line("المقطع 5 البداية: 9:16 ما حكم نعي الميت النهاية: 9:50")

    assert clip is not None
    assert clip.number == 5


def test_parse_csv_like_line() -> None:
    clip = parse_clip_line("05, ما حكم نعي الميت, 00:09:16, 00:09:50")

    assert clip is not None
    assert clip.number == 5
    assert clip.title == "ما حكم نعي الميت"
    assert clip.start == "00:09:16"
    assert clip.end == "00:09:50"


def test_unparseable_lines_return_warnings() -> None:
    result = parse_clip_message("هذا سطر غير مفهوم")

    assert result.clips == []
    assert len(result.warnings) == 1
    assert result.warnings[0].line_number == 1
    assert result.warnings[0].message_ar == f"{AR_UNPARSEABLE_LINE} 1"


def test_title_extraction_strips_separators() -> None:
    clip = parse_clip_line("3- 10:00 - 10:30 - عنوان مع شرطة")

    assert clip is not None
    assert clip.title == "عنوان مع شرطة"
