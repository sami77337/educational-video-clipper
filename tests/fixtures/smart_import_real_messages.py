"""Real-world Arabic smart import message corpus.

Each sample captures a message shape that should keep working as the parser
evolves. The corpus intentionally stores expected parser evidence rather than
UI behavior.
"""

from __future__ import annotations


SMART_IMPORT_REAL_MESSAGES = [
    {
        "name": "old_pr35_lumaat_13_clips",
        "input_text": """مقاطع من لمعة الإعتقاد ، الدرس الثاني
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
""",
        "expected_url": "https://youtu.be/05spuILAwrQ",
        "expected_project_title": "مقاطع من لمعة الإعتقاد ، الدرس الثاني",
        "expected_clips": [
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
        ],
        "expected_exclusions": {},
        "expected_warnings": ["يوجد تداخل بين المقاطع"],
        "notes": "Title lines after ranges, comma prefixes, parenthesized titles, final missing title.",
    },
    {
        "name": "youtube_live_arabic_until_separator",
        "input_text": """https://www.youtube.com/live/QnXIVFglX88?si=v1bDhYQI4dYc3E3c

٢:٢٧:٠٠ و حتى ٢:٣٠:٤٣
""",
        "expected_url": "https://www.youtube.com/live/QnXIVFglX88?si=v1bDhYQI4dYc3E3c",
        "expected_project_title": "",
        "expected_clips": [("02:27:00", "02:30:43", "مقطع 01")],
        "expected_exclusions": {},
        "expected_warnings": [],
        "notes": "Arabic-Indic digits and و حتى separator.",
    },
    {
        "name": "labeled_start_end_minutes_nearby",
        "input_text": """مقطع الدنيا مقياس لإيمان العبد

البداية : النبي صلى الله عليه وسلم
الدقيقة 4:15

النهاية: يخاف عليه
الدقيقة 6:35
https://youtu.be/mGmk-5cCFVM?si=9PDS-rkmDDG1oPcC
""",
        "expected_url": "https://youtu.be/mGmk-5cCFVM?si=9PDS-rkmDDG1oPcC",
        "expected_project_title": "مقطع الدنيا مقياس لإيمان العبد",
        "expected_clips": [("00:04:15", "00:06:35", "مقطع الدنيا مقياس لإيمان العبد")],
        "expected_exclusions": {},
        "expected_warnings": ["ملاحظة بداية المقطع", "ملاحظة نهاية المقطع"],
        "notes": "Textual بداية/نهاية labels with time on following الدقيقة lines.",
    },
    {
        "name": "bracketed_ranges_with_titles",
        "input_text": """[01:41] - [03:12] : فضل خواتيم سورة البقرة
[03:13] - [05:31] : (كسبت) و (اكتسبت).
""",
        "expected_url": "",
        "expected_project_title": "",
        "expected_clips": [
            ("00:01:41", "00:03:12", "فضل خواتيم سورة البقرة"),
            ("00:03:13", "00:05:31", "(كسبت) و (اكتسبت)."),
        ],
        "expected_exclusions": {},
        "expected_warnings": [],
        "notes": "Square brackets and parenthesized words inside meaningful title.",
    },
    {
        "name": "previous_title_lines_before_ranges",
        "input_text": """مقاطع وفوائد المجلس الأول من كتاب أمثال القرآن:
https://www.youtube.com/live/ZIt8rZ8ufL8?si=Y8BxHolOT2jj3AxE
١. فائدة ضرب الأمثال في القرآن الكريم:
3:00 - 6:05
٢. أقسام أمثال القرآن الكريم:
6:11- 7:49
""",
        "expected_url": "https://www.youtube.com/live/ZIt8rZ8ufL8?si=Y8BxHolOT2jj3AxE",
        "expected_project_title": "مقاطع وفوائد المجلس الأول من كتاب أمثال القرآن",
        "expected_clips": [
            ("00:03:00", "00:06:05", "فائدة ضرب الأمثال في القرآن الكريم"),
            ("00:06:11", "00:07:49", "أقسام أمثال القرآن الكريم"),
        ],
        "expected_exclusions": {},
        "expected_warnings": [],
        "notes": "Previous title line supplies following range title.",
    },
    {
        "name": "arabic_numbered_parenthesized_titles",
        "input_text": """١- ١:٣٩ - ٢:٤٩ ( لن تفلح في طلب العلم ان كان هذا حالك)
٢- ٥:٤٧ - ٦:٢٠ (الاستقرار والاستمرار)
""",
        "expected_url": "",
        "expected_project_title": "",
        "expected_clips": [
            ("00:01:39", "00:02:49", "لن تفلح في طلب العلم ان كان هذا حالك"),
            ("00:05:47", "00:06:20", "الاستقرار والاستمرار"),
        ],
        "expected_exclusions": {},
        "expected_warnings": [],
        "notes": "Arabic numbering and parenthesized title after range.",
    },
    {
        "name": "parenthesized_internal_exclusion_with_previous_title",
        "input_text": """مقاطع وفوائد المجلس الثاني من كتاب أمثال القرآن لابن القيم رحمه الله:
https://www.youtube.com/live/zoFRX8ng7bw?si=gA1pcmkCs_Rs16js
١٤. بقدر ما في قلبك من صلاح فإنه يتسع للخير (مابين القوسين يقطع)
26:56 - 29:14 (27:40 - 28:20)
""",
        "expected_url": "https://www.youtube.com/live/zoFRX8ng7bw?si=gA1pcmkCs_Rs16js",
        "expected_project_title": "مقاطع وفوائد المجلس الثاني من كتاب أمثال القرآن لابن القيم رحمه الله",
        "expected_clips": [("00:26:56", "00:29:14", "بقدر ما في قلبك من صلاح فإنه يتسع للخير")],
        "expected_exclusions": {0: [("00:27:40", "00:28:20")]},
        "expected_warnings": ["تم العثور على استثناء داخل المقطع"],
        "notes": "Previous title has exclusion cue, following range has parenthesized internal cut.",
    },
    {
        "name": "url_first_multiline_labeled_clip",
        "input_text": """https://youtu.be/NF86t6_0s38?si=iY4Ayq5mnVOU3z4B
مقطع النفس تميل للمعاصي والقلب يحن للتوبة

البداية: النفس تميل المعاصي 8:06

النهاية : كلمة (والله اعلم ) 11:06
""",
        "expected_url": "https://youtu.be/NF86t6_0s38?si=iY4Ayq5mnVOU3z4B",
        "expected_project_title": "مقطع النفس تميل للمعاصي والقلب يحن للتوبة",
        "expected_clips": [("00:08:06", "00:11:06", "مقطع النفس تميل للمعاصي والقلب يحن للتوبة")],
        "expected_exclusions": {},
        "expected_warnings": ["ملاحظة بداية المقطع", "ملاحظة نهاية المقطع"],
        "notes": "Project title after URL and multi-line بداية/نهاية.",
    },
    {
        "name": "title_before_parenthesized_range_with_note",
        "input_text": """فائدة : لماذا نتعلم السنة (3:09-19:01)

ريلز : أهمية حفظ الصحيحين (38:28-42:00) >>>>>قد تحذف قصة الشيخ بشار إذا اعتبر طويل الريلز
""",
        "expected_url": "",
        "expected_project_title": "",
        "expected_clips": [
            ("00:03:09", "00:19:01", "لماذا نتعلم السنة"),
            ("00:38:28", "00:42:00", "أهمية حفظ الصحيحين"),
        ],
        "expected_exclusions": {},
        "expected_warnings": ["توجد ملاحظة تحتاج مراجعة يدوية"],
        "notes": "Prefix cleanup and trailing note stored as warning/note.",
    },
    {
        "name": "from_minute_to_minute_with_textual_boundaries",
        "input_text": """https://youtu.be/ytrVTUv2dq8?si=ZmFvp8KOBL-R2HHP

من الدقيقة 22:09 الى الدقيقة 25:36

البداية: كما قلنا فضل الحج

النهاية: هذا حديث صحيح
""",
        "expected_url": "https://youtu.be/ytrVTUv2dq8?si=ZmFvp8KOBL-R2HHP",
        "expected_project_title": "",
        "expected_clips": [("00:22:09", "00:25:36", "مقطع 01")],
        "expected_exclusions": {},
        "expected_warnings": ["توجد حدود نصية تحتاج مراجعة يدوية"],
        "notes": "Range first, later textual start/end labels become notes/warnings.",
    },
    {
        "name": "end_before_start_typo",
        "input_text": """تاسيس اسألة دروس تأسيس ١:
١٣- ٢٦:٣٤ - ٢٦:١٨ (تشميت العاطس)
""",
        "expected_url": "",
        "expected_project_title": "تاسيس اسألة دروس تأسيس 1",
        "expected_clips": [("00:26:34", "00:26:18", "تشميت العاطس")],
        "expected_exclusions": {},
        "expected_warnings": ["نهاية المقطع قبل بدايته"],
        "notes": "Suspicious reversed range is not silently corrected.",
    },
    {
        "name": "space_after_colon_in_time",
        "input_text": "١١- ١٧:٤٧ - ٣٤: ١٨ (تأخير الصلاة عن وقت الضرورة)",
        "expected_url": "",
        "expected_project_title": "",
        "expected_clips": [("00:17:47", "00:34:18", "تأخير الصلاة عن وقت الضرورة")],
        "expected_exclusions": {},
        "expected_warnings": [],
        "notes": "Space around colon is normalized.",
    },
    {
        "name": "maqta_fifth_same_line_labels",
        "input_text": """https://youtu.be/WQXL2VnFgFU?si=6j8ZjPEmrw5RrKm5
المقطع الخامس
البداية: 9:16 ما حكم نعي الميت
النهاية: 9:50 ولكنه مكروه
""",
        "expected_url": "https://youtu.be/WQXL2VnFgFU?si=6j8ZjPEmrw5RrKm5",
        "expected_project_title": "المقطع الخامس",
        "expected_clips": [("00:09:16", "00:09:50", "ما حكم نعي الميت")],
        "expected_exclusions": {},
        "expected_warnings": ["ملاحظة نهاية المقطع"],
        "notes": "Consistent behavior: start-line text after time is the title.",
    },
    {
        "name": "single_times_with_nearby_start_end_labels",
        "input_text": """https://www.youtube.com/live/XndQMXzgrvw?si=8x5c2am6IwEKMkBP
المقطع الاول : العجب
1:15:14 هو الله عز وجل ما الذي
البداية يريده منك

1:17:59 النهاية : هو الخاسر
""",
        "expected_url": "https://www.youtube.com/live/XndQMXzgrvw?si=8x5c2am6IwEKMkBP",
        "expected_project_title": "العجب",
        "expected_clips": [("01:15:14", "01:17:59", "العجب")],
        "expected_exclusions": {},
        "expected_warnings": ["ملاحظة بداية المقطع", "ملاحظة نهاية المقطع"],
        "notes": "Start/end labels near single timestamp lines.",
    },
    {
        "name": "plus_joined_multi_part_one_clip_candidate",
        "input_text": """10:12 - 11:35 + 12:33 - 17:51 ( السلامة من الذنوب + محاسبة النفس )
" يحتاج قص من الداخل"
شباب هذا المقطع اعملوه مقطع واحد مش مقطعين
""",
        "expected_url": "",
        "expected_project_title": "",
        "expected_clips": [("00:10:12", "00:17:51", "السلامة من الذنوب محاسبة النفس")],
        "expected_exclusions": {},
        "expected_warnings": ["تم اكتشاف مقطع متعدد الأجزاء، قد يحتاج مراجعة قبل القص"],
        "notes": "Multi-part candidate should stay one preview clip, not independent clips.",
    },
]
