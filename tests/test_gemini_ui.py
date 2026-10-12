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


def test_gemini_replace_updates_old_youtube_source(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://www.youtube.com/watch?v=oldVideo123")
    window.paste_message_input.setPlainText(
        "https://youtu.be/newVideo123\n"
        "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n"
        "|---|---|---|---|\n"
        "| 1 | هل يجب الوضوء؟ | 00:02 | 00:37 |\n"
    )
    window.import_gemini_message()
    assert window.youtube_input.text() == "https://www.youtube.com/watch?v=newVideo123"
    assert window.clips_table.rowCount() == 1
    window.close()
    app.processEvents()


def test_gemini_append_rejects_mismatched_active_youtube_source(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(str(args[2])))
    window.youtube_radio.setChecked(True)
    window.youtube_input.setText("https://www.youtube.com/watch?v=oldVideo123")
    window._insert_clip_row(1, "سؤال أول", "00:01", "00:04")
    monkeypatch.setattr(window, "_ask_table_import_mode", lambda *args: "append")
    window.paste_message_input.setPlainText(
        "https://www.youtube.com/watch?v=newVideo123\n"
        "| م | عنوان السؤال | وقت البداية | وقت النهاية |\n"
        "|---|---|---|---|\n"
        "| 1 | سؤال آخر | 00:06 | 00:10 |\n"
    )
    window.import_gemini_message()
    assert window.clips_table.rowCount() == 1
    assert window.youtube_input.text() == "https://www.youtube.com/watch?v=oldVideo123"
    assert warnings and "يختلف" in warnings[0]
    window.close()
    app.processEvents()
