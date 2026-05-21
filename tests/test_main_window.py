import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox, QLabel, QPushButton, QScrollArea

from src.main_window import (
    END_COLUMN,
    EXCLUSIONS_COLUMN,
    QUEUE_ACTION_COLUMN,
    QUEUE_CLIP_COUNT_COLUMN,
    QUEUE_HIGH_PRIORITY_COLUMN,
    QUEUE_SOURCE_COLUMN,
    QUEUE_STATUS_COLUMN,
    QUEUE_TITLE_COLUMN,
    RULE_FOLDER_COLUMN,
    RULE_MAX_COLUMN,
    RULE_MIN_COLUMN,
    RULE_NAME_COLUMN,
    SMART_PASTE_APPEND_LABEL,
    SMART_PASTE_CANCEL_LABEL,
    SMART_PASTE_QUEUE_LABEL,
    SMART_PASTE_REPLACE_LABEL,
    START_COLUMN,
    TITLE_COLUMN,
    MainWindow,
    QueueProcessingWorker,
    SmartPasteImportDialog,
)
from src.job_queue import ClipJob, JobStatus, VideoJob, VideoSourceType as QueueVideoSourceType
from src.job_queue_processor import AR_QUEUE_NEXT_JOB_STARTED, AR_URL_QUEUE_PROCESSING_LATER
from src.readiness import STATUS_READY, ReadinessCheckItem, ReadinessReport
from src.video_black_flash import AR_BLACK_FLASH_APPLIED
from src.video_export_quality import AR_EXPORT_QUALITY_APPLIED
from src.smart_paste_parser import (
    SmartPasteClip,
    SmartPasteExclusion,
    SmartPastePart,
    SmartPastePreview,
    SmartPasteUnparsedLine,
    SmartPasteWarning,
    parse_smart_paste_message,
)
from src.smart_validation import SmartValidationReport
from tests.fixtures.smart_import_real_messages import SMART_IMPORT_REAL_MESSAGES


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _smart_import_fixture(name: str) -> dict:
    for sample in SMART_IMPORT_REAL_MESSAGES:
        if sample["name"] == name:
            return sample
    raise AssertionError(f"Unknown smart import fixture: {name}")


def _ancestor_group_titles(widget) -> list[str]:
    titles: list[str] = []
    parent = widget.parent()
    while parent is not None:
        if isinstance(parent, QGroupBox):
            titles.append(parent.title())
        parent = parent.parent()
    return titles


def _process_events_until(app: QApplication, condition, timeout_ms: int = 2000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    return condition()



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
    assert window.validate_button.text() == "فحص ذكي قبل القص"
    assert window.readiness_button.text() == "فحص جاهزية البرنامج"
    assert window.smart_validation_button.text() == "فحص ذكي قبل القص"
    assert window.start_button.text() == "بدء القص"
    assert window.new_work_button.text() == "عمل جديد"
    assert window.direct_cut_button.text() == "بدء القص المباشر - وضع قديم"
    assert window.open_output_button.text() == "فتح مجلد النتائج"
    assert window.pre_padding_input.value() == 0
    assert window.post_padding_input.value() == 0
    assert window.video_speed_enabled_checkbox.text() == "تعديل سرعة الفيديو"
    assert window.volume_enabled_checkbox.text() == "تعديل مستوى الصوت"
    assert not window.video_speed_enabled_checkbox.isChecked()
    assert not window.volume_enabled_checkbox.isChecked()
    assert window.video_speed_input.value() == 1.0
    assert window.volume_input.value() == 100
    assert not window.video_speed_input.isEnabled()
    assert not window.volume_input.isEnabled()
    assert window.reset_video_speed_button.text() == "إعادة السرعة إلى 1.00x"
    assert window.reset_volume_button.text() == "إعادة الصوت إلى 100%"
    assert window.black_fade_enabled_checkbox.text() == "إضافة بداية ونهاية سوداء تدريجية"
    assert not window.black_fade_enabled_checkbox.isChecked()
    assert not window.fade_in_duration_combo.isEnabled()
    assert not window.fade_out_duration_combo.isEnabled()
    assert window.fade_in_duration_combo.currentText() == "0.50 ثانية"
    assert window.fade_out_duration_combo.currentText() == "0.50 ثانية"
    assert window.black_flash_enabled_checkbox.text() == "إضافة وميض أسود عند الاستثناء"
    assert not window.black_flash_enabled_checkbox.isChecked()
    assert not window.black_flash_duration_combo.isEnabled()
    assert window.black_flash_duration_combo.currentText() == "0.20 ثانية"
    assert window.export_quality_enabled_checkbox.text() == "تخصيص جودة التصدير"
    assert not window.export_quality_enabled_checkbox.isChecked()
    assert not window.export_quality_preset_combo.isEnabled()
    assert not window.resolution_limit_combo.isEnabled()
    assert window.export_quality_preset_combo.currentText() == "متوازن"
    assert window.resolution_limit_combo.currentText() == "الأصلية"
    assert window.pre_padding_input.minimum() == 0
    assert window.post_padding_input.minimum() == 0
    assert window.video_speed_input.minimum() == 0.75
    assert window.volume_input.minimum() == 75
    window.pre_padding_input.setValue(-1)
    window.post_padding_input.setValue(-1)
    window.video_speed_input.setValue(0)
    window.volume_input.setValue(0)
    assert window.pre_padding_input.value() == 0
    assert window.post_padding_input.value() == 0
    assert window.video_speed_input.value() > 0
    assert window.volume_input.value() > 0
    assert window.import_excel_button.text() == "استيراد من Excel"
    assert window.smart_paste_button.text() == "استيراد ذكي"
    assert window.parse_message_button.text() == "تحويل بسيط إلى جدول"
    assert window.parse_message_button.parent() is None
    assert not window.parse_message_button.isVisible()
    visible_button_texts = [
        button.text()
        for button in window.findChildren(QPushButton)
        if button.isVisible()
    ]
    assert not any("ZIP" in text or "ضغط" in text for text in visible_button_texts)
    assert window.delete_row_button.text() == "حذف المقطع المحدد"
    assert window.preview_clip_start_button.text() == "معاينة بداية المقطع"
    assert window.preview_clip_end_button.text() == "معاينة نهاية المقطع"
    assert window.preview_selected_clip_button.text() == "معاينة المقطع المحدد"
    assert [
        window.queue_table.horizontalHeaderItem(column).text()
        for column in range(window.queue_table.columnCount())
    ] == ["المصدر", "العنوان", "عدد المقاطع", "الحالة", "أولوية عالية", "الإجراء"]
    assert window.queue_table.rowCount() == 0
    assert window.queue_job_details_label.text() == "لم يتم تحديد مهمة"
    assert window.copy_queue_job_details_button.text() == "نسخ تفاصيل المهمة"
    assert window.show_global_log_button.text() == "عرض السجل العام"
    assert window.log_header_label.text() == "سجل عام"
    assert window.add_current_work_to_queue_button.text() == "إضافة العمل الحالي إلى قائمة الانتظار"
    assert window.add_queue_local_video_button.text() == "إضافة فيديو محلي"
    assert window.add_queue_url_button.text() == "إضافة رابط"
    assert window.save_queue_clips_button.text() == "حفظ مقاطع المهمة المحددة"
    assert window.load_queue_clips_button.text() == "تحميل مقاطع المهمة المحددة"
    assert window.load_queue_job_workspace_button.text() == "تعديل المهمة المنتظرة"
    assert window.save_queue_job_edits_button.text() == "حفظ التعديلات على المهمة"
    assert window.cancel_queue_job_edit_button.text() == "إلغاء تعديل المهمة"
    assert window.save_queue_state_button.text() == "حفظ قائمة الانتظار"
    assert window.load_queue_state_button.text() == "تحميل قائمة الانتظار"
    assert window.add_and_run_queue_job_button.text() == "إضافة وتشغيل في قائمة الانتظار"
    assert window.start_queue_processing_button.text() == "بدء معالجة قائمة الانتظار"
    assert window.stop_queue_after_current_button.text() == "إيقاف بعد المهمة الحالية"
    assert not window.stop_queue_after_current_button.isEnabled()
    assert window.run_selected_queue_job_button.text() == "تشغيل المهمة المحددة"
    assert window.run_all_queue_simulation_button.text() == "اختبار القائمة بدون قص"
    assert window.validate_queue_job_button.text() == "إعادة فحص المهمة المحددة"
    assert window.validate_all_queue_jobs_button.text() == "فحص قائمة الانتظار بالكامل"
    assert window.delete_queue_job_button.text() == "إزالة المهمة المحددة"
    assert window.clear_queue_button.text() == "مسح القائمة"
    for button in (
        window.start_button,
        window.new_work_button,
        window.validate_button,
        window.open_output_button,
    ):
        assert "التشغيل والنتائج" in _ancestor_group_titles(button)
    assert not window.add_and_run_queue_job_button.isVisible()
    assert "إدارة قائمة الانتظار المتقدمة" in _ancestor_group_titles(window.direct_cut_button)
    assert window.queue_advanced_group.title() == "إدارة قائمة الانتظار المتقدمة"
    assert window.queue_advanced_toggle_button.text() == "إدارة قائمة الانتظار المتقدمة"
    assert not window.queue_advanced_toggle_button.isChecked()
    assert not window.queue_advanced_controls_widget.isVisible()
    for button in (
        window.validate_all_queue_jobs_button,
        window.run_all_queue_simulation_button,
        window.save_queue_state_button,
        window.load_queue_state_button,
        window.delete_queue_job_button,
        window.clear_queue_button,
    ):
        assert "قائمة الانتظار" in _ancestor_group_titles(button)
        assert "إدارة قائمة الانتظار المتقدمة" in _ancestor_group_titles(button)

    window.close()
    app.processEvents()


def test_cut_export_settings_are_grouped_into_clear_sections() -> None:
    app = _app()
    window = MainWindow()

    section_titles = {group.title() for group in window.findChildren(QGroupBox)}
    assert "إعدادات القص الأساسية" in section_titles
    assert "تعديلات اختيارية" in section_titles
    assert "المؤثرات البصرية الاختيارية" in section_titles
    assert "جودة التصدير" in section_titles

    assert "إعدادات القص الأساسية" in _ancestor_group_titles(window.pre_padding_input)
    assert "إعدادات القص الأساسية" in _ancestor_group_titles(window.post_padding_input)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.video_speed_enabled_checkbox)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.video_speed_input)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.reset_video_speed_button)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.volume_enabled_checkbox)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.volume_input)
    assert "تعديلات اختيارية" in _ancestor_group_titles(window.reset_volume_button)
    assert "المؤثرات البصرية الاختيارية" in _ancestor_group_titles(window.black_fade_enabled_checkbox)
    assert "المؤثرات البصرية الاختيارية" in _ancestor_group_titles(window.fade_in_duration_combo)
    assert "المؤثرات البصرية الاختيارية" in _ancestor_group_titles(window.fade_out_duration_combo)
    assert "المؤثرات البصرية الاختيارية" in _ancestor_group_titles(window.black_flash_enabled_checkbox)
    assert "المؤثرات البصرية الاختيارية" in _ancestor_group_titles(window.black_flash_duration_combo)
    assert "جودة التصدير" in _ancestor_group_titles(window.export_quality_enabled_checkbox)
    assert "جودة التصدير" in _ancestor_group_titles(window.export_quality_preset_combo)
    assert "جودة التصدير" in _ancestor_group_titles(window.resolution_limit_combo)
    assert any(
        label.text() == "الإعدادات الاختيارية لا تؤثر على التصدير إلا عند تفعيلها."
        for label in window.findChildren(QLabel)
    )

    window.close()
    app.processEvents()


def test_queue_add_current_local_work_with_clip_rows() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع محلي")
    window.youtube_input.setText("https://youtu.be/unused")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/lesson.mp4")
    window._insert_clip_row(1, "المقطع الأول", "00:01:00", "00:02:00", "00:01:20-00:01:30")

    window.add_current_work_to_queue()

    assert len(window.job_queue) == 1
    job = window.job_queue[0]
    assert job.source_type == QueueVideoSourceType.LOCAL
    assert job.source.replace("\\", "/") == "C:/videos/lesson.mp4"
    assert job.title == "مشروع محلي"
    assert job.settings.high_priority is False
    assert job.status == JobStatus.DRAFT
    assert len(job.clips) == 1
    assert job.clips[0].title == "المقطع الأول"
    assert job.clips[0].start == "00:01:00"
    assert job.clips[0].end == "00:02:00"
    assert job.clips[0].exclusions == "00:01:20-00:01:30"
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "فيديو محلي"
    assert window.queue_table.item(0, QUEUE_TITLE_COLUMN).text() == "مشروع محلي"
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert window.queue_table.item(0, QUEUE_HIGH_PRIORITY_COLUMN).checkState() == Qt.Unchecked
    assert "تم إضافة العمل الحالي إلى قائمة الانتظار" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_selecting_queue_job_shows_job_log_and_details_without_loading_editor() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_job(
        QueueVideoSourceType.YOUTUBE,
        "https://youtube.com/watch?v=abc123&token=secret",
        "درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30")],
        status=JobStatus.QUEUED,
    )
    job.settings.pre_roll_seconds = 1.0
    job.settings.post_roll_seconds = 2.0
    job.settings.speed_adjustment_enabled = True
    job.settings.speed = 1.10
    job.settings.volume_adjustment_enabled = True
    job.settings.volume_percent = 150
    job.settings.fade_enabled = True
    job.settings.fade_in_seconds = 1.0
    job.settings.fade_out_seconds = 1.5
    job.settings.black_flash_enabled = True
    job.settings.black_flash_duration_seconds = 0.3
    job.settings.export_quality_enabled = True
    job.settings.quality_preset = "high"
    job.settings.resolution_limit = "1080p"
    job.settings.use_browser_login = True
    job.settings.browser_name = "firefox"
    job.add_log("رسالة خاصة بالمهمة")
    window.project_name_input.setText("المحرر الحالي")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    app.processEvents()

    assert window.log_header_label.text() == "سجل المهمة المحددة"
    assert "رسالة خاصة بالمهمة" in window.log_area.toPlainText()
    details = window.queue_job_details_label.text()
    assert "تفاصيل" not in details
    assert "درس" in details
    assert "00:01:20-00:01:30" in window.queue_job_clips_table.item(0, EXCLUSIONS_COLUMN).text()
    assert "1.10x" in details
    assert "150%" in details
    assert "هل البداية والنهاية السوداء مفعّلة؟ نعم" in details
    assert "1.00 ثانية" in details
    assert "1.50 ثانية" in details
    assert "هل الوميض الأسود عند الاستثناء مفعّل؟ نعم" in details
    assert "0.30 ثانية" in details
    assert "هل تخصيص جودة التصدير مفعّل؟ نعم" in details
    assert "جودة التصدير: جودة عالية" in details
    assert "حد الدقة: 1080p" in details
    assert "firefox" in details
    assert "secret" not in details
    assert window.project_name_input.text() == "المحرر الحالي"
    assert window.clips_table.rowCount() == 0

    window.show_global_log()

    assert window.log_header_label.text() == "سجل عام"

    window.close()
    app.processEvents()


