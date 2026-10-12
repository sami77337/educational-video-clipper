import json

import pytest

from src.gemini_import import GeminiImportError, parse_gemini_response


def test_gemini_arabic_markdown_table_with_clickable_timestamps():
    message = """إليك 3 أسئلة مع توقيتها:
| م | عنوان السؤال | وقت البداية | وقت النهاية | رابط الفيديو |
|---|---|---|---|---|
| 1 | هل تجب صلاة الجماعة؟ | [00:19](https://www.youtube.com/watch?v=abcDEF12345&t=19s) | 00:37.500 | [رابط](https://www.youtube.com/watch?v=abcDEF12345) |
| 2 | حكم الكتابة بالقلم | 00:38 | 00:45 | [رابط](https://www.youtube.com/watch?v=abcDEF12345&t=38s) |
| 3 | هل تصح بوضوء؟ | 00:47 | 01:37 | [رابط](https://www.youtube.com/watch?v=abcDEF12345&t=47s) |
"""
    preview = parse_gemini_response(message)
    assert len(preview.clips) == 3
    assert preview.clips[0].start == "00:00:19"
    assert preview.clips[0].end == "00:00:37.500"
    assert preview.clips[0].title == "هل تجب صلاة الجماعة؟"
    assert preview.source_url == "https://www.youtube.com/watch?v=abcDEF12345"
    assert any("قصير" in warning for warning in preview.warnings)


def test_gemini_json_code_fence():
    fence = chr(96) * 3
    message = (
        "نتائج التحليل\n" + fence + "json\n"
        + json.dumps({"video_url": "https://youtu.be/abcDEF12345",
                      "clips": [{"id": "1", "title": "ما حكم الصلاة؟",
                                 "start": "00:01:02.250", "end": "00:01:44.750"}]},
                     ensure_ascii=False)
        + "\n" + fence
    )
    parsed = parse_gemini_response(message)
    assert parsed.clips[0].start == "00:01:02.250"
    assert parsed.clips[0].end == "00:01:44.750"
    assert parsed.source_url == "https://www.youtube.com/watch?v=abcDEF12345"


def test_gemini_csv_import_preserves_arabic_title_and_fractional_time():
    text = "number,title,start,end\n1,هل يجوز الصيام؟,00:19,00:37.5\n"
    parsed = parse_gemini_response(text)
    assert parsed.clips[0].end == "00:00:37.500"


@pytest.mark.parametrize("text", [
    '{"clips":[{"id":1,"title":"سؤال","start":null,"end":"00:37"}]}',
    "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n|---|---|---|---|\n| 1 | سؤال | غير مؤكد | 00:37 |",
    "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n|---|---|---|---|\n| 1 | سؤال | 00:50 | 00:30 |",
    "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n|---|---|---|---|\n| 1 | سؤال | 00:10 | 00:30 |\n| 1 | سؤال آخر | 00:31 | 00:40 |",
])
def test_gemini_uncertain_invalid_or_duplicate_ranges_block_import(text):
    with pytest.raises(GeminiImportError):
        parse_gemini_response(text)


def test_gemini_multiple_distinct_youtube_videos_block_import():
    text = """
| م | عنوان السؤال | وقت البداية | وقت النهاية | رابط الفيديو |
|---|---|---|---|---|
| 1 | سؤال | 00:01 | 00:30 | https://youtu.be/abcDEF12345 |
| 2 | سؤال آخر | 00:40 | 01:30 | https://youtu.be/otherID7890 |
"""
    with pytest.raises(GeminiImportError, match="أكثر من فيديو"):
        parse_gemini_response(text)


def test_gemini_warnings_expose_large_gaps_and_overlaps():
    message = """
| number | title | start | end |
|---|---|---|---|
| 1 | First | 00:01 | 00:20 |
| 2 | Second | 00:18 | 00:32 |
| 3 | Third | 01:10 | 02:10 |
"""
    parsed = parse_gemini_response(message)
    assert any("متداخلان" in line for line in parsed.warnings)
    assert any("فجوة" in line for line in parsed.warnings)


def test_gemini_no_partial_success_on_unparseable_row():
    message = """
| م | عنوان السؤال | وقت البداية | وقت النهاية |
|---|---|---|---|
| 1 | سؤال صالح | 00:01 | 00:20 |
| 2 | سؤال غير صالح | 00:30 | null |
"""
    with pytest.raises(GeminiImportError):
        parse_gemini_response(message)


def test_gemini_tab_separated_clipboard_table():
    copied = (
        "م\tعنوان السؤال\tوقت البداية\tوقت النهاية\n"
        "1\tهل يجوز جمع الصلاة؟\t00:19\t00:37.500\n"
        "2\tسؤال ثانٍ\t00:38\t01:03\n"
    )
    parsed = parse_gemini_response(copied)
    assert len(parsed.clips) == 2
    assert parsed.clips[0].end == "00:00:37.500"
