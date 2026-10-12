import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.main_window import END_COLUMN, TITLE_COLUMN, MainWindow


def test_gemini_paste_updates_clip_table_and_auto_enables_team_package(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    window.local_file_radio.setChecked(True)
    window.paste_message_input.setPlainText(
        "https://www.youtube.com/watch?v=abcDEF12345\n"
        "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n"
        "|---|---|---|---|\n"
        "| 1 | هل يجوز الجمع؟ | 00:19 | 00:37.500 |\n"
    )
    window.import_gemini_message()
    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "هل يجوز الجمع؟"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:00:37.500"
    assert window.handoff_package_checkbox.isChecked()
    assert window._current_job_settings_snapshot().create_handoff_package
    assert window._current_job_settings_snapshot().gemini_source_url == "https://www.youtube.com/watch?v=abcDEF12345"
    assert window._current_video_source().source_reference == "https://www.youtube.com/watch?v=abcDEF12345"

    window._reset_workspace_to_defaults()
    assert not window.handoff_package_checkbox.isChecked()
    assert not window._gemini_source_url
    window.close()
    app.processEvents()
