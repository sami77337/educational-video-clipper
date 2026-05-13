"""Main window for the desktop application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.export_utils import ExportError, validate_output_folder_path
from src.validation import ClipRowInput, validate_clip_rows, validate_required_text
from src.video_processor import (
    VideoProcessor,
    VideoProcessingError,
    VideoSourceError,
    VideoSourceRequest,
    VideoSourceType,
    validate_local_video_file,
    validate_youtube_url,
)


NUMBER_COLUMN = 0
TITLE_COLUMN = 1
START_COLUMN = 2
END_COLUMN = 3


class ProcessingWorker(QObject):
    """Runs video preparation and clip cutting away from the UI thread."""

    progress = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        video_processor: VideoProcessor,
        source_request: VideoSourceRequest,
        project_name: str,
        clip_rows: list[ClipRowInput],
    ) -> None:
        super().__init__()
        self.video_processor = video_processor
        self.source_request = source_request
        self.project_name = project_name
        self.clip_rows = clip_rows

    @Slot()
    def run(self) -> None:
        try:
            processing_result = self.video_processor.process_project(
                self.source_request,
                self.project_name,
                self.clip_rows,
                progress_callback=self.progress.emit,
            )
        except (VideoSourceError, VideoProcessingError, ExportError) as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"خطأ: {error}")
        else:
            self.succeeded.emit(str(processing_result.project_output_folder))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    """Arabic-friendly initial application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.output_root = Path.cwd() / "output"
        self.video_processor = VideoProcessor(self.output_root)
        self._processing_thread: QThread | None = None
        self._processing_worker: ProcessingWorker | None = None
        self._last_output_folder: Path | None = None

        self.setWindowTitle("Educational Video Clipper")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(980, 720)

        self.youtube_radio = QRadioButton("رابط YouTube")
        self.local_file_radio = QRadioButton("ملف فيديو من الجهاز")
        self.youtube_input = QLineEdit()
        self.local_file_input = QLineEdit()
        self.browse_button = QPushButton("استعراض")
        self.project_name_input = QLineEdit()
        self.clips_table = QTableWidget(0, 4)
        self.add_row_button = QPushButton("إضافة صف")
        self.delete_row_button = QPushButton("حذف الصف المحدد")
        self.validate_button = QPushButton("فحص الجدول")
        self.start_button = QPushButton("بدء المعالجة")
        self.open_output_button = QPushButton("فتح مجلد الإخراج")
        self.log_area = QTextEdit()

        self.setCentralWidget(self._build_ui())
        self._connect_signals()
        self.add_clip_row()
        self._update_source_inputs()
        self.open_output_button.setEnabled(False)

    def _build_ui(self) -> QWidget:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(self._build_video_source_section())
        layout.addWidget(self._build_project_section())
        layout.addWidget(self._build_clips_section(), stretch=1)
        layout.addWidget(self._build_log_section(), stretch=1)

        return central

    def _build_video_source_section(self) -> QGroupBox:
        group = QGroupBox("مصدر الفيديو")
        layout = QGridLayout(group)

        source_group = QButtonGroup(self)
        source_group.addButton(self.youtube_radio)
        source_group.addButton(self.local_file_radio)
        self.youtube_radio.setChecked(True)

        self.youtube_input.setPlaceholderText("ضع رابط YouTube هنا")
        self.local_file_input.setPlaceholderText("اختر ملف فيديو من جهازك")
        self.local_file_input.setReadOnly(True)

        layout.addWidget(self.youtube_radio, 0, 0)
        layout.addWidget(self.youtube_input, 0, 1, 1, 2)
        layout.addWidget(self.local_file_radio, 1, 0)
        layout.addWidget(self.local_file_input, 1, 1)
        layout.addWidget(self.browse_button, 1, 2)
        layout.setColumnStretch(1, 1)

        return group

    def _build_project_section(self) -> QGroupBox:
        group = QGroupBox("معلومات المشروع")
        layout = QGridLayout(group)

        self.project_name_input.setPlaceholderText("مثال: درس الجبر - الوحدة الأولى")

        layout.addWidget(QLabel("اسم المشروع"), 0, 0)
        layout.addWidget(self.project_name_input, 0, 1)
        layout.setColumnStretch(1, 1)

        return group

    def _build_clips_section(self) -> QGroupBox:
        group = QGroupBox("قائمة المقاطع")
        layout = QVBoxLayout(group)

        self.clips_table.setHorizontalHeaderLabels(["الرقم", "العنوان", "البداية", "النهاية"])
        self.clips_table.verticalHeader().setVisible(False)
        self.clips_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.clips_table.horizontalHeader().setSectionResizeMode(NUMBER_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(TITLE_COLUMN, QHeaderView.Stretch)
        self.clips_table.horizontalHeader().setSectionResizeMode(START_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(END_COLUMN, QHeaderView.ResizeToContents)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_row_button)
        buttons.addWidget(self.delete_row_button)
        buttons.addStretch(1)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.open_output_button)

        layout.addWidget(self.clips_table)
        layout.addLayout(buttons)

        return group

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("السجل والتقدم")
        layout = QVBoxLayout(group)

        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("ستظهر رسائل الفحص والتقدم هنا.")
        layout.addWidget(self.log_area)

        return group

    def _connect_signals(self) -> None:
        self.youtube_radio.toggled.connect(self._update_source_inputs)
        self.local_file_radio.toggled.connect(self._update_source_inputs)
        self.browse_button.clicked.connect(self._browse_local_video)
        self.add_row_button.clicked.connect(self.add_clip_row)
        self.delete_row_button.clicked.connect(self.delete_selected_row)
        self.validate_button.clicked.connect(self.validate_inputs)
        self.start_button.clicked.connect(self.start_processing)
        self.open_output_button.clicked.connect(self.open_output_folder)

    def add_clip_row(self) -> None:
        row = self.clips_table.rowCount()
        self.clips_table.insertRow(row)

        number_item = QTableWidgetItem(str(row + 1))
        number_item.setFlags(number_item.flags() & ~Qt.ItemIsEditable)
        number_item.setTextAlignment(Qt.AlignCenter)

        self.clips_table.setItem(row, NUMBER_COLUMN, number_item)
        self.clips_table.setItem(row, TITLE_COLUMN, QTableWidgetItem(""))
        self.clips_table.setItem(row, START_COLUMN, QTableWidgetItem(""))
        self.clips_table.setItem(row, END_COLUMN, QTableWidgetItem(""))
        self.clips_table.setCurrentCell(row, TITLE_COLUMN)

    def delete_selected_row(self) -> None:
        selected_rows = self.clips_table.selectionModel().selectedRows()
        if not selected_rows:
            self._write_log("اختر صفًا من الجدول أولًا.")
            return

        for row_index in sorted((index.row() for index in selected_rows), reverse=True):
            self.clips_table.removeRow(row_index)

        self._renumber_rows()
        self._write_log("تم حذف الصف المحدد.")

    def validate_inputs(self) -> bool:
        errors = self._collect_validation_errors()
        if errors:
            self._write_validation_errors(errors)
            return False

        self._write_log("تم فحص البيانات بنجاح. يمكنك بدء المعالجة.")
        return True

    def start_processing(self) -> None:
        errors = self._collect_validation_errors()
        if errors:
            self._write_validation_errors(errors)
            return

        try:
            project_name = validate_required_text(self.project_name_input.text(), "Project name")
        except ValueError:
            self._write_validation_errors(["أدخل اسم المشروع."])
            return

        self.log_area.clear()
        self._last_output_folder = None
        self._set_processing_enabled(False)
        self._start_processing_worker(
            source_request=self._current_video_source(),
            project_name=project_name,
            clip_rows=self._collect_clip_rows(),
        )

    def open_output_folder(self) -> None:
        try:
            output_dir = validate_output_folder_path(self._last_output_folder)
        except ExportError as error:
            self._append_log(str(error))
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir))):
            self._append_log("خطأ: فشل فتح مجلد الإخراج")
            return

        self._append_log(f"تم فتح مجلد الإخراج: {output_dir}")

    def _browse_local_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "اختر ملف فيديو",
            str(Path.home()),
            "Video files (*.mp4 *.mov *.mkv *.webm);;All files (*.*)",
        )
        if not file_path:
            return

        self.local_file_radio.setChecked(True)
        self.local_file_input.setText(file_path)

    def _update_source_inputs(self) -> None:
        use_youtube = self.youtube_radio.isChecked()
        self.youtube_input.setEnabled(use_youtube)
        self.local_file_input.setEnabled(not use_youtube)
        self.browse_button.setEnabled(not use_youtube)

    def _collect_clip_rows(self) -> list[ClipRowInput]:
        rows: list[ClipRowInput] = []
        for row in range(self.clips_table.rowCount()):
            rows.append(
                ClipRowInput(
                    row_number=row + 1,
                    title=self._cell_text(row, TITLE_COLUMN),
                    start=self._cell_text(row, START_COLUMN),
                    end=self._cell_text(row, END_COLUMN),
                )
            )

        return rows

    def _collect_validation_errors(self) -> list[str]:
        errors: list[str] = []

        try:
            validate_required_text(self.project_name_input.text(), "Project name")
        except ValueError:
            errors.append("أدخل اسم المشروع.")

        try:
            if self.youtube_radio.isChecked():
                validate_youtube_url(self.youtube_input.text())
            else:
                validate_local_video_file(self.local_file_input.text())
        except VideoSourceError as error:
            errors.append(str(error))

        errors.extend(error.message_ar for error in validate_clip_rows(self._collect_clip_rows()))
        return errors

    def _current_video_source(self) -> VideoSourceRequest:
        if self.youtube_radio.isChecked():
            return VideoSourceRequest(VideoSourceType.YOUTUBE, self.youtube_input.text())

        return VideoSourceRequest(VideoSourceType.LOCAL_FILE, self.local_file_input.text())

    def _cell_text(self, row: int, column: int) -> str:
        item = self.clips_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _renumber_rows(self) -> None:
        for row in range(self.clips_table.rowCount()):
            item = self.clips_table.item(row, NUMBER_COLUMN)
            if item is None:
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter)
                self.clips_table.setItem(row, NUMBER_COLUMN, item)
            item.setText(str(row + 1))

    def _write_log(self, message: str) -> None:
        self.log_area.setPlainText(message)

    def _append_log(self, message: str) -> None:
        self.log_area.append(message)

    def _write_validation_errors(self, errors: list[str]) -> None:
        self._write_log("تعذر فحص البيانات:\n" + "\n".join(f"- {error}" for error in errors))

    def _start_processing_worker(
        self,
        source_request: VideoSourceRequest,
        project_name: str,
        clip_rows: list[ClipRowInput],
    ) -> None:
        thread = QThread(self)
        worker = ProcessingWorker(
            video_processor=self.video_processor,
            source_request=source_request,
            project_name=project_name,
            clip_rows=clip_rows,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.succeeded.connect(self._handle_processing_success)
        worker.failed.connect(self._handle_processing_failure)
        worker.finished.connect(self._finish_processing)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_processing_worker)

        self._processing_thread = thread
        self._processing_worker = worker
        thread.start()

    @Slot(str)
    def _handle_processing_success(self, output_folder: str) -> None:
        self._last_output_folder = Path(output_folder)
        self._append_log(f"تم حفظ النتائج داخل: {output_folder}")

    @Slot(str)
    def _handle_processing_failure(self, message: str) -> None:
        self._last_output_folder = None
        self._append_log(message or "حدث خطأ أثناء المعالجة.")

    @Slot()
    def _finish_processing(self) -> None:
        self._set_processing_enabled(True)

    @Slot()
    def _clear_processing_worker(self) -> None:
        self._processing_thread = None
        self._processing_worker = None

    def _set_processing_enabled(self, enabled: bool) -> None:
        widgets = [
            self.youtube_radio,
            self.local_file_radio,
            self.youtube_input,
            self.local_file_input,
            self.browse_button,
            self.project_name_input,
            self.clips_table,
            self.add_row_button,
            self.delete_row_button,
            self.validate_button,
            self.start_button,
            self.open_output_button,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

        if enabled:
            self._update_source_inputs()

        self.open_output_button.setEnabled(enabled and self._last_output_folder is not None)