def test_failed_queue_job_details_and_row_show_failure_reason() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="يفشل")
    job.mark_status(JobStatus.FAILED)
    job.mark_failed("فشل تحميل أو معالجة رابط يوتيوب: sign in required", "download")
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    app.processEvents()

    assert "سبب الفشل" in window.queue_table.item(0, QUEUE_ACTION_COLUMN).text()
    assert "سبب الفشل" in window.queue_job_details_label.text()
    assert "download" in window.queue_job_details_label.text()
    assert "فشل تحميل أو معالجة رابط يوتيوب" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_new_work_resets_workspace_without_clearing_queue_or_running_job(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="موجودة")
    window._queue_processing_thread = object()
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/current.mp4")
    window.project_name_input.setText("عمل حالي")
    window.paste_message_input.setPlainText("رسالة")
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00", "00:01:20-00:01:30")
    window.pre_padding_input.setValue(2)
    window.post_padding_input.setValue(3)
    window.video_speed_enabled_checkbox.setChecked(True)
    window.video_speed_input.setValue(1.10)
    window.volume_enabled_checkbox.setChecked(True)
    window.volume_input.setValue(150)
    window.black_fade_enabled_checkbox.setChecked(True)
    window.fade_in_duration_combo.setCurrentText("1.00 ثانية")
    window.fade_out_duration_combo.setCurrentText("1.50 ثانية")
    window.black_flash_enabled_checkbox.setChecked(True)
    window.black_flash_duration_combo.setCurrentText("0.30 ثانية")
    window.export_quality_enabled_checkbox.setChecked(True)
    window.export_quality_preset_combo.setCurrentText("حجم أصغر")
    window.resolution_limit_combo.setCurrentText("720p")
    monkeypatch.setattr(window, "_ask_new_work_confirmation", lambda: True)

    window.start_new_work()

    assert len(window.job_queue) == 1
    assert window._queue_processing_thread is not None
    assert window.youtube_input.text() == ""
    assert window.local_file_input.text() == ""
    assert window.project_name_input.text() == ""
    assert window.paste_message_input.toPlainText() == ""
    assert window.clips_table.rowCount() == 0
    assert window.pre_padding_input.value() == 0
    assert window.post_padding_input.value() == 0
    assert not window.video_speed_enabled_checkbox.isChecked()
    assert window.video_speed_input.value() == 1.0
    assert not window.volume_enabled_checkbox.isChecked()
    assert window.volume_input.value() == 100
    assert not window.black_fade_enabled_checkbox.isChecked()
    assert window.fade_in_duration_combo.currentText() == "0.50 ثانية"
    assert window.fade_out_duration_combo.currentText() == "0.50 ثانية"
    assert not window.black_flash_enabled_checkbox.isChecked()
    assert window.black_flash_duration_combo.currentText() == "0.20 ثانية"
    assert not window.export_quality_enabled_checkbox.isChecked()
    assert window.export_quality_preset_combo.currentText() == "متوازن"
    assert window.resolution_limit_combo.currentText() == "الأصلية"
    assert "المهمة الجارية مستمرة في الخلفية" in window.log_area.toPlainText()

    window._queue_processing_thread = None
    window.close()
    app.processEvents()


def test_speed_and_volume_controls_require_explicit_enable() -> None:
    app = _app()
    window = MainWindow()

    window.video_speed_input.setValue(1.10)
    window.volume_input.setValue(150)

    assert window._collect_video_speed() == 1.0
    assert window._collect_volume_percent() == 100
    settings = window._current_job_settings_snapshot()
    assert settings.speed_adjustment_enabled is False
    assert settings.speed == 1.0
    assert settings.volume_adjustment_enabled is False
    assert settings.volume_percent == 100
    assert settings.fade_enabled is False
    assert settings.black_flash_enabled is False
    assert settings.black_flash_duration_seconds == 0.2
    assert settings.export_quality_enabled is False
    assert settings.quality_preset == "default"
    assert settings.resolution_limit == "original"

    window.video_speed_enabled_checkbox.setChecked(True)
    window.volume_enabled_checkbox.setChecked(True)

    assert window.video_speed_input.isEnabled()
    assert window.volume_input.isEnabled()
    assert window._collect_video_speed() == 1.1
    assert window._collect_volume_percent() == 150
    assert "تسريع الفيديو" in window.video_speed_status_label.text()
    assert "رفع الصوت" in window.volume_status_label.text()

    window.video_speed_input.setValue(0.75)
    window.volume_input.setValue(75)
    assert "تبطيء الفيديو" in window.video_speed_status_label.text()
    assert "أقل من الطبيعي" in window.volume_status_label.text()

    window.reset_video_speed()
    window.reset_volume()
    assert window.video_speed_input.value() == 1.0
    assert window.volume_input.value() == 100

    window.close()
    app.processEvents()


def test_black_fade_controls_require_explicit_enable_and_snapshot_settings() -> None:
    app = _app()
    window = MainWindow()

    assert not window.black_fade_enabled_checkbox.isChecked()
    assert not window.fade_in_duration_combo.isEnabled()
    assert not window.fade_out_duration_combo.isEnabled()
    assert window._collect_clip_fade().enabled is False

    window.black_fade_enabled_checkbox.setChecked(True)
    window.fade_in_duration_combo.setCurrentText("1.00 ثانية")
    window.fade_out_duration_combo.setCurrentText("1.50 ثانية")

    fade = window._collect_clip_fade()
    settings = window._current_job_settings_snapshot()

    assert window.fade_in_duration_combo.isEnabled()
    assert window.fade_out_duration_combo.isEnabled()
    assert fade.enabled is True
    assert fade.fade_in_seconds == 1.0
    assert fade.fade_out_seconds == 1.5
    assert settings.fade_enabled is True
    assert settings.fade_in_seconds == 1.0
    assert settings.fade_out_seconds == 1.5
    assert "بداية ونهاية سوداء تدريجية" in window.black_fade_status_label.text()

    window.close()
    app.processEvents()


def test_black_flash_controls_require_explicit_enable_and_snapshot_settings() -> None:
    app = _app()
    window = MainWindow()

    assert not window.black_flash_enabled_checkbox.isChecked()
    assert not window.black_flash_duration_combo.isEnabled()
    assert window._collect_clip_black_flash().enabled is False

    window.black_flash_enabled_checkbox.setChecked(True)
    window.black_flash_duration_combo.setCurrentText("0.30 ثانية")

    flash = window._collect_clip_black_flash()
    settings = window._current_job_settings_snapshot()

    assert window.black_flash_duration_combo.isEnabled()
    assert flash.enabled is True
    assert flash.duration_seconds == 0.3
    assert settings.black_flash_enabled is True
    assert settings.black_flash_duration_seconds == 0.3
    assert "وميض أسود عند الاستثناء" in window.black_flash_status_label.text()

    window.close()
    app.processEvents()


def test_export_quality_controls_require_explicit_enable_and_snapshot_settings() -> None:
    app = _app()
    window = MainWindow()

    assert not window.export_quality_enabled_checkbox.isChecked()
    assert not window.export_quality_preset_combo.isEnabled()
    assert not window.resolution_limit_combo.isEnabled()
    assert window._collect_export_quality_settings().enabled is False

    window.export_quality_enabled_checkbox.setChecked(True)
    window.export_quality_preset_combo.setCurrentText("حجم أصغر")
    window.resolution_limit_combo.setCurrentText("720p")

    export_quality = window._collect_export_quality_settings()
    settings = window._current_job_settings_snapshot()

    assert window.export_quality_preset_combo.isEnabled()
    assert window.resolution_limit_combo.isEnabled()
    assert export_quality.enabled is True
    assert export_quality.quality_preset == "small"
    assert export_quality.resolution_limit == "720p"
    assert settings.export_quality_enabled is True
    assert settings.quality_preset == "small"
    assert settings.resolution_limit == "720p"
    assert "جودة التصدير" in window.export_quality_status_label.text()

    window.close()
    app.processEvents()


def test_queue_current_work_snapshot_is_independent_from_later_table_edits() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/lesson.mp4")
    window.pre_padding_input.setValue(1.5)
    window.post_padding_input.setValue(2.0)
    window.video_speed_enabled_checkbox.setChecked(True)
    window.volume_enabled_checkbox.setChecked(True)
    window.video_speed_input.setValue(1.10)
    window.volume_input.setValue(150)
    window.black_fade_enabled_checkbox.setChecked(True)
    window.fade_in_duration_combo.setCurrentText("1.00 ثانية")
    window.fade_out_duration_combo.setCurrentText("1.50 ثانية")
    window.black_flash_enabled_checkbox.setChecked(True)
    window.black_flash_duration_combo.setCurrentText("0.30 ثانية")
    window.export_quality_enabled_checkbox.setChecked(True)
    window.export_quality_preset_combo.setCurrentText("حجم أصغر")
    window.resolution_limit_combo.setCurrentText("720p")
    window._insert_clip_row(1, "قديم", "00:01:00", "00:02:00", "00:01:20-00:01:30")

    window.add_current_work_to_queue()
    window.clips_table.item(0, TITLE_COLUMN).setText("معدل")
    window.clips_table.item(0, START_COLUMN).setText("00:05:00")
    window.pre_padding_input.setValue(0)
    window.post_padding_input.setValue(0)
    window.video_speed_input.setValue(1.0)
    window.volume_input.setValue(100)
    window.black_fade_enabled_checkbox.setChecked(False)
    window.black_flash_enabled_checkbox.setChecked(False)
    window.export_quality_enabled_checkbox.setChecked(False)
    window.export_quality_preset_combo.setCurrentText("جودة عالية")
    window.resolution_limit_combo.setCurrentText("1080p")

    job = window.job_queue[0]
    assert job.clips[0].title == "قديم"
    assert job.clips[0].start == "00:01:00"
    assert job.settings.pre_roll_seconds == 1.5
    assert job.settings.post_roll_seconds == 2.0
    assert job.settings.speed_adjustment_enabled is True
    assert job.settings.speed == 1.1
    assert job.settings.volume_adjustment_enabled is True
    assert job.settings.volume_percent == 150
    assert job.settings.fade_enabled is True
    assert job.settings.fade_in_seconds == 1.0
    assert job.settings.fade_out_seconds == 1.5
    assert job.settings.black_flash_enabled is True
    assert job.settings.black_flash_duration_seconds == 0.3
    assert job.settings.export_quality_enabled is True
    assert job.settings.quality_preset == "small"
    assert job.settings.resolution_limit == "720p"

    window.close()
    app.processEvents()


def test_queue_jobs_snapshot_speed_independently_from_later_ui_edits() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/lesson.mp4")
    window.video_speed_enabled_checkbox.setChecked(True)
    window.video_speed_input.setValue(1.05)
    window._insert_clip_row(1, "الأول", "00:01:00", "00:02:00")

    window.add_current_work_to_queue()
    window.video_speed_input.setValue(1.25)
    window.clips_table.item(0, TITLE_COLUMN).setText("الثاني")
    window.add_current_work_to_queue()
    window.video_speed_input.setValue(1.0)
    window.clips_table.item(0, TITLE_COLUMN).setText("تعديل لاحق")

    assert len(window.job_queue) == 2
    assert window.job_queue[0].settings.speed_adjustment_enabled is True
    assert window.job_queue[1].settings.speed_adjustment_enabled is True
    assert window.job_queue[0].settings.speed == 1.05
    assert window.job_queue[1].settings.speed == 1.25
    assert window.job_queue[0].clips[0].title == "الأول"
    assert window.job_queue[1].clips[0].title == "الثاني"

    window.close()
    app.processEvents()


def test_queue_jobs_snapshot_volume_independently_from_later_ui_edits() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/lesson.mp4")
    window.volume_enabled_checkbox.setChecked(True)
    window.volume_input.setValue(75)
    window._insert_clip_row(1, "الأول", "00:01:00", "00:02:00")

    window.add_current_work_to_queue()
    window.volume_input.setValue(200)
    window.clips_table.item(0, TITLE_COLUMN).setText("الثاني")
    window.add_current_work_to_queue()
    window.volume_input.setValue(100)
    window.clips_table.item(0, TITLE_COLUMN).setText("تعديل لاحق")

    assert len(window.job_queue) == 2
    assert window.job_queue[0].settings.volume_adjustment_enabled is True
    assert window.job_queue[1].settings.volume_adjustment_enabled is True
    assert window.job_queue[0].settings.volume_percent == 75
    assert window.job_queue[1].settings.volume_percent == 200
    assert window.job_queue[0].clips[0].title == "الأول"
    assert window.job_queue[1].clips[0].title == "الثاني"

    window.close()
    app.processEvents()


