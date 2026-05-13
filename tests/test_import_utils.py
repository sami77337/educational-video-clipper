import csv
import os
from datetime import time

import pytest
from openpyxl import Workbook

from src.import_utils import (
    AR_MISSING_REQUIRED_COLUMNS,
    ClipImportError,
    ImportedClipRow,
    import_clip_rows,
    normalize_imported_time,
)


def test_valid_xlsx_import(tmp_path) -> None:
    file_path = tmp_path / "clips.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["number", "title", "start", "end"])
    worksheet.append([1, "مقدمة", "00:09:16", "00:09:50"])
    workbook.save(file_path)

    rows = import_clip_rows(file_path)

    assert rows == [ImportedClipRow(number=1, title="مقدمة", start="00:09:16", end="00:09:50")]


def test_valid_csv_import(tmp_path) -> None:
    file_path = tmp_path / "clips.csv"
    with file_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["number", "title", "start", "end"])
        writer.writeheader()
        writer.writerow({"number": "2", "title": "سؤال قصير", "start": "9:16", "end": "9:50"})

    rows = import_clip_rows(file_path)

    assert rows == [ImportedClipRow(number=2, title="سؤال قصير", start="09:16", end="09:50")]


def test_missing_required_columns(tmp_path) -> None:
    file_path = tmp_path / "clips.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["number", "title", "start"])
    worksheet.append([1, "مقدمة", "00:01"])
    workbook.save(file_path)

    with pytest.raises(ClipImportError) as error:
        import_clip_rows(file_path)

    assert str(error.value) == AR_MISSING_REQUIRED_COLUMNS


def test_arabic_title_import(tmp_path) -> None:
    file_path = tmp_path / "clips.csv"
    file_path.write_text("number,title,start,end\n1,ما حكم نعي الميت,00:01,00:05\n", encoding="utf-8-sig")

    rows = import_clip_rows(file_path)

    assert rows[0].title == "ما حكم نعي الميت"


def test_time_text_parsing() -> None:
    assert normalize_imported_time("9:16") == "09:16"
    assert normalize_imported_time("00:09:16") == "00:09:16"
    assert normalize_imported_time("٩:١٦") == "09:16"


def test_excel_time_value_parsing() -> None:
    assert normalize_imported_time(time(0, 9, 16)) == "09:16"


def test_append_and_replace_table_behavior_is_practical() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.main_window import END_COLUMN, NUMBER_COLUMN, START_COLUMN, TITLE_COLUMN, MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._insert_clip_lines([ImportedClipRow(number=1, title="قديم", start="00:01", end="00:02")], append=False)
    window._insert_clip_lines([ImportedClipRow(number=2, title="جديد", start="00:03", end="00:04")], append=True)

    assert window.clips_table.rowCount() == 2
    assert window.clips_table.item(1, NUMBER_COLUMN).text() == "2"
    assert window.clips_table.item(1, TITLE_COLUMN).text() == "جديد"

    window._insert_clip_lines([ImportedClipRow(number=3, title="بديل", start="00:05", end="00:06")], append=False)

    assert window.clips_table.rowCount() == 1
    assert window.clips_table.item(0, NUMBER_COLUMN).text() == "3"
    assert window.clips_table.item(0, TITLE_COLUMN).text() == "بديل"
    assert window.clips_table.item(0, START_COLUMN).text() == "00:05"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:06"
    window.close()
    app.processEvents()
