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
    assert result.clips[0].start == "00:09:16"
    assert result.clips[0].end == "00:09:50"
    assert result.clips[0].title == "ما حكم نعي الميت"
    assert result.clips[1].number == 2
    assert result.clips[1].title == "هل يجوز لبس ملابس عليها نجمة داوود"


def test_parse_arabic_indic_digits() -> None:
    clip = parse_clip_line("١- ٩:١٦ - ٩:٥٠ ما حكم نعي الميت")

    assert clip is not None
    assert clip.number == 1
    assert clip.start == "00:09:16"
    assert clip.end == "00:09:50"
    assert clip.title == "ما حكم نعي الميت"


def test_normalize_digits_supports_arabic_indic_digits() -> None:
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"


def test_parse_begin_end_style() -> None:
    clip = parse_clip_line("المقطع الخامس البداية: 9:16 ما حكم نعي الميت النهاية: 9:50 ولكنه مكروه")

    assert clip is not None
    assert clip.number == 5
    assert clip.start == "00:09:16"
    assert clip.end == "00:09:50"
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


def test_parse_bracketed_time_range_with_title_after() -> None:
    result = parse_clip_message("[20:10] - [26:11] اسم الله الوهاب")

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].number == 1
    assert result.clips[0].title == "اسم الله الوهاب"
    assert result.clips[0].start == "00:20:10"
    assert result.clips[0].end == "00:26:11"


def test_parse_title_before_bracketed_time_range() -> None:
    result = parse_clip_message(
        "أكثر دعاء كان النبي يكرره ربنا لا تزغ قلوبنا بعد اذ هديتنا [01:44] - [08:00]"
    )

    assert result.warnings == []
    assert result.clips[0].title == "أكثر دعاء كان النبي يكرره ربنا لا تزغ قلوبنا بعد اذ هديتنا"
    assert result.clips[0].start == "00:01:44"
    assert result.clips[0].end == "00:08:00"


def test_parse_arabic_indic_numbered_list_titles_and_times() -> None:
    result = parse_clip_message(
        "١- ٠٠:١٥ - ١:٣٥ (تجارة العلماء)\n"
        "٢- ١:٣٦ - ٢:٢٠ (ترك الجماعة بسبب الدراسة)"
    )

    assert result.warnings == []
    assert [clip.number for clip in result.clips] == [1, 2]
    assert result.clips[0].title == "تجارة العلماء"
    assert result.clips[0].start == "00:00:15"
    assert result.clips[0].end == "00:01:35"
    assert result.clips[1].title == "ترك الجماعة بسبب الدراسة"


def test_parse_title_line_followed_by_time_range_line() -> None:
    result = parse_clip_message(
        "١. او كصيب من السماء فيه ظلمات ورعد وبرق\n"
        "4:22 - 8:17"
    )

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].number == 1
    assert result.clips[0].title == "او كصيب من السماء فيه ظلمات ورعد وبرق"
    assert result.clips[0].start == "00:04:22"
    assert result.clips[0].end == "00:08:17"


def test_parse_segment_begin_end_block() -> None:
    result = parse_clip_message(
        "المقطع الخامس\n"
        "البداية: 9:16 ما حكم نعي الميت\n"
        "النهاية: 9:50 ولكنه مكروه"
    )

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].number == 5
    assert result.clips[0].title == "ما حكم نعي الميت"
    assert result.clips[0].start == "00:09:16"
    assert result.clips[0].end == "00:09:50"


def test_parse_explicit_multiline_title_with_begin_end_block() -> None:
    result = parse_clip_message(
        "مقطع النفس تميل للمعاصي والقلب يحن للتوبة\n\n"
        "البداية: النفس تميل المعاصي 8:06\n"
        "النهاية : كلمة والله اعلم 11:06"
    )

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].number == 1
    assert result.clips[0].title == "مقطع النفس تميل للمعاصي والقلب يحن للتوبة"
    assert result.clips[0].start == "00:08:06"
    assert result.clips[0].end == "00:11:06"


def test_parse_multiline_title_continuation() -> None:
    result = parse_clip_message(
        "[20:10] - [26:11] اسم الله الوهاب\n"
        "والا يقيد المسلم دعاءه"
    )

    assert result.warnings == []
    assert result.clips[0].title == "اسم الله الوهاب والا يقيد المسلم دعاءه"


def test_note_lines_starting_with_asterisk_are_ignored() -> None:
    result = parse_clip_message(
        "* هذه ملاحظة لا تتحول إلى مقطع\n"
        "[20:10] - [26:11] اسم الله الوهاب"
    )

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].title == "اسم الله الوهاب"


def test_extra_internal_range_in_parentheses_is_not_a_second_clip() -> None:
    result = parse_clip_message("26:56 - 29:14 (27:40 - 28:20)")

    assert result.warnings == []
    assert len(result.clips) == 1
    assert result.clips[0].start == "00:26:56"
    assert result.clips[0].end == "00:29:14"
    assert result.clips[0].title == "مقطع 01"


def test_auto_numbering_when_no_number_exists() -> None:
    result = parse_clip_message(
        "20:10 - 26:11 اسم الله الوهاب\n"
        "1:01:04- 1:06:55 ، أسباب الضلال"
    )

    assert result.warnings == []
    assert [clip.number for clip in result.clips] == [1, 2]
    assert result.clips[0].start == "00:20:10"
    assert result.clips[1].start == "01:01:04"
    assert result.clips[1].end == "01:06:55"


def test_malformed_spaces_around_colon_are_normalized() -> None:
    result = parse_clip_message("٣٨ :09 - ٤٠ : ١٠ عنوان")

    assert result.warnings == []
    assert result.clips[0].start == "00:38:09"
    assert result.clips[0].end == "00:40:10"
    assert result.clips[0].title == "عنوان"


def test_unparseable_line_warning_after_real_world_parsing() -> None:
    result = parse_clip_message(
        "هذا سطر غير مفهوم\n"
        "20:10 - 26:11 اسم الله الوهاب"
    )

    assert len(result.clips) == 1
    assert len(result.warnings) == 1
    assert result.warnings[0].line_number == 1
    assert result.warnings[0].message_ar == f"{AR_UNPARSEABLE_LINE} 1"