def test_queue_add_current_work_and_start_snapshots_job_without_direct_processing(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    started: list[bool] = []
    window.project_name_input.setText("مشروع")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/lesson.mp4")
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00")
    monkeypatch.setattr(window, "start_queue_processing", lambda: started.append(True))

    window.start_button.click()

    assert started == [True]
    assert len(window.job_queue) == 1
    assert window.job_queue[0].status == JobStatus.QUEUED
    assert "تم إضافة المهمة إلى قائمة الانتظار" in window.log_area.toPlainText()
    assert "يمكنك تجهيز مهمة أخرى أثناء المعالجة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None
    assert window._queue_processing_thread is None

    window.close()
    app.processEvents()


def test_main_queue_cut_button_click_creates_job_and_starts_idle_queue(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"video")
    started: list[int] = []
    window.project_name_input.setText("مشروع قص")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(video_path))
    window.pre_padding_input.setValue(0.5)
    window.post_padding_input.setValue(1.0)
    window.video_speed_enabled_checkbox.setChecked(True)
    window.volume_enabled_checkbox.setChecked(True)
    window.video_speed_input.setValue(1.05)
    window.volume_input.setValue(150)
    window.black_fade_enabled_checkbox.setChecked(True)
    window.fade_in_duration_combo.setCurrentText("1.00 ثانية")
    window.fade_out_duration_combo.setCurrentText("1.50 ثانية")
    window.black_flash_enabled_checkbox.setChecked(True)
    window.black_flash_duration_combo.setCurrentText("0.30 ثانية")
    window.export_quality_enabled_checkbox.setChecked(True)
    window.export_quality_preset_combo.setCurrentText("جودة عالية")
    window.resolution_limit_combo.setCurrentText("1080p")
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00", "00:01:20-00:01:30")
    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda rules: started.append(len(rules)))

    window.start_button.click()
    app.processEvents()

    assert started == [2]
    assert len(window.job_queue) == 1
    job = window.job_queue[0]
    assert job.source_type == QueueVideoSourceType.LOCAL
    assert job.source == str(video_path)
    assert job.title == "مشروع قص"
    assert job.status == JobStatus.QUEUED
    assert job.settings.pre_roll_seconds == 0.5
    assert job.settings.post_roll_seconds == 1.0
    assert job.settings.speed_adjustment_enabled is True
    assert job.settings.speed == 1.05
    assert job.settings.volume_adjustment_enabled is True
    assert job.settings.volume_percent == 150
    assert job.settings.fade_enabled is True
    assert job.settings.fade_in_seconds == 1.0
    assert job.settings.fade_out_seconds == 1.5
    assert job.settings.black_flash_enabled is True
    assert job.settings.black_flash_duration_seconds == 0.3
    assert job.settings.export_quality_enabled is True
    assert job.settings.quality_preset == "high"
    assert job.settings.resolution_limit == "1080p"
    assert job.clips[0].title == "مقطع"
    assert job.clips[0].exclusions == "00:01:20-00:01:30"
    window.clips_table.item(0, TITLE_COLUMN).setText("تعديل لاحق")
    window.clips_table.item(0, START_COLUMN).setText("00:09:00")
    assert job.clips[0].title == "مقطع"
    assert job.clips[0].start == "00:01:00"
    assert "تم إضافة المهمة إلى قائمة الانتظار" in window.log_area.toPlainText()
    assert "جاري معالجة المهمة في الخلفية" in window.log_area.toPlainText()
    assert "يمكنك تجهيز مهمة أخرى أثناء المعالجة" in window.log_area.toPlainText()
    assert window.start_button.text() == "بدء القص"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_direct_cut_fallback_button_still_uses_direct_processing_path(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"video")
    captured = {}
    window.video_speed_enabled_checkbox.setChecked(True)
    window.volume_enabled_checkbox.setChecked(True)
    window.video_speed_input.setValue(1.25)
    window.volume_input.setValue(200)
    window.project_name_input.setText("قص مباشر")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(video_path))
    window._insert_clip_row(1, "مقطع مباشر", "00:01:00", "00:02:00")

    def fake_start_processing_worker(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(window, "_start_processing_worker", fake_start_processing_worker)
    monkeypatch.setattr(window, "_ask_direct_cut_fallback_confirmation", lambda: True)

    window.direct_cut_button.click()
    app.processEvents()

    assert window.direct_cut_button.text() == "جاري المعالجة..."
    assert captured["project_name"] == "قص مباشر"
    assert captured["source_request"].value == str(video_path)
    assert captured["video_speed"] == 1.25
    assert captured["volume_percent"] == 200
    assert captured["clip_rows"][0].title == "مقطع مباشر"
    assert len(window.job_queue) == 0
    assert window._queue_processing_thread is None
    assert window._queue_processing_worker is None

    window.close()
    app.processEvents()


def test_direct_cut_fallback_cancel_does_not_process(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    direct_calls: list[bool] = []
    monkeypatch.setattr(window, "_ask_direct_cut_fallback_confirmation", lambda: False)
    monkeypatch.setattr(window, "start_processing", lambda: direct_calls.append(True))

    window.direct_cut_button.click()
    app.processEvents()

    assert direct_calls == []
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_add_current_url_work_with_clip_rows() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("درس رابط")
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://youtu.be/abc123")
    window.use_browser_cookies_checkbox.setChecked(True)
    window.browser_combo.setCurrentText("Edge")
    window._insert_clip_row(1, "المقطع", "00:01:00", "00:02:00")

    window.add_current_work_to_queue()

    assert len(window.job_queue) == 1
    job = window.job_queue[0]
    assert job.source_type == QueueVideoSourceType.YOUTUBE
    assert job.source == "https://youtu.be/abc123"
    assert job.title == "درس رابط"
    assert job.settings.use_browser_login is True
    assert job.settings.browser_name == "edge"
    assert len(job.clips) == 1
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط يوتيوب"
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_add_current_facebook_url_work() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://facebook.com/watch/example")
    window._insert_clip_row(1, "المقطع", "00:01:00", "00:02:00")

    window.add_current_work_to_queue()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].source_type == QueueVideoSourceType.FACEBOOK
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط فيسبوك"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_start_cut_youtube_enqueues_and_starts_background_queue(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    direct_calls: list[bool] = []
    queue_worker_calls: list[bool] = []
    window.project_name_input.setText("درس يوتيوب")
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://youtu.be/abc123")
    window.use_browser_cookies_checkbox.setChecked(True)
    window.browser_combo.setCurrentText("Firefox")
    window._insert_clip_row(1, "المقطع", "00:01:00", "00:02:00")
    monkeypatch.setattr(window, "_start_processing_worker", lambda **_kwargs: direct_calls.append(True))
    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda rules: queue_worker_calls.append(len(rules)))

    window.start_button.click()
    app.processEvents()

    assert direct_calls == []
    assert queue_worker_calls == [2]
    assert len(window.job_queue) == 1
    job = window.job_queue[0]
    assert job.source_type == QueueVideoSourceType.YOUTUBE
    assert job.status == JobStatus.QUEUED
    assert job.settings.use_browser_login is True
    assert job.settings.browser_name == "firefox"
    assert AR_URL_QUEUE_PROCESSING_LATER not in job.warnings
    assert "جاري معالجة المهمة في الخلفية" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None
    assert window._queue_processing_thread is None
    assert window._queue_processing_worker is None

    window.close()
    app.processEvents()


def test_queue_add_current_work_empty_clips_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/abc123")

    window._ask_add_current_work_without_clips_confirmation = lambda: False
    window.add_current_work_to_queue()

    assert window.job_queue == []
    assert "لا توجد مقاطع في الجدول" in window.log_area.toPlainText()

    window._ask_add_current_work_without_clips_confirmation = lambda: True
    window.add_current_work_to_queue()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].clip_count == 0
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "0"
    assert "تم إضافة العمل الحالي إلى قائمة الانتظار" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_add_current_work_rejects_missing_or_unsupported_source() -> None:
    app = _app()
    window = MainWindow()

    window.add_current_work_to_queue()

    assert window.job_queue == []
    assert "لا يوجد مصدر فيديو لإضافته" in window.log_area.toPlainText()

    window.youtube_input.setText("https://vimeo.com/123")
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00")
    window.add_current_work_to_queue()

    assert window.job_queue == []
    assert "الرابط غير مدعوم حاليًا" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_local_video_adds_video_job_without_processing() -> None:
    app = _app()
    window = MainWindow()

    job = window._add_queue_local_file_job("C:/videos/lesson.mp4")

    assert job.source_type == QueueVideoSourceType.LOCAL
    assert job.source.replace("\\", "/") == "C:/videos/lesson.mp4"
    assert job.title == "lesson"
    assert job.settings.high_priority is False
    assert window.queue_table.rowCount() == 1
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "فيديو محلي"
    assert window.queue_table.item(0, QUEUE_TITLE_COLUMN).text() == "lesson"
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "0"
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مسودة"
    assert window.queue_table.item(0, QUEUE_HIGH_PRIORITY_COLUMN).checkState() == Qt.Unchecked
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_url_adds_video_job_without_processing() -> None:
    app = _app()
    window = MainWindow()

    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")

    assert job.source_type == QueueVideoSourceType.YOUTUBE
    assert job.source == "https://youtu.be/abc123"
    assert job.title == "درس"
    assert window.queue_table.rowCount() == 1
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط يوتيوب"
    assert window.queue_table.item(0, QUEUE_HIGH_PRIORITY_COLUMN).checkState() == Qt.Unchecked
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_facebook_url_is_created_as_facebook_job() -> None:
    app = _app()
    window = MainWindow()

    job = window._add_queue_url_job("https://facebook.com/watch/example", title="درس")

    assert job.source_type == QueueVideoSourceType.FACEBOOK
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط فيسبوك"
    assert window._processing_thread is None

    window.close()
    app.processEvents()


