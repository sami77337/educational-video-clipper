import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.main_window import END_COLUMN, START_COLUMN, TITLE_COLUMN, MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_table_starts_empty_and_add_row_creates_blank_row() -> None:
    app = _app()
    window = MainWindow()

    assert window.clips_table.rowCount() == 0

    window.add_clip_row()

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == ""
    assert window.clips_table.item(0, START_COLUMN).text() == ""
    assert window.clips_table.item(0, END_COLUMN).text() == ""

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
