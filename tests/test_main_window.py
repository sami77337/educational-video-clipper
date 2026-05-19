import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from src.main_window import (
    END_COLUMN,
    EXCLUSIONS_COLUMN,
    QUEUE_CLIP_COUNT_COLUMN,
    QUEUE_HIGH_PRIORITY_COLUMN,
    QUEUE_SOURCE_COLUMN,
    QUEUE_STATUS_COLUMN,
    QUEUE_TITLE_COLUMN,
    RULE_FOLDER_COLUMN,
    RULE_MAX_COLUMN,
    RULE_MIN_COLUMN,
    RULE_NAME_COLUMN,
    START_COLUMN,
    TITLE_COLUMN,
    MainWindow,
    SmartPasteImportDialog,
)
from src.job_queue import ClipJob, JobStatus, VideoSourceType as QueueVideoSourceType
from src.readiness import STATUS_READY, ReadinessCheckItem, ReadinessReport
from src.smart_paste_parser import (
    SmartPasteClip,
    SmartPasteExclusion,
    SmartPastePart,
    SmartPastePreview,
    SmartPasteWarning,
)
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
    assert [
        window.queue_table.horizontalHeaderItem(column).text()
        for column in range(window.queue_table.columnCount())
    ] == ["المصدر", "العنوان", "عدد المقاطع", "الحالة", "أولوية عالية", "الإجراء"]
    assert window.queue_table.rowCount() == 0
    assert window.add_current_work_to_queue_button.text() == "إضافة العمل الحالي إلى قائمة الانتظار"
    assert window.add_queue_local_video_button.text() == "إضافة فيديو محلي"
    assert window.add_queue_url_button.text() == "إضافة رابط"
    assert window.save_queue_clips_button.text() == "حفظ المقاطع للمهمة المحددة"
    assert window.load_queue_clips_button.text() == "تحميل مقاطع المهمة المحددة"
    assert window.load_queue_job_workspace_button.text() == "تحميل المهمة المحددة للتحرير"
    assert window.save_queue_state_button.text() == "حفظ قائمة الانتظار"
    assert window.load_queue_state_button.text() == "تحميل قائمة انتظار"
    assert window.run_selected_queue_job_button.text() == "تشغيل المحدد فقط"
    assert window.run_all_queue_simulation_button.text() == "تشغيل كل القائمة تجريبيًا"
    assert window.validate_queue_job_button.text() == "إعادة فحص المحدد"
    assert window.validate_all_queue_jobs_button.text() == "فحص كل قائمة الانتظار"
    assert window.delete_queue_job_button.text() == "إزالة المهمة المحددة"
    assert window.clear_queue_button.text() == "مسح القائمة"

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


def test_queue_add_current_url_work_with_clip_rows() -> None:
    app = _app()
    window = MainWindow()
    window.project_name_input.setText("درس رابط")
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://youtu.be/abc123")
    window._insert_clip_row(1, "المقطع", "00:01:00", "00:02:00")

    window.add_current_work_to_queue()

    assert len(window.job_queue) == 1
    job = window.job_queue[0]
    assert job.source_type == QueueVideoSourceType.YOUTUBE
    assert job.source == "https://youtu.be/abc123"
    assert job.title == "درس رابط"
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
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط Facebook"
    assert window._processing_thread is None
    assert window._processing_worker is None

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
    assert window.queue_table.item(0, QUEUE_SOURCE_COLUMN).text() == "رابط Facebook"
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
    assert "تم تحميل المهمة المحددة للتحرير" in window.log_area.toPlainText()
    assert "لم يتم بدء أي قص أو تحميل" in window.log_area.toPlainText()
    assert window._processing_thread is None
    assert window._processing_worker is None

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
    assert "تم تحميل المهمة المحددة للتحرير" in window.log_area.toPlainText()
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
    assert "تم تحميل المهمة المحددة للتحرير" in window.log_area.toPlainText()
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
    assert "تم فحص كل قائمة الانتظار" in window.log_area.toPlainText()
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
    assert "الرابط غير مدعوم حاليًا" in job.errors
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
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتمل"
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
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتمل"
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
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتمل"
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
    assert window.queue_table.item(0, QUEUE_STATUS_COLUMN).text() == "مكتمل"
    assert window.queue_table.item(1, QUEUE_STATUS_COLUMN).text() == "مكتمل"
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
    assert "الرابط غير مدعوم حاليًا" in window.log_area.toPlainText()
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
    assert "00:10:12 - 00:11:35" in dialog.clips_preview_table.item(0, 3).text()
    assert "00:12:33 - 00:17:51" in dialog.clips_preview_table.item(0, 3).text()
    assert "مقطع مركب" in dialog.warnings_area.toPlainText()

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


def test_smart_paste_keeps_multi_part_clips_preview_only() -> None:
    app = _app()
    window = MainWindow()
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