def test_queue_delete_and_clear_are_passive() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="الأول")
    window._add_queue_url_job("https://youtu.be/def456", title="الثاني")
    window._ask_clear_queue_confirmation = lambda: True

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.delete_selected_queue_job()

    assert len(window.job_queue) == 1
    assert window.queue_table.rowCount() == 1
    assert window.queue_table.item(0, QUEUE_TITLE_COLUMN).text() == "الثاني"

    window.clear_queue()

    assert window.job_queue == []
    assert window.queue_table.rowCount() == 0
    assert window._processing_thread is None
    assert "تم مسح قائمة الانتظار" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_queue_save_current_clip_rows_to_selected_job() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    window._insert_clip_row(1, "المقطع الأول", "00:01:00", "00:02:00", "00:01:20-00:01:30")
    window._insert_clip_row(2, "المقطع الثاني", "00:03:00", "00:04:00", "")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.save_clips_to_selected_queue_job()

    assert len(job.clips) == 2
    assert job.clips[0].title == "المقطع الأول"
    assert job.clips[0].start == "00:01:00"
    assert job.clips[0].end == "00:02:00"
    assert job.clips[0].exclusions == "00:01:20-00:01:30"
    assert job.clips[0].notes == []
    assert job.clips[1].title == "المقطع الثاني"
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "2"
    assert "تم حفظ المقاطع للمهمة المحددة" in window.log_area.toPlainText()
    assert "تم تحديث عدد المقاطع" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_save_clips_without_selection_shows_feedback() -> None:
    app = _app()
    window = MainWindow()
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00")

    window.save_clips_to_selected_queue_job()

    assert "لا توجد مهمة محددة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_save_clips_empty_table_shows_feedback() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.save_clips_to_selected_queue_job()

    assert job.clips == []
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "0"
    assert "لا توجد مقاطع لحفظها" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_save_clips_replacing_existing_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    job.clips = [ClipJob(title="قديم", start="00:00:01", end="00:00:02")]
    window._refresh_queue_job_row(0)
    window._insert_clip_row(1, "جديد", "00:01:00", "00:02:00")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)

    window._ask_replace_queue_clips_confirmation = lambda: False
    window.save_clips_to_selected_queue_job()

    assert [clip.title for clip in job.clips] == ["قديم"]
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"

    window._ask_replace_queue_clips_confirmation = lambda: True
    window.save_clips_to_selected_queue_job()

    assert [clip.title for clip in job.clips] == ["جديد"]
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert "تم حفظ المقاطع للمهمة المحددة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_to_workspace_source_and_clips() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس محفوظ")
    job.clips = [
        ClipJob(title="المقطع", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30")
    ]
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert window.youtube_radio.isChecked()
    assert window.youtube_input.text() == "https://youtu.be/abc123"
    assert window.project_name_input.text() == "درس محفوظ"
    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "المقطع"
    assert window.clips_table.item(0, START_COLUMN).text() == "00:01:00"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:02:00"
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:01:20-00:01:30"
    assert "أنت تعدل مهمة منتظرة من قائمة الانتظار" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_restores_speed_and_volume_intent() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس محفوظ")
    job.settings.speed_adjustment_enabled = True
    job.settings.speed = 1.10
    job.settings.volume_adjustment_enabled = True
    job.settings.volume_percent = 150
    job.settings.pre_roll_seconds = 1.5
    job.settings.post_roll_seconds = 2.0
    job.settings.fade_enabled = True
    job.settings.fade_in_seconds = 1.0
    job.settings.fade_out_seconds = 1.5
    job.settings.black_flash_enabled = True
    job.settings.black_flash_duration_seconds = 0.3
    job.settings.export_quality_enabled = True
    job.settings.quality_preset = "high"
    job.settings.resolution_limit = "1080p"
    job.settings.use_browser_login = True
    job.settings.browser_name = "firefox"
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert window.video_speed_enabled_checkbox.isChecked()
    assert window.video_speed_input.isEnabled()
    assert window.video_speed_input.value() == 1.10
    assert window.volume_enabled_checkbox.isChecked()
    assert window.volume_input.isEnabled()
    assert window.volume_input.value() == 150
    assert window.pre_padding_input.value() == 1.5
    assert window.post_padding_input.value() == 2.0
    assert window.black_fade_enabled_checkbox.isChecked()
    assert window.fade_in_duration_combo.currentText() == "1.00 ثانية"
    assert window.fade_out_duration_combo.currentText() == "1.50 ثانية"
    assert window.black_flash_enabled_checkbox.isChecked()
    assert window.black_flash_duration_combo.currentText() == "0.30 ثانية"
    assert window.export_quality_enabled_checkbox.isChecked()
    assert window.export_quality_preset_combo.currentText() == "جودة عالية"
    assert window.resolution_limit_combo.currentText() == "1080p"
    assert window.use_browser_cookies_checkbox.isChecked()
    assert window.browser_combo.currentText() == "Firefox"

    window.close()
    app.processEvents()


def test_waiting_queue_job_can_be_loaded_edited_and_saved_in_place() -> None:
    app = _app()
    window = MainWindow()
    first = window._add_queue_url_job("https://youtu.be/first", title="الأول")
    second = window._add_queue_url_job("https://youtu.be/second", title="الثاني")
    second.status = JobStatus.QUEUED
    second.settings.high_priority = True
    second.settings.pre_roll_seconds = 0.5
    second.settings.post_roll_seconds = 1.0
    second.settings.speed_adjustment_enabled = True
    second.settings.speed = 1.10
    second.settings.volume_adjustment_enabled = True
    second.settings.volume_percent = 150
    second.settings.fade_enabled = True
    second.settings.fade_in_seconds = 1.0
    second.settings.fade_out_seconds = 1.5
    second.settings.black_flash_enabled = True
    second.settings.black_flash_duration_seconds = 0.3
    second.settings.export_quality_enabled = True
    second.settings.quality_preset = "balanced"
    second.settings.resolution_limit = "1080p"
    second.settings.use_browser_login = True
    second.settings.browser_name = "edge"
    second.clips = [
        ClipJob(title="قديم", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30")
    ]
    window._refresh_queue_job_row(1)

    window.queue_table.setCurrentCell(1, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()

    assert window._editing_queue_job is second
    assert window.youtube_input.text() == "https://youtu.be/second"
    assert window.project_name_input.text() == "الثاني"
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "قديم"
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:01:20-00:01:30"
    assert window.pre_padding_input.value() == 0.5
    assert window.post_padding_input.value() == 1.0
    assert window.video_speed_enabled_checkbox.isChecked()
    assert window.video_speed_input.value() == 1.10
    assert window.volume_enabled_checkbox.isChecked()
    assert window.volume_input.value() == 150
    assert window.black_fade_enabled_checkbox.isChecked()
    assert window.fade_in_duration_combo.currentText() == "1.00 ثانية"
    assert window.fade_out_duration_combo.currentText() == "1.50 ثانية"
    assert window.black_flash_enabled_checkbox.isChecked()
    assert window.black_flash_duration_combo.currentText() == "0.30 ثانية"
    assert window.export_quality_enabled_checkbox.isChecked()
    assert window.export_quality_preset_combo.currentText() == "متوازن"
    assert window.resolution_limit_combo.currentText() == "1080p"
    assert window.use_browser_cookies_checkbox.isChecked()
    assert window.browser_combo.currentText() == "Edge"

    window.youtube_input.setText("https://youtu.be/edited")
    window.project_name_input.setText("الثاني المعدل")
    window.clips_table.item(0, TITLE_COLUMN).setText("جديد")
    window.clips_table.item(0, START_COLUMN).setText("00:03:00")
    window.clips_table.item(0, END_COLUMN).setText("00:04:00")
    window.clips_table.item(0, EXCLUSIONS_COLUMN).setText("00:03:20-00:03:30")
    window.pre_padding_input.setValue(2.0)
    window.post_padding_input.setValue(3.0)
    window.video_speed_input.setValue(1.25)
    window.volume_input.setValue(200)
    window.fade_in_duration_combo.setCurrentText("0.25 ثانية")
    window.fade_out_duration_combo.setCurrentText("2.00 ثانية")
    window.black_flash_duration_combo.setCurrentText("0.50 ثانية")
    window.export_quality_preset_combo.setCurrentText("حجم أصغر")
    window.resolution_limit_combo.setCurrentText("720p")
    window.browser_combo.setCurrentText("Brave")

    assert window.save_waiting_queue_job_edits() is True

    assert window.job_queue == [first, second]
    assert window.job_queue[1] is second
    assert second.source == "https://youtu.be/edited"
    assert second.title == "الثاني المعدل"
    assert second.clips[0].title == "جديد"
    assert second.clips[0].start == "00:03:00"
    assert second.clips[0].exclusions == "00:03:20-00:03:30"
    assert second.settings.high_priority is True
    assert second.settings.pre_roll_seconds == 2.0
    assert second.settings.post_roll_seconds == 3.0
    assert second.settings.speed_adjustment_enabled is True
    assert second.settings.speed == 1.25
    assert second.settings.volume_adjustment_enabled is True
    assert second.settings.volume_percent == 200
    assert second.settings.fade_enabled is True
    assert second.settings.fade_in_seconds == 0.25
    assert second.settings.fade_out_seconds == 2.0
    assert second.settings.black_flash_enabled is True
    assert second.settings.black_flash_duration_seconds == 0.5
    assert second.settings.export_quality_enabled is True
    assert second.settings.quality_preset == "small"
    assert second.settings.resolution_limit == "720p"
    assert second.settings.use_browser_login is True
    assert second.settings.browser_name == "brave"
    assert window.queue_table.item(1, QUEUE_TITLE_COLUMN).text() == "الثاني المعدل"
    assert window.queue_table.item(1, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert window._editing_queue_job is None
    assert "تم حفظ التعديلات على المهمة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_waiting_queue_job_edit_preserves_protected_speed_volume_defaults() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/defaults", title="افتراضي")
    job.clips = [ClipJob(title="مقطع", start="00:01:00", end="00:02:00")]
    job.settings.speed_adjustment_enabled = False
    job.settings.speed = 1.50
    job.settings.volume_adjustment_enabled = False
    job.settings.volume_percent = 200
    job.settings.fade_enabled = False
    job.settings.fade_in_seconds = 2.0
    job.settings.fade_out_seconds = 1.5
    job.settings.black_flash_enabled = False
    job.settings.black_flash_duration_seconds = 0.5
    job.settings.export_quality_enabled = False
    job.settings.quality_preset = "high"
    job.settings.resolution_limit = "720p"
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()

    assert not window.video_speed_enabled_checkbox.isChecked()
    assert not window.video_speed_input.isEnabled()
    assert window.video_speed_input.value() == 1.0
    assert not window.volume_enabled_checkbox.isChecked()
    assert not window.volume_input.isEnabled()
    assert window.volume_input.value() == 100
    assert not window.black_fade_enabled_checkbox.isChecked()
    assert not window.fade_in_duration_combo.isEnabled()
    assert window.fade_in_duration_combo.currentText() == "0.50 ثانية"
    assert window.fade_out_duration_combo.currentText() == "0.50 ثانية"
    assert not window.black_flash_enabled_checkbox.isChecked()
    assert not window.black_flash_duration_combo.isEnabled()
    assert window.black_flash_duration_combo.currentText() == "0.20 ثانية"
    assert not window.export_quality_enabled_checkbox.isChecked()
    assert not window.export_quality_preset_combo.isEnabled()
    assert not window.resolution_limit_combo.isEnabled()
    assert window.export_quality_preset_combo.currentText() == "متوازن"
    assert window.resolution_limit_combo.currentText() == "الأصلية"

    assert window.save_waiting_queue_job_edits() is True

    assert job.settings.speed_adjustment_enabled is False
    assert job.settings.speed == 1.0
    assert job.settings.volume_adjustment_enabled is False
    assert job.settings.volume_percent == 100
    assert job.settings.fade_enabled is False
    assert job.settings.fade_in_seconds == 0.5
    assert job.settings.fade_out_seconds == 0.5
    assert job.settings.black_flash_enabled is False
    assert job.settings.black_flash_duration_seconds == 0.2
    assert job.settings.export_quality_enabled is False
    assert job.settings.quality_preset == "default"
    assert job.settings.resolution_limit == "original"

    window.close()
    app.processEvents()


def test_waiting_queue_job_later_workspace_edits_do_not_mutate_without_saving() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/original", title="أصلي")
    job.clips = [ClipJob(title="قديم", start="00:01:00", end="00:02:00")]
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    window.clips_table.item(0, TITLE_COLUMN).setText("مؤقت")
    window.cancel_waiting_queue_job_edit()
    window.clips_table.item(0, TITLE_COLUMN).setText("تعديل بعد الإلغاء")

    assert job.clips[0].title == "قديم"
    assert job.source == "https://youtu.be/original"
    assert job.title == "أصلي"
    assert window._editing_queue_job is None
    assert "تم إلغاء تعديل المهمة" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_running_and_completed_queue_jobs_cannot_be_edited() -> None:
    app = _app()
    window = MainWindow()
    running = window._add_queue_url_job("https://youtu.be/running", title="جارية")
    running.status = JobStatus.CUTTING
    done = window._add_queue_url_job("https://youtu.be/done", title="مكتملة")
    done.status = JobStatus.DONE
    window._refresh_queue_job_row(0)
    window._refresh_queue_job_row(1)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    assert "لا يمكن تعديل المهمة الجارية" in window.log_area.toPlainText()
    assert window._editing_queue_job is None

    window.queue_table.setCurrentCell(1, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    assert "لا يمكن تعديل مهمة مكتملة. أعد إضافتها كمهمة جديدة." in window.log_area.toPlainText()
    assert window._editing_queue_job is None

    window.close()
    app.processEvents()


def test_saving_waiting_job_is_blocked_if_it_starts_running_during_edit() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/job", title="مهمة")
    job.clips = [ClipJob(title="قديم", start="00:01:00", end="00:02:00")]
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    window.clips_table.item(0, TITLE_COLUMN).setText("جديد")
    job.status = JobStatus.DOWNLOADING
    window._refresh_queue_job_row(0)

    assert not window.save_queue_job_edits_button.isEnabled()
    assert window.save_waiting_queue_job_edits() is False
    assert job.clips[0].title == "قديم"
    assert "لا يمكن تعديل المهمة بعد بدء معالجتها" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_start_cut_during_waiting_job_edit_saves_instead_of_duplicate(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    started: list[bool] = []
    job = window._add_queue_url_job("https://youtu.be/original", title="أصلي")
    job.clips = [ClipJob(title="قديم", start="00:01:00", end="00:02:00")]
    window._refresh_queue_job_row(0)
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    window.youtube_input.setText("https://youtu.be/edited")
    window.project_name_input.setText("معدل")
    window.clips_table.item(0, TITLE_COLUMN).setText("جديد")
    monkeypatch.setattr(window, "_ask_save_waiting_job_edit_instead_confirmation", lambda: True)
    monkeypatch.setattr(window, "start_queue_processing", lambda: started.append(True))

    window.start_button.click()

    assert len(window.job_queue) == 1
    assert window.job_queue[0] is job
    assert job.source == "https://youtu.be/edited"
    assert job.title == "معدل"
    assert job.clips[0].title == "جديد"
    assert started == [True]
    assert window._editing_queue_job is None

    window.close()
    app.processEvents()


def test_start_cut_during_waiting_job_edit_can_cancel_without_duplicate(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    started: list[bool] = []
    job = window._add_queue_url_job("https://youtu.be/original", title="أصلي")
    job.clips = [ClipJob(title="قديم", start="00:01:00", end="00:02:00")]
    window._refresh_queue_job_row(0)
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.edit_waiting_queue_job()
    window.youtube_input.setText("https://youtu.be/edited")
    window.clips_table.item(0, TITLE_COLUMN).setText("جديد")
    monkeypatch.setattr(window, "_ask_save_waiting_job_edit_instead_confirmation", lambda: False)
    monkeypatch.setattr(window, "start_queue_processing", lambda: started.append(True))

    window.start_button.click()

    assert len(window.job_queue) == 1
    assert job.source == "https://youtu.be/original"
    assert job.clips[0].title == "قديم"
    assert started == []
    assert window._editing_queue_job is job
    assert "لم يتم إنشاء مهمة جديدة" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_queue_load_selected_local_job_to_workspace_source() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_job(
        QueueVideoSourceType.LOCAL,
        "C:/videos/lesson.mp4",
        "درس محلي",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
    )

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert job.source_type == QueueVideoSourceType.LOCAL
    assert window.local_file_radio.isChecked()
    assert window.local_file_input.text().replace("\\", "/") == "C:/videos/lesson.mp4"
    assert window.project_name_input.text() == "درس محلي"
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "مقطع"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_facebook_job_to_workspace_source() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_job(
        QueueVideoSourceType.FACEBOOK,
        "https://facebook.com/watch/example",
        "درس Facebook",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
    )

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert window.youtube_radio.isChecked()
    assert window.youtube_input.text() == "https://facebook.com/watch/example"
    assert window.project_name_input.text() == "درس Facebook"
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "مقطع"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_without_selection_or_source_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.load_selected_queue_job_to_workspace()

    assert "لا توجد مهمة محددة" in window.log_area.toPlainText()

    window._add_queue_job(QueueVideoSourceType.YOUTUBE, "", "بدون مصدر")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert "لا يوجد مصدر محفوظ لهذه المهمة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_without_saved_clips_loads_source_only() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="درس بلا مقاطع")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_selected_queue_job_to_workspace()

    assert window.youtube_input.text() == "https://youtu.be/abc123"
    assert window.project_name_input.text() == "درس بلا مقاطع"
    assert window.clips_table.rowCount() == 0
    assert "لا توجد مقاطع محفوظة لهذه المهمة" in window.log_area.toPlainText()
    assert "أنت تعدل مهمة منتظرة من قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_source_replacement_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/current")
    window._add_queue_url_job("https://youtu.be/saved", title="درس")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)

    window._ask_replace_workspace_source_confirmation = lambda: False
    window.load_selected_queue_job_to_workspace()

    assert window.youtube_input.text() == "https://youtu.be/current"

    window._ask_replace_workspace_source_confirmation = lambda: True
    window.load_selected_queue_job_to_workspace()

    assert window.youtube_input.text() == "https://youtu.be/saved"
    assert "تم استبدال مصدر الفيديو الحالي" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_selected_job_clip_table_replacement_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/saved")
    job = window._add_queue_url_job("https://youtu.be/saved", title="درس")
    job.clips = [ClipJob(title="محفوظ", start="00:01:00", end="00:02:00")]
    window._insert_clip_row(1, "حالي", "00:03:00", "00:04:00")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)

    window._ask_replace_current_clip_table_confirmation = lambda: False
    window.load_selected_queue_job_to_workspace()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "حالي"

    window._ask_replace_current_clip_table_confirmation = lambda: True
    window.load_selected_queue_job_to_workspace()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "محفوظ"
    assert "تم استبدال مقاطع الجدول" in window.log_area.toPlainText()
    assert "أنت تعدل مهمة منتظرة من قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_saved_clip_rows_into_current_table() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    job.clips = [
        ClipJob(title="الأول", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30"),
        ClipJob(title="الثاني", start="00:03:00", end="00:04:00"),
    ]
    window._refresh_queue_job_row(0)

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_clips_from_selected_queue_job()

    assert window.clips_table.rowCount() == 2
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "الأول"
    assert window.clips_table.item(0, START_COLUMN).text() == "00:01:00"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:02:00"
    assert window.clips_table.item(0, EXCLUSIONS_COLUMN).text() == "00:01:20-00:01:30"
    assert window.clips_table.item(1, TITLE_COLUMN).text() == "الثاني"
    assert "تم تحميل مقاطع المهمة المحددة" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_saved_clips_without_selection_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.load_clips_from_selected_queue_job()

    assert "لا توجد مهمة محددة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_saved_clips_empty_job_shows_feedback() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="درس")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.load_clips_from_selected_queue_job()

    assert window.clips_table.rowCount() == 0
    assert "لا توجد مقاطع محفوظة لهذه المهمة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_saved_clips_replacing_table_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    job.clips = [ClipJob(title="محفوظ", start="00:01:00", end="00:02:00")]
    window._insert_clip_row(1, "حالي", "00:03:00", "00:04:00")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)

    window._ask_replace_current_clip_table_confirmation = lambda: False
    window.load_clips_from_selected_queue_job()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "حالي"

    window._ask_replace_current_clip_table_confirmation = lambda: True
    window.load_clips_from_selected_queue_job()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "محفوظ"
    assert "تم استبدال مقاطع الجدول" in window.log_area.toPlainText()
    assert "تم تحميل مقاطع المهمة المحددة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_save_state_with_empty_queue_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.save_queue_state()

    assert "لا توجد مهام لحفظها" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_save_and_load_state_roundtrip(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    file_path = tmp_path / "queue.json"
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    window._insert_clip_row(1, "المقطع", "00:01:00", "00:02:00", "00:01:20-00:01:30")
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.save_clips_to_selected_queue_job()
    job.settings.high_priority = True
    window._refresh_queue_job_row(0)

    monkeypatch.setattr(
        "src.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(file_path), "JSON Files (*.json)"),
    )
    window.save_queue_state()

    assert file_path.exists()
    assert "تم حفظ قائمة الانتظار" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()

    window.job_queue.clear()
    window.queue_table.setRowCount(0)
    monkeypatch.setattr(
        "src.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(file_path), "JSON Files (*.json)"),
    )
    window.load_queue_state()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].title == "درس"
    assert window.job_queue[0].settings.high_priority is True
    assert window.job_queue[0].clips[0].title == "المقطع"
    assert window.job_queue[0].clips[0].exclusions == "00:01:20-00:01:30"
    assert window.queue_table.rowCount() == 1
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert "تم تحميل قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_state_existing_queue_requires_confirmation(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    file_path = tmp_path / "queue.json"
    window._add_queue_url_job("https://youtu.be/current", title="حالي")

    second_window = MainWindow()
    second_window._add_queue_url_job("https://youtu.be/saved", title="محفوظ")
    monkeypatch.setattr(
        "src.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(file_path), "JSON Files (*.json)"),
    )
    second_window.save_queue_state()
    second_window.close()

    monkeypatch.setattr(
        "src.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(file_path), "JSON Files (*.json)"),
    )
    window._ask_replace_queue_state_confirmation = lambda: False
    window.load_queue_state()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].title == "حالي"

    window._ask_replace_queue_state_confirmation = lambda: True
    window.load_queue_state()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].title == "محفوظ"
    assert "تم تحميل قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_load_invalid_state_file_shows_error(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    file_path = tmp_path / "bad.json"
    file_path.write_text("{bad", encoding="utf-8")

    monkeypatch.setattr(
        "src.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(file_path), "JSON Files (*.json)"),
    )
    window.load_queue_state()

    assert "فشل تحميل قائمة الانتظار" in window.log_area.toPlainText()
    assert window.job_queue == []
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_empty_queue_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.validate_all_queue_jobs()

    assert "لا توجد مهام في قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_one_valid_local_job(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_local_file_job(str(video_path))

    window.validate_all_queue_jobs()

    assert job.status == JobStatus.READY
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "جاهز"
    assert "تم فحص قائمة الانتظار بالكامل" in window.log_area.toPlainText()
    assert "عدد المهام: 1" in window.log_area.toPlainText()
    assert "المهام الجاهزة: 1" in window.log_area.toPlainText()
    assert "المهام التي فيها تحذيرات: 0" in window.log_area.toPlainText()
    assert "المهام التي فيها أخطاء: 0" in window.log_area.toPlainText()
    assert "يمكن تشغيل القائمة لاحقًا" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_one_missing_local_file_job(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    missing_path = tmp_path / "missing.mp4"
    job = window._add_queue_local_file_job(str(missing_path))

    window.validate_all_queue_jobs()

    assert job.status == JobStatus.VALIDATION_ERROR
    assert "لم يتم العثور على الملف" in job.errors
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "خطأ في الفحص"
    assert "المهام التي فيها أخطاء: 1" in window.log_area.toPlainText()
    assert "1 - missing: لا يمكن بدء المهمة قبل إصلاح الأخطاء" in window.log_area.toPlainText()
    assert "لا يمكن تشغيل القائمة قبل إصلاح الأخطاء" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_one_valid_youtube_job() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")

    window.validate_all_queue_jobs()

    assert job.status == JobStatus.READY
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "جاهز"
    assert "المهام الجاهزة: 1" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_one_unsupported_url_job() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://vimeo.com/123", title="غير مدعوم")

    window.validate_all_queue_jobs()

    assert job.status == JobStatus.VALIDATION_ERROR
    assert "رابط يوتيوب غير صالح" in job.errors
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "خطأ في الفحص"
    assert "المهام التي فيها أخطاء: 1" in window.log_area.toPlainText()
    assert "1 - غير مدعوم: لا يمكن بدء المهمة قبل إصلاح الأخطاء" in window.log_area.toPlainText()
    assert "لا يمكن تشغيل القائمة قبل إصلاح الأخطاء" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_all_mixed_jobs_updates_statuses(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    window._add_queue_local_file_job(str(video_path))
    window._add_queue_url_job("https://youtu.be/abc123", title="يوتيوب")
    window._add_queue_url_job("https://vimeo.com/123", title="غير مدعوم")

    window.validate_all_queue_jobs_button.click()
    app.processEvents()

    assert [job.status for job in window.job_queue] == [
        JobStatus.READY,
        JobStatus.READY,
        JobStatus.VALIDATION_ERROR,
    ]
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "جاهز"
    assert window.queue_table.item(1, QUEUE_STATUS_COLUMN).text() == "جاهز"
    assert window.queue_table.item(2, QUEUE_STATUS_COLUMN).text() == "خطأ في الفحص"
    assert "عدد المهام: 3" in window.log_area.toPlainText()
    assert "المهام الجاهزة: 2" in window.log_area.toPlainText()
    assert "المهام التي فيها أخطاء: 1" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_selected_only_is_passive() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="درس")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.run_selected_queue_job()

    assert "تشغيل قائمة الانتظار سيتم تفعيله في مرحلة لاحقة" in window.log_area.toPlainText()
    assert "تم تشغيل المحاكاة فقط" in window.log_area.toPlainText()
    assert "لم يتم تنزيل أي فيديو" in window.log_area.toPlainText()
    assert "لم يتم قص أي مقطع" in window.log_area.toPlainText()
    assert "عدد المهام: 1" in window.log_area.toPlainText()
    assert "المهام التي تمت محاكاتها: 1" in window.log_area.toPlainText()
    assert "المهام التي تم تخطيها: 0" in window.log_area.toPlainText()
    assert "الأخطاء إن وجدت: 0" in window.log_area.toPlainText()
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتملة"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_selected_ready_job_simulates_only(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_local_file_job(str(video_path))

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.validate_selected_queue_job()
    window.log_area.clear()
    window.run_selected_queue_job()

    assert job.status == JobStatus.DONE
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتملة"
    assert "تم تشغيل المحاكاة فقط" in window.log_area.toPlainText()
    assert "لم يتم تنزيل أي فيديو" in window.log_area.toPlainText()
    assert "لم يتم قص أي مقطع" in window.log_area.toPlainText()
    assert "المهام التي تمت محاكاتها: 1" in window.log_area.toPlainText()
    assert "المهام التي تم تخطيها: 0" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_selected_without_selection_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.run_selected_queue_job()

    assert "لا توجد مهمة محددة" in window.log_area.toPlainText()
    assert window._processing_thread is None

    window.close()
    app.processEvents()


def test_queue_run_selected_validation_error_job_is_skipped() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://vimeo.com/123", title="غير مدعوم")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.validate_selected_queue_job()
    window.log_area.clear()
    window.run_selected_queue_job()

    assert job.status == JobStatus.SKIPPED
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "تم تجاوزه"
    assert "تم تخطي المهمة بسبب أخطاء" in window.log_area.toPlainText()
    assert "المهام التي تمت محاكاتها: 0" in window.log_area.toPlainText()
    assert "المهام التي تم تخطيها: 1" in window.log_area.toPlainText()
    assert "الأخطاء إن وجدت: 1" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_all_simulation_empty_queue_shows_feedback() -> None:
    app = _app()
    window = MainWindow()

    window.run_all_queue_simulation()

    assert "لا توجد مهام في قائمة الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_all_simulation_one_ready_job(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_local_file_job(str(video_path))

    window.validate_all_queue_jobs()
    window.log_area.clear()
    window.run_all_queue_simulation()

    assert job.status == JobStatus.DONE
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتملة"
    assert "تم تشغيل المحاكاة فقط" in window.log_area.toPlainText()
    assert "لم يتم تنزيل أي فيديو" in window.log_area.toPlainText()
    assert "لم يتم قص أي مقطع" in window.log_area.toPlainText()
    assert "عدد المهام: 1" in window.log_area.toPlainText()
    assert "تمت محاكاتها: 1" in window.log_area.toPlainText()
    assert "تم تخطيها: 0" in window.log_area.toPlainText()
    assert "فيها أخطاء: 0" in window.log_area.toPlainText()
    assert "فيها تحذيرات: 0" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_run_all_simulation_multiple_jobs_with_warning_and_error(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    ready_job = window._add_queue_local_file_job(str(video_path))
    warning_job = window._add_queue_url_job("https://youtu.be/" + ("a" * 230), title="رابط طويل")
    error_job = window._add_queue_url_job("https://vimeo.com/123", title="غير مدعوم")

    window.validate_all_queue_jobs()
    window.log_area.clear()
    window.run_all_queue_simulation_button.click()
    app.processEvents()

    assert [ready_job.status, warning_job.status, error_job.status] == [
        JobStatus.DONE,
        JobStatus.DONE,
        JobStatus.SKIPPED,
    ]
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتملة"
    assert window.queue_table.item(1, QUEUE_STATUS_COLUMN).text() == "مكتملة"
    assert window.queue_table.item(2, QUEUE_STATUS_COLUMN).text() == "تم تجاوزه"
    assert "تم تشغيل المحاكاة فقط" in window.log_area.toPlainText()
    assert "لم يتم تنزيل أي فيديو" in window.log_area.toPlainText()
    assert "لم يتم قص أي مقطع" in window.log_area.toPlainText()
    assert "تم تخطي المهمة بسبب أخطاء: غير مدعوم" in window.log_area.toPlainText()
    assert "عدد المهام: 3" in window.log_area.toPlainText()
    assert "تمت محاكاتها: 2" in window.log_area.toPlainText()
    assert "تم تخطيها: 1" in window.log_area.toPlainText()
    assert "فيها أخطاء: 1" in window.log_area.toPlainText()
    assert "فيها تحذيرات: 1" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_start_processing_prepares_local_job_without_direct_worker(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_job(
        QueueVideoSourceType.LOCAL,
        str(video_path),
        "درس محلي",
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:04")],
    )
    started: list[int] = []

    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda rules: started.append(len(rules)))

    window.start_queue_processing()

    assert started == [2]
    assert job.status == JobStatus.QUEUED
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "في الانتظار"
    assert "جاري معالجة المهمة في الخلفية" in window.log_area.toPlainText()
    assert "يمكنك تجهيز مهمة أخرى أثناء المعالجة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None
    assert window._queue_processing_thread is None

    window.close()
    app.processEvents()


def test_queue_start_processing_leaves_facebook_jobs_queued_without_processing() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_job(
        QueueVideoSourceType.FACEBOOK,
        "https://facebook.com/watch/example",
        "درس رابط",
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:04")],
    )

    window.start_queue_processing()

    assert job.status == JobStatus.QUEUED
    assert AR_URL_QUEUE_PROCESSING_LATER in job.warnings
    assert AR_URL_QUEUE_PROCESSING_LATER in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None
    assert window._queue_processing_thread is None

    window.close()
    app.processEvents()


def test_queue_start_processing_marks_job_without_clips_as_validation_error(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_local_file_job(str(video_path))

    window.start_queue_processing()

    assert job.status == JobStatus.VALIDATION_ERROR
    assert "لا توجد مقاطع محفوظة لهذه المهمة" in job.errors
    assert window._queue_processing_thread is None

    window.close()
    app.processEvents()


def test_queue_start_processing_while_running_does_not_start_second_worker(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    start_calls: list[bool] = []
    window._queue_processing_thread = object()
    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda rules: start_calls.append(True))

    window.start_queue_processing()

    assert start_calls == []
    assert "المهمة في الانتظار" in window.log_area.toPlainText()
    assert "يمكنك تجهيز مهمة أخرى أثناء المعالجة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window._queue_processing_thread = None
    window.close()
    app.processEvents()


def test_queue_processing_keeps_preparation_ui_available_while_running() -> None:
    app = _app()
    window = MainWindow()
    window.local_file_radio.setChecked(True)
    window._update_source_inputs()

    window._set_queue_processing_controls_running(True)

    assert window.local_file_input.isEnabled()
    assert window.browse_button.isEnabled()
    assert window.paste_message_input.isEnabled()
    assert window.smart_paste_button.isEnabled()
    assert window.parse_message_button.parent() is None
    assert window.clips_table.isEnabled()
    assert window.add_row_button.isEnabled()
    assert window.delete_row_button.isEnabled()
    assert window.clear_table_button.isEnabled()
    assert window.import_excel_button.isEnabled()
    assert window.classification_rules_table.isEnabled()
    assert window.pre_padding_input.isEnabled()
    assert window.post_padding_input.isEnabled()
    assert window.video_speed_enabled_checkbox.isEnabled()
    assert not window.video_speed_input.isEnabled()
    assert window.reset_video_speed_button.isEnabled()
    assert window.volume_enabled_checkbox.isEnabled()
    assert not window.volume_input.isEnabled()
    assert window.reset_volume_button.isEnabled()
    assert window.black_fade_enabled_checkbox.isEnabled()
    assert not window.fade_in_duration_combo.isEnabled()
    assert not window.fade_out_duration_combo.isEnabled()
    assert window.black_flash_enabled_checkbox.isEnabled()
    assert not window.black_flash_duration_combo.isEnabled()
    assert window.add_current_work_to_queue_button.isEnabled()
    assert window.add_queue_local_video_button.isEnabled()
    assert window.add_queue_url_button.isEnabled()
    assert window.add_and_run_queue_job_button.isEnabled()
    assert window.start_button.isEnabled()
    assert window.new_work_button.isEnabled()
    assert window.queue_table.isEnabled()
    assert window.log_area.isEnabled()
    assert not window.direct_cut_button.isEnabled()
    assert not window.start_queue_processing_button.isEnabled()
    assert not window.run_selected_queue_job_button.isEnabled()
    assert window.validate_queue_job_button.isEnabled()
    assert window.validate_all_queue_jobs_button.isEnabled()
    assert window.save_queue_clips_button.isEnabled()
    assert window.load_queue_clips_button.isEnabled()
    assert not window.load_queue_job_workspace_button.isEnabled()
    assert not window.save_queue_job_edits_button.isEnabled()
    assert not window.cancel_queue_job_edit_button.isEnabled()
    assert window.save_queue_state_button.isEnabled()
    assert window.load_queue_state_button.isEnabled()
    assert window.delete_queue_job_button.isEnabled()
    assert window.clear_queue_button.isEnabled()
    assert window.stop_queue_after_current_button.isEnabled()
    enabled_sections = {
        group.title()
        for group in window.findChildren(QGroupBox)
        if group.title()
    }
    assert {
        "مصدر الفيديو",
        "الصق الرسالة هنا",
        "جدول المقاطع",
        "إعدادات القص",
        "قائمة الانتظار",
        "سجل الحالة",
    }.issubset(enabled_sections)
    for group in window.findChildren(QGroupBox):
        if group.title() in enabled_sections:
            assert group.isEnabled()

    window._set_queue_processing_controls_running(False)
    assert window.start_button.isEnabled()
    assert window.direct_cut_button.isEnabled()
    assert window.start_queue_processing_button.isEnabled()
    assert not window.stop_queue_after_current_button.isEnabled()

    window.close()
    app.processEvents()


def test_simple_conversion_button_is_hidden_from_main_workflow() -> None:
    app = _app()
    window = MainWindow()
    window.show()
    app.processEvents()

    assert window.smart_paste_button.isVisible()
    assert window.smart_paste_button.isEnabled()
    assert not window.parse_message_button.isVisible()
    assert window.parse_message_button.parent() is None

    window.close()
    app.processEvents()


def test_direct_processing_is_blocked_while_queue_worker_active(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    start_calls: list[bool] = []
    window._queue_processing_thread = object()
    monkeypatch.setattr(window, "_start_processing_worker", lambda **kwargs: start_calls.append(True))

    window.start_processing()

    assert start_calls == []
    assert window._processing_thread is None
    assert window._processing_worker is None
    assert "جاري معالجة المهمة في الخلفية" in window.log_area.toPlainText()
    assert "يمكنك تجهيز مهمة أخرى أثناء المعالجة" in window.log_area.toPlainText()

    window._queue_processing_thread = None
    window.close()
    app.processEvents()


def test_queue_processing_invokes_video_processor_off_ui_thread(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    worker_thread_is_ui: list[bool] = []
    job = window._add_queue_job(
        QueueVideoSourceType.LOCAL,
        str(video_path),
        "درس محلي",
        clips=[ClipJob(title="مقطع", start="00:00:01", end="00:00:04")],
        status=JobStatus.QUEUED,
    )

    class FakeVideoProcessor:
        def process_project(self, *args, **kwargs):
            worker_thread_is_ui.append(QThread.currentThread() == app.thread())
            return SimpleNamespace(project_output_folder=tmp_path / "output")

    window.video_processor = FakeVideoProcessor()

    window.start_queue_processing()

    assert _process_events_until(app, lambda: window._queue_processing_thread is None)
    assert worker_thread_is_ui == [False]
    assert job.status == JobStatus.DONE
    assert not window.stop_queue_after_current_button.isEnabled()

    window.close()
    app.processEvents()


def test_queue_processing_worker_processes_multiple_local_jobs_in_order() -> None:
    calls: list[str] = []
    first = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/first.mp4",
        title="الأول",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    second = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/second.mp4",
        title="الثاني",
        clips=[ClipJob(title="مقطع", start="00:03:00", end="00:04:00")],
        status=JobStatus.QUEUED,
    )

    class FakeVideoProcessor:
        def process_project(self, _source_request, project_name, _clip_rows, **_kwargs):
            calls.append(project_name)
            return SimpleNamespace(project_output_folder=Path(f"C:/output/{project_name}"))

    worker = QueueProcessingWorker([first, second], FakeVideoProcessor(), [])
    worker.run()

    assert calls == ["الأول", "الثاني"]
    assert [first.status, second.status] == [JobStatus.DONE, JobStatus.DONE]


def test_start_cut_while_running_keeps_new_job_queued(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    start_calls: list[bool] = []
    window._queue_processing_thread = object()
    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda _rules: start_calls.append(True))
    window.project_name_input.setText("مشروع جديد")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText("C:/videos/next.mp4")
    window._insert_clip_row(1, "مقطع جديد", "00:01:00", "00:02:00")

    window.start_button.click()

    assert len(window.job_queue) == 1
    assert window.job_queue[0].status == JobStatus.QUEUED
    assert window.job_queue[0].clips[0].title == "مقطع جديد"
    assert start_calls == []
    assert "تم إضافة المهمة إلى قائمة الانتظار" in window.log_area.toPlainText()
    assert "المهمة في الانتظار" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window._queue_processing_thread = None
    window.close()
    app.processEvents()


def test_queue_auto_continues_with_job_added_while_worker_was_running(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "next.mp4"
    video_path.write_bytes(b"ok")
    started: list[int] = []
    monkeypatch.setattr(window, "_start_queue_processing_worker", lambda rules: started.append(len(rules)))

    window._queue_processing_thread = object()
    window.project_name_input.setText("مشروع جديد")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(video_path))
    window._insert_clip_row(1, "مقطع جديد", "00:01:00", "00:02:00")

    window.add_current_work_and_start_queue()

    assert started == []
    assert len(window.job_queue) == 1
    assert window.job_queue[0].status == JobStatus.QUEUED
    assert "المهمة في الانتظار" in window.log_area.toPlainText()

    window._queue_processing_thread = None
    window._queue_auto_continue_after_worker = True
    window._continue_queue_processing_if_needed()

    assert started == [2]
    assert window.job_queue[0].status == JobStatus.QUEUED
    assert AR_QUEUE_NEXT_JOB_STARTED in window.log_area.toPlainText()
    assert "جاري معالجة المهمة في الخلفية" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window._set_queue_processing_controls_running(False)
    window.close()
    app.processEvents()


def test_queue_processing_worker_processes_one_local_job_with_snapshot() -> None:
    app = _app()
    calls: list[dict] = []
    job = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30")],
        status=JobStatus.QUEUED,
    )
    job.settings.pre_roll_seconds = 1.0
    job.settings.post_roll_seconds = 2.0
    job.settings.speed_adjustment_enabled = True
    job.settings.speed = 1.10
    job.settings.volume_adjustment_enabled = True
    job.settings.volume_percent = 150
    job.settings.fade_enabled = True
    job.settings.fade_in_seconds = 1.0
    job.settings.fade_out_seconds = 1.5
    job.settings.black_flash_enabled = True
    job.settings.black_flash_duration_seconds = 0.3

    class FakeVideoProcessor:
        def process_project(self, source_request, project_name, clip_rows, **kwargs):
            calls.append(
                {
                    "source_request": source_request,
                    "project_name": project_name,
                    "clip_rows": clip_rows,
                    "clip_padding": kwargs["clip_padding"],
                    "video_speed": kwargs["video_speed"],
                    "volume_percent": kwargs["volume_percent"],
                    "clip_fade": kwargs["clip_fade"],
                    "clip_black_flash": kwargs["clip_black_flash"],
                }
            )
            return SimpleNamespace(project_output_folder=Path("C:/output/lesson"))

    worker = QueueProcessingWorker([job], FakeVideoProcessor(), [])
    worker.run()

    assert job.status == JobStatus.DONE
    assert len(calls) == 1
    assert calls[0]["project_name"] == "درس"
    assert calls[0]["clip_rows"][0].title == "مقطع"
    assert calls[0]["clip_rows"][0].exclusions == "00:01:20-00:01:30"
    assert calls[0]["clip_padding"].pre_seconds == 1.0
    assert calls[0]["clip_padding"].post_seconds == 2.0
    assert calls[0]["video_speed"] == 1.1
    assert calls[0]["volume_percent"] == 150
    assert calls[0]["clip_fade"].enabled is True
    assert calls[0]["clip_fade"].fade_in_seconds == 1.0
    assert calls[0]["clip_fade"].fade_out_seconds == 1.5
    assert calls[0]["clip_black_flash"].enabled is True
    assert calls[0]["clip_black_flash"].duration_seconds == 0.3
    assert app is not None


def test_queue_processing_worker_uses_default_speed_and_volume_when_adjustments_disabled() -> None:
    calls: list[dict] = []
    job = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    job.settings.speed = 1.25
    job.settings.volume_percent = 150
    job.settings.fade_enabled = False
    job.settings.fade_in_seconds = 2.0
    job.settings.fade_out_seconds = 2.0
    job.settings.black_flash_enabled = False
    job.settings.black_flash_duration_seconds = 0.5

    class FakeVideoProcessor:
        def process_project(self, _source_request, _project_name, _clip_rows, **kwargs):
            calls.append(
                {
                    "video_speed": kwargs["video_speed"],
                    "volume_percent": kwargs["volume_percent"],
                    "clip_fade": kwargs["clip_fade"],
                    "clip_black_flash": kwargs["clip_black_flash"],
                }
            )
            return SimpleNamespace(project_output_folder=Path("C:/output/lesson"))

    worker = QueueProcessingWorker([job], FakeVideoProcessor(), [])
    worker.run()

    assert calls[0]["video_speed"] == 1.0
    assert calls[0]["volume_percent"] == 100
    assert calls[0]["clip_fade"].enabled is False
    assert calls[0]["clip_black_flash"].enabled is False


def test_queue_processing_worker_passes_export_quality_snapshot_and_logs_when_enabled() -> None:
    calls: list[dict] = []
    job = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    job.settings.export_quality_enabled = True
    job.settings.quality_preset = "small"
    job.settings.resolution_limit = "720p"

    class FakeVideoProcessor:
        def process_project(self, _source_request, _project_name, _clip_rows, **kwargs):
            calls.append({"export_quality": kwargs["export_quality"]})
            kwargs["progress_callback"](AR_EXPORT_QUALITY_APPLIED)
            return SimpleNamespace(project_output_folder=Path("C:/output/lesson"))

    worker = QueueProcessingWorker([job], FakeVideoProcessor(), [])
    worker.run()

    assert calls[0]["export_quality"].enabled is True
    assert calls[0]["export_quality"].quality_preset == "small"
    assert calls[0]["export_quality"].resolution_limit == "720p"
    assert AR_EXPORT_QUALITY_APPLIED in job.log_messages


def test_queue_processing_worker_uses_default_export_quality_when_disabled() -> None:
    calls: list[dict] = []
    job = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="درس",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    job.settings.quality_preset = "high"
    job.settings.resolution_limit = "720p"

    class FakeVideoProcessor:
        def process_project(self, _source_request, _project_name, _clip_rows, **kwargs):
            calls.append({"export_quality": kwargs["export_quality"]})
            return SimpleNamespace(project_output_folder=Path("C:/output/lesson"))

    worker = QueueProcessingWorker([job], FakeVideoProcessor(), [])
    worker.run()

    assert calls[0]["export_quality"].enabled is False
    assert calls[0]["export_quality"].quality_preset == "default"
    assert calls[0]["export_quality"].resolution_limit == "original"


def test_queue_processing_worker_processes_youtube_job_with_cookie_snapshot() -> None:
    calls: list[dict] = []
    progress_messages: list[str] = []
    job = VideoJob(
        source_type=QueueVideoSourceType.YOUTUBE,
        source="https://youtu.be/abc123",
        title="درس يوتيوب",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00", exclusions="00:01:20-00:01:30")],
        status=JobStatus.QUEUED,
    )
    job.settings.pre_roll_seconds = 0.5
    job.settings.post_roll_seconds = 1.0
    job.settings.speed_adjustment_enabled = True
    job.settings.speed = 1.05
    job.settings.volume_adjustment_enabled = True
    job.settings.volume_percent = 125
    job.settings.fade_enabled = True
    job.settings.fade_in_seconds = 0.25
    job.settings.fade_out_seconds = 2.0
    job.settings.black_flash_enabled = True
    job.settings.black_flash_duration_seconds = 0.5
    job.settings.use_browser_login = True
    job.settings.browser_name = "brave"

    class FakeVideoProcessor:
        def process_project(self, source_request, project_name, clip_rows, **kwargs):
            calls.append(
                {
                    "source_request": source_request,
                    "project_name": project_name,
                    "clip_rows": clip_rows,
                    "clip_padding": kwargs["clip_padding"],
                    "video_speed": kwargs["video_speed"],
                    "volume_percent": kwargs["volume_percent"],
                    "clip_fade": kwargs["clip_fade"],
                    "clip_black_flash": kwargs["clip_black_flash"],
                }
            )
            kwargs["progress_callback"]("تم تنزيل الفيديو")
            kwargs["progress_callback"](AR_BLACK_FLASH_APPLIED)
            return SimpleNamespace(project_output_folder=Path("C:/output/youtube"))

    worker = QueueProcessingWorker([job], FakeVideoProcessor(), [])
    worker.progress.connect(progress_messages.append)
    worker.run()

    assert job.status == JobStatus.DONE
    assert len(calls) == 1
    assert calls[0]["source_request"].source_type.value == "youtube"
    assert calls[0]["source_request"].value == "https://youtu.be/abc123"
    assert calls[0]["source_request"].use_browser_cookies is True
    assert calls[0]["source_request"].browser == "brave"
    assert calls[0]["project_name"] == "درس يوتيوب"
    assert calls[0]["clip_rows"][0].exclusions == "00:01:20-00:01:30"
    assert calls[0]["clip_padding"].pre_seconds == 0.5
    assert calls[0]["clip_padding"].post_seconds == 1.0
    assert calls[0]["video_speed"] == 1.05
    assert calls[0]["volume_percent"] == 125
    assert calls[0]["clip_fade"].enabled is True
    assert calls[0]["clip_fade"].fade_in_seconds == 0.25
    assert calls[0]["clip_fade"].fade_out_seconds == 2.0
    assert calls[0]["clip_black_flash"].enabled is True
    assert calls[0]["clip_black_flash"].duration_seconds == 0.5
    assert AR_BLACK_FLASH_APPLIED in job.log_messages
    assert "جاري تحميل الفيديو في الخلفية" in progress_messages
    assert "جاري قص المقاطع في الخلفية" in progress_messages
    assert not any("cookie" in message.lower() for message in progress_messages)


def test_queue_processing_worker_auto_runs_local_job_after_youtube_job() -> None:
    calls: list[str] = []
    youtube_job = VideoJob(
        source_type=QueueVideoSourceType.YOUTUBE,
        source="https://youtu.be/abc123",
        title="يوتيوب",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    local_job = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="محلي",
        clips=[ClipJob(title="مقطع", start="00:03:00", end="00:04:00")],
        status=JobStatus.QUEUED,
    )

    class FakeVideoProcessor:
        def process_project(self, source_request, project_name, _clip_rows, **_kwargs):
            calls.append(f"{source_request.source_type.value}:{project_name}")
            return SimpleNamespace(project_output_folder=Path(f"C:/output/{project_name}"))

    worker = QueueProcessingWorker([youtube_job, local_job], FakeVideoProcessor(), [])
    worker.run()

    assert calls == ["youtube:يوتيوب", "local_file:محلي"]
    assert [youtube_job.status, local_job.status] == [JobStatus.DONE, JobStatus.DONE]


def test_queue_processing_worker_marks_youtube_failure_clearly() -> None:
    job = VideoJob(
        source_type=QueueVideoSourceType.YOUTUBE,
        source="https://youtu.be/abc123",
        title="يفشل",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )

    class FailingVideoProcessor:
        def process_project(self, *args, **kwargs):
            raise RuntimeError("sign in required")

    worker = QueueProcessingWorker([job], FailingVideoProcessor(), [])
    worker.run()

    assert job.status == JobStatus.FAILED
    assert len(job.errors) == 1
    assert "فشل تحميل أو معالجة رابط يوتيوب" in job.errors[0]
    assert job.failure_stage == "download"


def test_queue_processing_worker_marks_failed_job_without_running_next() -> None:
    first = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/lesson.mp4",
        title="يفشل",
        clips=[ClipJob(title="مقطع", start="00:01:00", end="00:02:00")],
        status=JobStatus.QUEUED,
    )
    second = VideoJob(
        source_type=QueueVideoSourceType.LOCAL,
        source="C:/videos/second.mp4",
        title="يبقى في الانتظار",
        clips=[ClipJob(title="مقطع", start="00:03:00", end="00:04:00")],
        status=JobStatus.QUEUED,
    )

    class FailingVideoProcessor:
        def process_project(self, *args, **kwargs):
            raise RuntimeError("failed cut")

    worker = QueueProcessingWorker([first, second], FailingVideoProcessor(), [])
    worker.run()

    assert first.status == JobStatus.FAILED
    assert len(first.errors) == 1
    assert "فشل قص المقاطع" in first.errors[0]
    assert first.failure_stage == "cutting"
    assert second.status == JobStatus.QUEUED


def test_queue_validate_selected_local_job_updates_status_without_processing(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    job = window._add_queue_local_file_job(str(video_path))

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.validate_selected_queue_job()

    assert job.status == JobStatus.READY
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "جاهز"
    assert "تم فحص المهمة المحددة" in window.log_area.toPlainText()
    assert "الملف موجود" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_validate_selected_unsupported_url_sets_error_without_processing() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://vimeo.com/123", title="غير مدعوم")

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.validate_selected_queue_job()

    assert job.status == JobStatus.VALIDATION_ERROR
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "خطأ في الفحص"
    assert "رابط يوتيوب غير صالح" in window.log_area.toPlainText()
    assert "لا يمكن بدء المهمة قبل إصلاح الأخطاء" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_queue_high_priority_checkbox_toggles_per_job() -> None:
    app = _app()
    window = MainWindow()
    job = window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    priority_item = window.queue_table.item(0, QUEUE_HIGH_PRIORITY_COLUMN)

    priority_item.setCheckState(Qt.Checked)

    assert job.settings.high_priority is True

    priority_item.setCheckState(Qt.Unchecked)

    assert job.settings.high_priority is False

    window.close()
    app.processEvents()


def test_queue_clear_requires_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window._add_queue_url_job("https://youtu.be/abc123", title="درس")
    window._ask_clear_queue_confirmation = lambda: False

    window.clear_queue()

    assert len(window.job_queue) == 1
    assert window.queue_table.rowCount() == 1
    assert "تم إلغاء مسح قائمة الانتظار" in window.log_area.toPlainText()

    window._ask_clear_queue_confirmation = lambda: True

    window.clear_queue()

    assert window.job_queue == []
    assert window.queue_table.rowCount() == 0

    window.close()
    app.processEvents()


def test_queue_action_buttons_wiring_remains_passive(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    video_path = tmp_path / "lesson.mp4"
    video_path.write_bytes(b"ok")
    queue_file = tmp_path / "queue.json"

    def fake_open_file_name(*args, **kwargs):
        caption = args[1] if len(args) > 1 else ""
        if "تحميل قائمة" in caption:
            return str(queue_file), "JSON Files (*.json)"
        return str(video_path), "Video Files (*.mp4)"

    monkeypatch.setattr("src.main_window.QFileDialog.getOpenFileName", fake_open_file_name)
    monkeypatch.setattr(
        "src.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(queue_file), "JSON Files (*.json)"),
    )
    monkeypatch.setattr(
        "src.main_window.QInputDialog.getText",
        lambda *args, **kwargs: ("https://youtu.be/abc123", True),
    )
    window._ask_replace_queue_clips_confirmation = lambda: True
    window._ask_replace_current_clip_table_confirmation = lambda: True
    window._ask_replace_workspace_source_confirmation = lambda: True
    window._ask_replace_queue_state_confirmation = lambda: True
    window._ask_clear_queue_confirmation = lambda: True

    window.project_name_input.setText("مشروع")
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(video_path))
    window._insert_clip_row(1, "مقطع", "00:00:01", "00:00:05")

    window.add_current_work_to_queue_button.click()
    window.add_queue_local_video_button.click()
    window.add_queue_url_button.click()
    app.processEvents()

    assert len(window.job_queue) == 3
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.save_queue_clips_button.click()
    window.validate_queue_job_button.click()
    window.validate_all_queue_jobs_button.click()
    window.run_selected_queue_job_button.click()
    window.run_all_queue_simulation_button.click()
    assert "تم تشغيل المحاكاة فقط" in window.log_area.toPlainText()
    window.load_queue_clips_button.click()
    window.load_queue_job_workspace_button.click()
    window.save_queue_state_button.click()
    app.processEvents()

    assert queue_file.exists()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.clear_queue_button.click()
    assert len(window.job_queue) == 0
    window.load_queue_state_button.click()
    assert len(window.job_queue) == 3
    window.queue_table.setCurrentCell(0, QUEUE_SOURCE_COLUMN)
    window.delete_queue_job_button.click()
    assert len(window.job_queue) == 2
    window.clear_queue_button.click()

    assert len(window.job_queue) == 0
    assert window.queue_table.rowCount() == 0
    assert window._processing_thread is None
    assert window._processing_worker is None

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


def test_combined_validation_button_runs_table_and_smart_validation(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    captured = {}

    def fake_smart_validation(rows, *, known_video_duration_seconds):
        captured["rows"] = list(rows)
        captured["known_video_duration_seconds"] = known_video_duration_seconds
        return SmartValidationReport(total_clips_count=1, issues=[])

    monkeypatch.setattr("src.main_window.validate_clips_before_cutting", fake_smart_validation)
    window.project_name_input.setText("مشروع")
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window.add_clip_row()
    window.clips_table.item(0, TITLE_COLUMN).setText("مقطع")
    window.clips_table.item(0, START_COLUMN).setText("4:15")
    window.clips_table.item(0, END_COLUMN).setText("6:35")

    assert window.validate_before_cutting() is True

    assert len(captured["rows"]) == 1
    assert window.clips_table.item(0, START_COLUMN).text() == "00:04:15"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:06:35"
    assert "نتيجة الفحص الذكي قبل القص" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_smart_paste_preview_dialog_generates_summary_and_clip_table() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    assert dialog.summary_label.text() == "الصق الرسالة ثم اضغط فحص الرسالة لعرض المعاينة."
    assert dialog.parse_button.text() == "فحص الرسالة"
    assert dialog.apply_button.text() == "اختيار طريقة الاستيراد"
    assert dialog.copy_debug_button.text() == "نسخ تقرير التحليل"
    dialog.message_input.setPlainText(
        "https://youtu.be/abc123\n"
        "01:41 - 03:12 : اسم الله الوهاب\n"
        "20:10 - 26:11 عنوان آخر"
    )

    preview = dialog.generate_preview()

    assert len(preview.video_urls) == 1
    assert len(preview.clips) == 2
    assert "عدد المقاطع المكتشفة: 2" in dialog.summary_label.text()
    assert "عدد التحذيرات: 0" in dialog.summary_label.text()
    assert dialog.detected_url_label.text() == "https://youtu.be/abc123"
    assert dialog.clips_preview_table.rowCount() == 2
    assert [
        dialog.clips_preview_table.horizontalHeaderItem(column).text()
        for column in range(dialog.clips_preview_table.columnCount())
    ] == ["الرقم", "العنوان", "البداية", "النهاية", "الاستثناءات", "الحالة / الملاحظات"]
    assert dialog.clips_preview_table.item(0, 0).text() == "1"
    assert dialog.clips_preview_table.item(0, 1).text() == "اسم الله الوهاب"
    assert dialog.apply_button.isEnabled()
    assert dialog.copy_debug_button.isEnabled()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_dialog_shows_exclusions_and_notes() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    dialog.message_input.setPlainText("26:56 - 29:14 عنوان (27:40 - 28:20) أول كلمة: بداية آخر كلمة: نهاية")

    preview = dialog.generate_preview()

    assert len(preview.clips) == 1
    assert dialog.clips_preview_table.item(0, 4).text() == "00:27:40-00:28:20"
    assert "ملاحظة بداية المقطع" in dialog.clips_preview_table.item(0, 5).text()
    assert "ملاحظة نهاية المقطع" in dialog.clips_preview_table.item(0, 5).text()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_dialog_shows_multi_part_clips() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    dialog.message_input.setPlainText("10:12 - 11:35 + 12:33 - 17:51 (title)")

    preview = dialog.generate_preview()

    assert len(preview.clips) == 1
    assert preview.clips[0].multi_part
    assert "00:10:12 - 00:11:35" in dialog.clips_preview_table.item(0, 5).text()
    assert "00:12:33 - 00:17:51" in dialog.clips_preview_table.item(0, 5).text()
    assert "مقطع مركب" in dialog.warnings_area.toPlainText()
    assert "توجد تحذيرات، راجعها قبل الاستيراد" in dialog.review_status_label.text()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_dialog_blocks_end_before_start_error() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    dialog.message_input.setPlainText("26:34 - 26:18 (تشميت العاطس)")

    preview = dialog.generate_preview()

    assert len(preview.clips) == 1
    assert "عدد الأخطاء: 1" in dialog.summary_label.text()
    assert "توجد أخطاء تحتاج مراجعة قبل الاستيراد" in dialog.review_status_label.text()
    assert "نهاية المقطع قبل بدايته" in dialog.warnings_area.toPlainText()
    assert not dialog.apply_button.isEnabled()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_dialog_shows_unparsed_lines_and_debug_copy() -> None:
    app = _app()
    dialog = SmartPasteImportDialog()
    preview = SmartPastePreview(
        video_urls=["https://youtube.com/watch?v=abc123&token=secret"],
        project_title="مشروع",
        clips=[SmartPasteClip(1, "مقطع", "00:01:00", "00:02:00", 1, "1:00 - 2:00 مقطع")],
        warnings=[SmartPasteWarning(3, "توجد حدود نصية تحتاج مراجعة يدوية", "آخر كلمة")],
        unparsed_lines=[SmartPasteUnparsedLine(4, "سطر غير مفهوم")],
    )

    dialog.preview = preview
    dialog._show_preview(preview)
    dialog.copy_debug_report()

    assert "هل توجد أسطر تحتاج مراجعة: نعم" in dialog.summary_label.text()
    assert "سطر غير مفهوم" in dialog.unparsed_area.toPlainText()
    assert "توجد حدود نصية تحتاج مراجعة يدوية" in dialog.warnings_area.toPlainText()
    assert "تقرير فحص الاستيراد الذكي" in dialog.analysis_details_area.toPlainText()
    assert "secret" not in dialog.detected_url_label.text()
    assert "secret" not in QApplication.clipboard().text()
    assert dialog.apply_button.isEnabled()

    dialog.close()
    app.processEvents()


def test_smart_paste_apply_empty_url_and_table_without_processing() -> None:
    app = _app()
    window = MainWindow()
    window._ask_smart_paste_apply_mode = lambda preview: "replace"
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


def test_smart_paste_does_not_apply_without_confirmation() -> None:
    app = _app()
    window = MainWindow()
    window.youtube_input.setText("https://youtu.be/existing")
    asked = {"apply": 0}

    def cancel_apply(preview):
        asked["apply"] += 1
        return None

    window._ask_smart_paste_apply_mode = cancel_apply
    preview = SmartPastePreview(
        video_urls=["https://youtu.be/new"],
        project_title="",
        clips=[],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is False
    assert asked["apply"] == 1
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
    asked = {"apply": 0}

    def cancel_apply(preview):
        asked["apply"] += 1
        return None

    window._ask_smart_paste_apply_mode = cancel_apply
    preview = SmartPastePreview(
        video_urls=[],
        project_title="",
        clips=[SmartPasteClip(1, "جديد", "00:01:00", "00:02:00", 1, "01:00 - 02:00 جديد")],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is False
    assert asked["apply"] == 1
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
    window._ask_smart_paste_apply_mode = lambda preview: "append"
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
    window._ask_smart_paste_apply_mode = lambda preview: "replace"
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


def test_smart_paste_keeps_multi_part_clips_preview_only() -> None:
    app = _app()
    window = MainWindow()
    window._ask_smart_paste_apply_mode = lambda preview: "replace"
    preview = SmartPastePreview(
        video_urls=[],
        project_title="",
        clips=[
            SmartPasteClip(
                1,
                "title",
                "00:10:12",
                "00:17:51",
                1,
                "10:12 - 11:35 + 12:33 - 17:51 (title)",
                parts=[
                    SmartPastePart("00:10:12", "00:11:35"),
                    SmartPastePart("00:12:33", "00:17:51"),
                ],
            )
        ],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is True
    assert window.clips_table.rowCount() == 0
    assert "مقطع مركب في المعاينة فقط" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_smart_paste_main_paste_box_opens_preview_without_processing(monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    captured = {}

    def fake_exec(dialog):
        captured["text"] = dialog.message_input.toPlainText()
        captured["summary"] = dialog.summary_label.text()
        captured["url"] = dialog.detected_url_label.text()
        assert dialog.preview is not None
        return QDialog.Accepted

    monkeypatch.setattr("src.main_window.SmartPasteImportDialog.exec", fake_exec)
    window._ask_smart_paste_apply_mode = lambda preview: "append"
    window.paste_message_input.setPlainText(
        "https://youtu.be/abc123\n"
        "01:00 - 02:00 عنوان"
    )

    window.import_smart_paste_message()

    assert captured["text"].startswith("https://youtu.be/abc123")
    assert "عدد المقاطع المكتشفة: 1" in captured["summary"]
    assert captured["url"] == "https://youtu.be/abc123"
    assert window.youtube_input.text() == "https://youtu.be/abc123"
    assert window.clips_table.rowCount() == 1
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_smart_paste_preview_shows_detected_project_title_url_and_clip_titles() -> None:
    app = _app()
    dialog = SmartPasteImportDialog(
        initial_text=(
            "مقاطع من لمعة الإعتقاد ، الدرس الثاني\n"
            "https://youtu.be/05spuILAwrQ\n\n"
            "6:20 - 8:50\n"
            ", إثبات صحة النبوة"
        ),
        auto_generate=True,
    )

    assert dialog.preview is not None
    assert dialog.detected_project_label.text() == "مقاطع من لمعة الإعتقاد ، الدرس الثاني"
    assert dialog.detected_url_label.text() == "https://youtu.be/05spuILAwrQ"
    assert dialog.clips_preview_table.item(0, 0).text() == "1"
    assert dialog.clips_preview_table.item(0, 1).text() == "إثبات صحة النبوة"
    assert dialog.clips_preview_table.item(0, 2).text() == "00:06:20"
    assert dialog.clips_preview_table.item(0, 3).text() == "00:08:50"

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_old_pr35_sample_still_shows_all_detected_clips() -> None:
    app = _app()
    sample = _smart_import_fixture("old_pr35_lumaat_13_clips")
    dialog = SmartPasteImportDialog(initial_text=sample["input_text"], auto_generate=True)

    assert dialog.preview is not None
    assert dialog.preview.video_urls == [sample["expected_url"]]
    assert dialog.detected_project_label.text() == sample["expected_project_title"]
    assert "عدد المقاطع المكتشفة: 13" in dialog.summary_label.text()
    assert dialog.clips_preview_table.rowCount() == 13
    first_start, first_end, first_title = sample["expected_clips"][0]
    last_start, last_end, last_title = sample["expected_clips"][-1]
    assert dialog.clips_preview_table.item(0, 1).text() == first_title
    assert dialog.clips_preview_table.item(0, 2).text() == first_start
    assert dialog.clips_preview_table.item(0, 3).text() == first_end
    assert dialog.clips_preview_table.item(12, 1).text() == last_title
    assert dialog.clips_preview_table.item(12, 2).text() == last_start
    assert dialog.clips_preview_table.item(12, 3).text() == last_end
    assert "يوجد تداخل بين المقاطع" in dialog.warnings_area.toPlainText()

    dialog.close()
    app.processEvents()


def test_smart_paste_preview_real_world_evidence_samples_show_review_metadata() -> None:
    app = _app()
    sample_names = [
        "youtube_live_arabic_until_separator",
        "labeled_start_end_minutes_nearby",
        "parenthesized_internal_exclusion_with_previous_title",
        "plus_joined_multi_part_one_clip_candidate",
    ]

    for sample_name in sample_names:
        sample = _smart_import_fixture(sample_name)
        dialog = SmartPasteImportDialog(initial_text=sample["input_text"], auto_generate=True)

        assert dialog.preview is not None
        assert dialog.preview.video_urls == ([sample["expected_url"]] if sample["expected_url"] else [])
        assert dialog.preview.project_title == sample["expected_project_title"]
        assert dialog.clips_preview_table.rowCount() == len(sample["expected_clips"])
        if sample["expected_url"]:
            assert sample["expected_url"].split("?")[0] in dialog.detected_url_label.text()
        for row, (expected_start, expected_end, expected_title) in enumerate(sample["expected_clips"]):
            assert dialog.clips_preview_table.item(row, 1).text() == expected_title
            assert dialog.clips_preview_table.item(row, 2).text() == expected_start
            assert dialog.clips_preview_table.item(row, 3).text() == expected_end
        for row, exclusions in sample["expected_exclusions"].items():
            exclusions_text = dialog.clips_preview_table.item(row, 4).text()
            for exclusion_start, exclusion_end in exclusions:
                assert f"{exclusion_start}-{exclusion_end}" in exclusions_text
        for expected_warning in sample["expected_warnings"]:
            assert expected_warning in dialog.warnings_area.toPlainText()
        assert "عدد المقاطع المكتشفة" in dialog.summary_label.text()

        dialog.close()
        app.processEvents()


def test_smart_paste_preview_marks_multi_part_sample_for_review_without_splitting() -> None:
    app = _app()
    sample = _smart_import_fixture("plus_joined_multi_part_one_clip_candidate")
    dialog = SmartPasteImportDialog(initial_text=sample["input_text"], auto_generate=True)

    assert dialog.preview is not None
    assert len(dialog.preview.clips) == 1
    assert dialog.preview.clips[0].multi_part
    assert "تم اكتشاف مقطع متعدد الأجزاء، قد يحتاج مراجعة قبل القص" in dialog.warnings_area.toPlainText()
    assert "مقطع مركب" in dialog.clips_preview_table.item(0, 5).text()
    assert "توجد تحذيرات، راجعها قبل الاستيراد" in dialog.review_status_label.text()

    dialog.close()
    app.processEvents()


def test_smart_paste_replace_preserves_detected_project_and_clip_titles() -> None:
    app = _app()
    window = MainWindow()
    window._ask_smart_paste_apply_mode = lambda preview: "replace"
    preview = parse_smart_paste_message(
        "مقاطع من لمعة الإعتقاد ، الدرس الثاني\n"
        "https://youtu.be/05spuILAwrQ\n\n"
        "6:20 - 8:50\n"
        ", إثبات صحة النبوة\n\n"
        "1:25:14 - 1:26:04"
    )

    assert window._apply_smart_paste_preview(preview) is True

    assert window.project_name_input.text() == "مقاطع من لمعة الإعتقاد ، الدرس الثاني"
    assert window.youtube_input.text() == "https://youtu.be/05spuILAwrQ"
    assert window.clips_table.rowCount() == 2
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "إثبات صحة النبوة"
    assert window.clips_table.item(1, TITLE_COLUMN).text() == "مقطع 02"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_smart_paste_apply_choices_are_user_facing_arabic_labels() -> None:
    assert SMART_PASTE_REPLACE_LABEL == "استبدال البيانات الحالية"
    assert SMART_PASTE_APPEND_LABEL == "إضافة كمقاطع جديدة"
    assert SMART_PASTE_QUEUE_LABEL == "إضافة كمهمة جديدة في قائمة الانتظار"
    assert SMART_PASTE_CANCEL_LABEL == "إلغاء"


def test_smart_paste_can_add_detected_data_as_queue_job_without_processing() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window._ask_smart_paste_apply_mode = lambda preview: "queue"
    preview = SmartPastePreview(
        video_urls=["https://youtu.be/abc123"],
        project_title="عنوان من الرسالة",
        clips=[
            SmartPasteClip(
                1,
                "مقطع",
                "00:01:00",
                "00:02:00",
                1,
                "01:00 - 02:00 مقطع (01:20 - 01:30)",
                exclusions=[SmartPasteExclusion("00:01:20", "00:01:30")],
            )
        ],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is True

    assert len(window.job_queue) == 1
    assert window.job_queue[0].source_type == QueueVideoSourceType.YOUTUBE
    assert window.job_queue[0].source == "https://youtu.be/abc123"
    assert window.job_queue[0].title == "عنوان من الرسالة"
    assert len(window.job_queue[0].clips) == 1
    assert window.job_queue[0].clips[0].title == "مقطع"
    assert window.job_queue[0].clips[0].exclusions == "00:01:20-00:01:30"
    assert window.job_queue[0].settings.speed_adjustment_enabled is False
    assert window.job_queue[0].settings.speed == 1.0
    assert window.job_queue[0].settings.volume_adjustment_enabled is False
    assert window.job_queue[0].settings.volume_percent == 100
    assert window.queue_table.item(0, QUEUE_CLIP_COUNT_COLUMN).text() == "1"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_smart_paste_queue_preserves_detected_project_and_clip_titles() -> None:
    app = _app()
    window = MainWindow()
    window._ask_smart_paste_apply_mode = lambda preview: "queue"
    preview = parse_smart_paste_message(
        "مقاطع من لمعة الإعتقاد ، الدرس الثاني\n"
        "https://youtu.be/05spuILAwrQ\n\n"
        "6:20 - 8:50\n"
        ", إثبات صحة النبوة"
    )

    assert window._apply_smart_paste_preview(preview) is True

    assert len(window.job_queue) == 1
    assert window.job_queue[0].title == "مقاطع من لمعة الإعتقاد ، الدرس الثاني"
    assert window.job_queue[0].source == "https://youtu.be/05spuILAwrQ"
    assert window.job_queue[0].clips[0].title == "إثبات صحة النبوة"
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_smart_paste_no_detected_url_or_clips_shows_clear_message() -> None:
    app = _app()
    window = MainWindow()
    window._ask_smart_paste_apply_mode = lambda preview: "replace"
    preview = SmartPastePreview(
        video_urls=[],
        project_title="",
        clips=[],
        warnings=[],
        unparsed_lines=[],
    )

    assert window._apply_smart_paste_preview(preview) is False
    assert "لم يتم العثور على رابط أو مقاطع مفهومة" in window.log_area.toPlainText()

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


def test_delete_selected_clip_row_removes_only_selected_row() -> None:
    app = _app()
    window = MainWindow()
    window._insert_clip_row(1, "الأول", "00:01:00", "00:02:00")
    window._insert_clip_row(2, "الثاني", "00:03:00", "00:04:00")
    window.clips_table.selectRow(0)
    window.clips_table.setCurrentCell(0, TITLE_COLUMN)

    window.delete_selected_row()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "الثاني"
    assert window.clips_table.item(0, 0).text() == "1"

    window.close()
    app.processEvents()


def test_delete_clip_without_selected_row_does_not_crash() -> None:
    app = _app()
    window = MainWindow()
    window._insert_clip_row(1, "الأول", "00:01:00", "00:02:00")
    window.clips_table.clearSelection()
    window.clips_table.setCurrentCell(-1, -1)

    window.delete_selected_row()

    assert window.clips_table.rowCount() == 1
    assert "لا يوجد مقطع محدد" in window.log_area.toPlainText()

    window.close()
    app.processEvents()


def test_preview_without_selected_clip_shows_arabic_message() -> None:
    app = _app()
    window = MainWindow()

    window.preview_selected_clip_start()

    assert "لا يوجد مقطع محدد" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_youtube_preview_without_downloaded_input_shows_message() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("مشروع")
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://youtube.com/watch?v=test")
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00")
    window.clips_table.setCurrentCell(0, TITLE_COLUMN)

    window.preview_selected_clip_start()

    assert "يجب تنزيل الفيديو أولًا قبل المعاينة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_selected_clip_preview_uses_local_video_without_final_processing(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    source_video = tmp_path / "lesson.mp4"
    source_video.write_bytes(b"video")
    preview_output = tmp_path / "preview.mp4"
    captured = {}

    def fake_create_preview_clip(input_video_path, preview_range, **kwargs):
        captured["input_video_path"] = input_video_path
        captured["preview_range"] = preview_range
        captured["kwargs"] = kwargs
        preview_output.write_bytes(b"preview")
        return preview_output

    monkeypatch.setattr("src.main_window.probe_media_duration_seconds", lambda path: 120)
    monkeypatch.setattr("src.main_window.create_preview_clip", fake_create_preview_clip)
    monkeypatch.setattr("src.main_window.QDesktopServices.openUrl", lambda url: True)
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(source_video))
    window.pre_padding_input.setValue(1)
    window.post_padding_input.setValue(2)
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00")
    window.clips_table.setCurrentCell(0, TITLE_COLUMN)

    window.preview_selected_clip()

    assert captured["input_video_path"] == source_video
    assert captured["preview_range"].start_seconds == 59
    assert captured["preview_range"].end_seconds == 120
    assert captured["kwargs"]["preview_kind"].value == "full"
    assert "تم فتح المعاينة" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

    window.close()
    app.processEvents()


def test_selected_clip_preview_notes_exclusions_are_ignored(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    source_video = tmp_path / "lesson.mp4"
    source_video.write_bytes(b"video")

    monkeypatch.setattr("src.main_window.probe_media_duration_seconds", lambda path: 120)
    monkeypatch.setattr("src.main_window.create_preview_clip", lambda *args, **kwargs: tmp_path / "preview.mp4")
    monkeypatch.setattr("src.main_window.QDesktopServices.openUrl", lambda url: True)
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(source_video))
    window._insert_clip_row(1, "مقطع", "00:01:00", "00:02:00", "00:01:10-00:01:20")
    window.clips_table.setCurrentCell(0, TITLE_COLUMN)

    window.preview_selected_clip()

    assert "ملاحظة: المعاينة لا تطبق الاستثناءات في هذه النسخة" in window.log_area.toPlainText()

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
