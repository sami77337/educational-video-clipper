import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea

from src.main_window import (
    END_COLUMN,
    EXCLUSIONS_COLUMN,
    RULE_FOLDER_COLUMN,
    RULE_MAX_COLUMN,
    RULE_MIN_COLUMN,
    RULE_NAME_COLUMN,
    START_COLUMN,
    TITLE_COLUMN,
    MainWindow,
    SmartPasteImportDialog,
)
from src.readiness import STATUS_READY, ReadinessCheckItem, ReadinessReport
from src.smart_paste_parser import SmartPasteClip, SmartPasteExclusion, SmartPastePreview, SmartPasteWarning
from src.smart_validation import SmartValidationReport


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])



def test_main_window_uses_scroll_area_for_tall_ui() -> None:
    app = _app()
    window = MainWindow()

    assert isinstance(window.centralWidget(), QScrollArea)
    assert window.centralWidget().widgetResizable()

    window.close()
    app.processEvents()


def test_main_window_smoke_expected_widgets_and_buttons_exist() -> None:
    app = _app()
    window = MainWindow()

    assert window.windowTitle() == "المقص البسيط"
    assert [
        window.clips_table.horizontalHeaderItem(column).text()
        for column in range(window.clips_table.columnCount())
    ] == ["الرقم", "العنوان", "البداية", "النهاية", "استثناءات"]
    assert window.clips_table.columnCount() == 5
    assert window.classification_rules_table.rowCount() == 2
    assert window.youtube_radio.text() == "رابط يوتيوب"
    assert window.local_file_radio.text() == "فيديو من الجهاز"
    assert window.use_browser_cookies_checkbox.text() == "استخدام تسجيل الدخول من المتصفح"
    assert [window.browser_combo.itemText(index) for index in range(window.browser_combo.count())] == [
        "Chrome",
        "Edge",
        "Brave",
        "Firefox",
    ]
    assert window.validate_button.text() == "فحص الجدول"
    assert window.readiness_button.text() == "فحص جاهزية البرنامج"
    assert window.smart_validation_button.text() == "فحص ذكي قبل القص"
    assert window.start_button.text() == "بدء القص"
    assert window.open_output_button.text() == "فتح مجلد النتائج"
    assert window.import_excel_button.text() == "استيراد من Excel"
    assert window.smart_paste_button.text() == "استيراد ذكي من رسالة"
    assert window.parse_message_button.text() == "تحويل النص إلى جدول"

    window.close()
    app.processEvents()


def test_readiness_button_writes_arabic_report(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    captured = {}

    def fake_readiness_check(output_folder, temp_folder, *, selected_paths):
        captured["output_folder"] = output_folder
        captured["temp_folder"] = temp_folder
        captured["selected_paths"] = selected_paths
        return ReadinessReport([ReadinessCheckItem("ffmpeg", STATUS_READY, "ffmpeg جاهز")])

    monkeypatch.setattr("src.main_window.run_readiness_check", fake_readiness_check)

    window.check_readiness()

    assert "نتيجة فحص جاهزية البرنامج" in window.log_area.toPlainText()
    assert "جاهز: ffmpeg جاهز" in window.log_area.toPlainText()
    assert captured["output_folder"].name == "مشروع-بدون-اسم"
    assert captured["temp_folder"].name == "_temp_segments"

    window.close()
    app.processEvents()


def test_smart_validation_button_writes_arabic_summary(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    captured = {}

    def fake_smart_validation(rows, *, known_video_duration_seconds):
        captured["rows"] = list(rows)
        captured["known_video_duration_seconds"] = known_video_duration_seconds
        return SmartValidationReport(total_clips_count=1, issues=[])

    monkeypatch.setattr("src.main_window.validate_clips_before_cutting", fake_smart_validation)

    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("00:00:01")
    window.clips_table.item(0, END_COLUMN).setText("00:00:10")
    window.run_smart_pre_cut_validation()

    assert len(captured["rows"]) == 1
    assert captured["known_video_duration_seconds"] is None
    assert "نتيجة الفحص الذكي قبل القص" in window.log_area.toPlainText()
    assert "النتيجة: يمكن بدء القص" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_smart_paste_preview_dialog_generates_summary_and_clip_table() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    dialog.message_input.setPlainText(
        "https://youtu.be/abc123\n"
        "01:41 - 03:12 : اسم الله الوهاب\n"
        "20:10 - 26:11 عنوان آخر"
    )

    preview = dialog.generate_preview()

    assert len(preview.video_urls) == 1
    assert len(preview.clips) == 2
    assert "عدد الروابط: 1" in dialog.summary_label.text()
    assert "عدد المقاطع: 2" in dialog.summary_label.text()
    assert dialog.clips_preview_table.rowCount() == 2
    assert dialog.clips_preview_table.item(0, 0).text() == "اسم الله الوهاب"
    assert dialog.apply_button.isEnabled()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_dialog_shows_exclusions_and_notes() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    dialog.message_input.setPlainText("26:56 - 29:14 عنوان (27:40 - 28:20) أول كلمة: بداية آخر كلمة: نهاية")

    preview = dialog.generate_preview()

    assert len(preview.clips) == 1
    assert dialog.clips_preview_table.item(0, 3).text() == "00:27:40-00:28:20"
    assert "ملاحظة بداية المقطع" in dialog.clips_preview_table.item(0, 4).text()
    assert "ملاحظة نهاية المقطع" in dialog.clips_preview_table.item(0, 4).text()

    dialog.close()
    app.processEvents()


def test_smart_paste_apply_empty_url_and_table_without_processing() -> None:
    app = _app()
    window = MainWindow()
    preview = SmartPastePreview(
        video_urls=["https://youtu.be/abc123"],
        project_title="",
        clips=[
            SmartPasteClip(1, "الأول", "00:01:00", "00:02:00", 2, "01:00 - 02:00 الأول"),
            SmartPasteClip(2, "الثاني", "00:03:00", "00:04:00", 3, "03:00 - 04:00 الثاني"),
        ],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is True

    assert window.youtube_radio.isChecked()
    assert window.youtube_input.text() == "https://youtu.be/abc123"
    assert window.clips_table.rowCount() == 2
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "الأول"
    assert window._processing_thread is None
    assert "تم تطبيق 2 مقطع" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_smart_paste_does_not_overwrite_existing_url_without_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/existing")
    asked = {"url": 0}

    def cancel_url_replace():
        asked["url"] += 1
        return None

    window._ask_smart_paste_url_mode = cancel_url_replace
    preview = SmartPastePreview(
        video_urls=["https://youtu.be/new"],
        project_title="",
        clips=[],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is False
    assert asked["url"] == 1
    assert window.youtube_input.text() == "https://youtu.be/existing"

    window.close()
    app.processEvents()


def test_smart_paste_does_not_overwrite_existing_table_without_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("قديم")
    window.clips_table.item(0, START_COLUMN).setText("00:00:01")
    window.clips_table.item(0, END_COLUMN).setText("00:00:02")
    asked = {"table": 0}

    def cancel_table_apply():
        asked["table"] += 1
        return None

    window._ask_smart_paste_clip_mode = cancel_table_apply
    preview = SmartPastePreview(
        video_urls=[],
        project_title="",
        clips=[SmartPasteClip(1, "جديد", "00:01:00", "00:02:00", 1, "01:00 - 02:00 جديد")],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is False
    assert asked["table"] == 1
    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "قديم"

    window.close()
    app.processEvents()


def test_smart_paste_can_keep_existing_url_and_append_clips_with_warnings() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/existing")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("قديم")
    window.clips_table.item(0, START_COLUMN).setText("00:00:01")
    window.clips_table.item(0, END_COLUMN).setText("00:00:02")
    window._ask_smart_paste_url_mode = lambda: "keep"
    window._ask_smart_paste_clip_mode = lambda: "append"
    preview = SmartPastePreview(
        video_urls=["https://youtu.be/new"],
        project_title="",
        clips=[SmartPasteClip(1, "جديد", "00:01:00", "00:02:00", 1, "01:00 - 02:00 جديد")],
        warnings=[SmartPasteWarning(1, "تحذير", "x")],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is True
    assert window.youtube_input.text() == "https://youtu.be/existing"
    assert window.clips_table.rowCount() == 2
    assert window.clips_table.item(1, TITLE_COLUMN).text() == "جديد"
    assert "تم التطبيق مع 1 تحذير" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_smart_paste_applies_exclusions_to_existing_table_column() -> None:
    app = _app()
    window = MainWindow()
    preview = SmartPastePreview(
        video_urls=[],
        project_title="",
        clips=[
            SmartPasteClip(
                1,
                "مع استثناء",
                "00:26:56",
                "00:29:14",
                1,
                "26:56 - 29:14 (27:40 - 28:20)",
                exclusions=[SmartPasteExclusion("00:27:40", "00:28:20")],
            )
        ],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is True
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:27:40-00:28:20"

    window.close()
    app.processEvents()


def test_log_append_updates_text_immediately() -> None:
    app = _app()
    window = MainWindow()

    window._write_log("بداية")
    window._append_log("رسالة تقدم")
    app.processEvents()

    assert "بداية" in window.log_area.toPlainText()
    assert "رسالة تقدم" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_processing_status_label_uses_clear_running_and_finish_states() -> None:
    app = _app()
    window = MainWindow()

    window._set_processing_enabled(False)
    assert "جاري المعالجة" in window.processing_status_label.text()
    assert not window.start_button.isEnabled()

    window._handle_processing_success("C:/tmp/output")
    assert "تم الانتهاء بنجاح" in window.processing_status_label.text()

    window._handle_processing_failure("فشل تجريبي")
    assert "فشل التنفيذ" in window.processing_status_label.text()

    window.close()
    app.processEvents()

def test_table_starts_empty_and_add_row_creates_blank_row() -> None:
    app = _app()
    window = MainWindow()

    assert window.clips_table.rowCount() == 0

    window.add_clip_row()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.columnCount() == 5
    assert window.clips_table.item(0, TITLE_COLUMN).text() == ""
    assert window.clips_table.item(0, START_COLUMN).text() == ""
    assert window.clips_table.item(0, END_COLUMN).text() == ""
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == ""

    window.close()
    app.processEvents()


def test_validation_reports_empty_table_in_arabic() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")

    assert window.validate_inputs() is False
    assert "أضف مقطعًا واحدًا على الأقل" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_successful_validation_normalizes_table_times() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("4:15")
    window.clips_table.item(0, END_COLUMN).setText("6:35")

    assert window.validate_inputs() is True
    assert window.clips_table.item(0, START_COLUMN).text() == "00:04:15"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:06:35"

    window.close()
    app.processEvents()


def test_empty_exclusions_validate_successfully() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("4:15")
    window.clips_table.item(0, END_COLUMN).setText("6:35")
    window.clips_table.item(0, EXCLUSIONS_COLUMN).setText("   ")

    assert window.validate_inputs() is True
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == ""

    window.close()
    app.processEvents()


def test_validation_normalizes_exclusions_column() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("26:56")
    window.clips_table.item(0, END_COLUMN).setText("29:14")
    window.clips_table.item(0, EXCLUSIONS_COLUMN).setText("٢٧ : ٤٠ - ٢٨ : ٢٠")

    assert window.validate_inputs() is True
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:27:40-00:28:20"

    window.close()
    app.processEvents()


def test_invalid_exclusions_show_arabic_error() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("26:56")
    window.clips_table.item(0, END_COLUMN).setText("29:14")
    window.clips_table.item(0, EXCLUSIONS_COLUMN).setText("25:00 - 26:00")

    assert window.validate_inputs() is False
    assert "الاستثناء خارج حدود المقطع" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_source_selection_disables_inactive_input() -> None:
    app = _app()
    window = MainWindow()

    assert window.youtube_input.isEnabled()
    assert not window.local_file_input.isEnabled()
    assert not window.browse_button.isEnabled()

    window.local_file_radio.setChecked(True)

    assert not window.youtube_input.isEnabled()
    assert window.local_file_input.isEnabled()
    assert window.browse_button.isEnabled()
    assert "فيديو من الجهاز" in window.source_status_label.text()

    window.close()
    app.processEvents()


def test_logs_include_simple_timestamp() -> None:
    app = _app()
    window = MainWindow()

    window._write_log("رسالة اختبار")

    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] رسالة اختبار", window.log_area.toPlainText())

    window.close()
    app.processEvents()


def test_clear_table_asks_confirmation_before_clearing() -> None:
    app = _app()
    window = MainWindow()
    window.add_clip_row()
    window._ask_clear_table_confirmation = lambda: True

    window.clear_table()

    assert window.clips_table.rowCount() == 0
    assert "تم مسح الجدول" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_pasted_text_fills_exclusions_column() -> None:
    app = _app()
    window = MainWindow()
    window.paste_message_input.setPlainText("26:56 - 29:14 مابين القوسين يقطع (27:40 - 28:20)")

    window.convert_pasted_text_to_table()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, START_COLUMN).text() == "00:26:56"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:29:14"
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:27:40-00:28:20"

    window.close()
    app.processEvents()


def test_imported_rows_fill_exclusions_column() -> None:
    app = _app()
    window = MainWindow()
    from src.import_utils import ImportedClipRow

    window._insert_clip_lines(
        [
            ImportedClipRow(
                number=1,
                title="مع حذف",
                start="00:26:56",
                end="00:29:14",
                exclusions="00:27:40-00:28:20",
            )
        ],
        append=False,
    )

    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:27:40-00:28:20"

    window.close()
    app.processEvents()


def test_default_ui_classification_rules_preserve_existing_behavior() -> None:
    app = _app()
    window = MainWindow()

    assert window.classification_rules_table.rowCount() == 2
    assert window.classification_rules_table.item(0, RULE_NAME_COLUMN).text() == "ريلز"
    assert window.classification_rules_table.item(0, RULE_MIN_COLUMN).text() == "0"
    assert window.classification_rules_table.item(0, RULE_MAX_COLUMN).text() == "3"
    assert window.classification_rules_table.item(0, RULE_FOLDER_COLUMN).text() == "ريلز"
    assert window.classification_rules_table.item(1, RULE_NAME_COLUMN).text() == "فوائد"
    assert window.classification_rules_table.item(1, RULE_MAX_COLUMN).text() == "مفتوح"

    window.close()
    app.processEvents()


def test_custom_three_rule_ui_classification_rules_are_collected() -> None:
    app = _app()
    window = MainWindow()
    window.classification_rules_table.setRowCount(0)

    for values in (
        ("Shorts", "0", "1", "Shorts"),
        ("ريلز", "1", "3", "ريلز"),
        ("فوائد طويلة", "3", "مفتوح", "فوائد طويلة"),
    ):
        window.add_classification_rule()
        row = window.classification_rules_table.rowCount() - 1
        for column, value in enumerate(values):
            window.classification_rules_table.item(row, column).setText(value)

    rules = window._collect_classification_rules()

    assert len(rules) == 3
    assert rules[0].name == "Shorts"
    assert rules[0].max_minutes == 1
    assert rules[2].folder_name == "فوائد طويلة"
    assert rules[2].max_minutes is None

    window.close()
    app.processEvents()


def test_invalid_ui_classification_rules_stop_processing() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("00:00:00")
    window.clips_table.item(0, END_COLUMN).setText("00:00:30")
    window.classification_rules_table.item(0, RULE_NAME_COLUMN).setText("")

    window.start_processing()

    assert window._processing_thread is None
    assert "جاري فحص قواعد التصنيف" in window.log_area.toPlainText()
    assert "اسم التصنيف فارغ" in window.log_area.toPlainText()

    window.close()
    app.processEvents()
