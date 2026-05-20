"""Main window for the desktop application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QApplication,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.classification import (
    ClassificationRule,
    ClassificationRuleError,
    classify_duration,
    format_classification_errors_ar,
    format_rule_minutes,
    get_default_classification_rules,
    validate_classification_rules,
)
from src.clip_padding import ClipPadding
from src.clip_preview import (
    MAX_FULL_CLIP_PREVIEW_SECONDS,
    ClipPreviewError,
    ClipPreviewKind,
    calculate_preview_range,
    create_preview_clip,
)
from src.export_utils import ExportError, validate_output_folder_path
from src.import_utils import ClipImportError, ImportedClipRow, import_clip_rows
from src.job_queue import ClipJob, JobSettings, JobStatus, VideoJob, VideoSourceType as QueueVideoSourceType
from src.job_queue_processor import (
    AR_QUEUE_CAN_PREPARE_NEXT,
    AR_QUEUE_FINISHED,
    AR_QUEUE_JOB_ADDED,
    AR_QUEUE_NEXT_JOB_STARTED,
    AR_QUEUE_JOB_WAITING,
    AR_URL_QUEUE_PROCESSING_LATER,
    QueueProcessorState,
    SequentialQueueProcessor,
)
from src.job_queue_runner import format_queue_run_summary_ar, run_dry_queue
from src.job_queue_storage import QueueStorageError, load_queue_jobs, save_queue_jobs
from src.job_queue_validation import (
    apply_queue_validation_result,
    format_queue_validation_result_ar,
    validate_queue_job,
)
from src.message_parser import ParsedClipLine, parse_clip_message
from src.readiness import format_readiness_report_ar, run_readiness_check
from src.smart_paste_parser import SmartPasteClip, SmartPastePreview, parse_smart_paste_message
from src.smart_validation import format_smart_validation_report_ar, validate_clips_before_cutting
from src.time_utils import normalize_timestamp_text, parse_timestamp
from src.version import APP_NAME, APP_SUBTITLE
from src.validation import ClipRowInput, normalize_clip_exclusions, validate_clip_rows, validate_required_text
from src.video_speed import AR_INVALID_VIDEO_SPEED, DEFAULT_VIDEO_SPEED, VideoSpeedError, normalize_video_speed
from src.video_volume import (
    AR_INVALID_VOLUME_PERCENT,
    DEFAULT_VOLUME_PERCENT,
    VideoVolumeError,
    normalize_volume_percent,
)
from src.video_processor import (
    INPUT_VIDEO_NAME,
    TEMP_SEGMENTS_FOLDER_NAME,
    VideoProcessor,
    VideoProcessingError,
    VideoSourceError,
    VideoSourceRequest,
    VideoSourceType,
    probe_media_duration_seconds,
    sanitize_project_name,
    validate_local_video_file,
    validate_youtube_url,
)


NUMBER_COLUMN = 0
TITLE_COLUMN = 1
START_COLUMN = 2
END_COLUMN = 3
EXCLUSIONS_COLUMN = 4
RULE_NAME_COLUMN = 0
RULE_MIN_COLUMN = 1
RULE_MAX_COLUMN = 2
RULE_FOLDER_COLUMN = 3
QUEUE_SOURCE_COLUMN = 0
QUEUE_TITLE_COLUMN = 1
QUEUE_CLIP_COUNT_COLUMN = 2
QUEUE_STATUS_COLUMN = 3
QUEUE_HIGH_PRIORITY_COLUMN = 4
QUEUE_ACTION_COLUMN = 5
QUEUE_EDITABLE_STATUSES = {
    JobStatus.DRAFT,
    JobStatus.READY,
    JobStatus.VALIDATION_ERROR,
    JobStatus.WARNING,
    JobStatus.QUEUED,
}
QUEUE_TERMINAL_STATUSES = {
    JobStatus.DONE,
    JobStatus.FAILED,
    JobStatus.SKIPPED,
    JobStatus.CANCELLED,
}
AR_OPEN_MINUTES = "مفتوح"
SMART_PASTE_REPLACE_LABEL = "استبدال البيانات الحالية"
SMART_PASTE_APPEND_LABEL = "إضافة كمقاطع جديدة"
SMART_PASTE_QUEUE_LABEL = "إضافة كمهمة جديدة في قائمة الانتظار"
SMART_PASTE_CANCEL_LABEL = "إلغاء"


class IntentionalDoubleSpinBox(QDoubleSpinBox):
    """Spin box that ignores accidental wheel edits unless it has keyboard focus."""

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class IntentionalSpinBox(QSpinBox):
    """Spin box that ignores accidental wheel edits unless it has keyboard focus."""

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class SmartPasteImportDialog(QDialog):
    """Preview-only dialog for smart paste imports."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial_text: str = "",
        auto_generate: bool = False,
    ) -> None:
        super().__init__(parent)
        self.preview: SmartPastePreview | None = None

        self.setWindowTitle("استيراد ذكي")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(760, 620)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("الصق الرسالة كاملة هنا، بما في ذلك رابط الفيديو والمقاطع.")
        self.message_input.setMinimumHeight(120)

        self.summary_label = QLabel("الصق الرسالة ثم اضغط فحص الرسالة.")
        self.summary_label.setWordWrap(True)

        self.clips_preview_table = QTableWidget(0, 6)
        self.clips_preview_table.setHorizontalHeaderLabels(
            ["العنوان", "البداية", "النهاية", "الأجزاء", "الاستثناءات", "الملاحظات"]
        )
        self.clips_preview_table.verticalHeader().setVisible(False)
        self.clips_preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.clips_preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.warnings_area = QTextEdit()
        self.warnings_area.setReadOnly(True)
        self.warnings_area.setMaximumHeight(95)

        self.unparsed_area = QTextEdit()
        self.unparsed_area.setReadOnly(True)
        self.unparsed_area.setMaximumHeight(95)

        self.parse_button = QPushButton("فحص الرسالة")
        self.apply_button = QPushButton("تطبيق النتائج")
        self.cancel_button = QPushButton("إلغاء")
        self.apply_button.setEnabled(False)

        self._build_ui()
        self.parse_button.clicked.connect(self.generate_preview)
        self.apply_button.clicked.connect(self._accept_preview)
        self.cancel_button.clicked.connect(self.reject)
        if initial_text:
            self.message_input.setPlainText(initial_text)
        if auto_generate:
            self.generate_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("الصق الرسالة هنا"))
        layout.addWidget(self.message_input)
        layout.addWidget(self.parse_button)
        layout.addWidget(self.summary_label)
        layout.addWidget(QLabel("المقاطع المكتشفة"))
        layout.addWidget(self.clips_preview_table, stretch=1)
        layout.addWidget(QLabel("التحذيرات"))
        layout.addWidget(self.warnings_area)
        layout.addWidget(QLabel("أسطر تحتاج مراجعة"))
        layout.addWidget(self.unparsed_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

    def generate_preview(self) -> SmartPastePreview:
        self.preview = parse_smart_paste_message(self.message_input.toPlainText())
        self._show_preview(self.preview)
        return self.preview

    def _show_preview(self, preview: SmartPastePreview) -> None:
        needs_review = bool(preview.warnings or preview.unparsed_lines or any(clip.confidence != "high" for clip in preview.clips))
        self.summary_label.setText(
            "\n".join(
                [
                    f"عدد الروابط: {len(preview.video_urls)}",
                    f"عدد المقاطع: {len(preview.clips)}",
                    f"عدد التحذيرات: {len(preview.warnings)}",
                    "عدد الأخطاء: 0",
                    f"أسطر تحتاج مراجعة: {len(preview.unparsed_lines)}",
                    f"هل يوجد مقاطع تحتاج مراجعة: {'نعم' if needs_review else 'لا'}",
                    f"عنوان المشروع: {preview.project_title or 'غير مكتشف'}",
                    f"الرابط: {preview.video_urls[0] if preview.video_urls else 'غير مكتشف'}",
                ]
            )
        )

        self.clips_preview_table.setRowCount(0)
        for clip in preview.clips:
            row = self.clips_preview_table.rowCount()
            self.clips_preview_table.insertRow(row)
            self.clips_preview_table.setItem(row, 0, QTableWidgetItem(clip.title))
            self.clips_preview_table.setItem(row, 1, QTableWidgetItem(clip.start))
            self.clips_preview_table.setItem(row, 2, QTableWidgetItem(clip.end))
            self.clips_preview_table.setItem(row, 3, QTableWidgetItem(clip.parts_text))
            self.clips_preview_table.setItem(row, 4, QTableWidgetItem(clip.exclusions_text))
            self.clips_preview_table.setItem(row, 5, QTableWidgetItem(clip.notes_text))

        self.warnings_area.setPlainText(
            "\n".join(warning.message_ar for warning in preview.warnings) or "لا توجد تحذيرات."
        )
        self.unparsed_area.setPlainText(
            "\n".join(
                f"السطر {line.line_number}: {line.raw_line}"
                for line in preview.unparsed_lines
            )
            or "لا توجد أسطر غير مفهومة."
        )
        self.apply_button.setEnabled(bool(preview.video_urls or preview.clips))

    def _accept_preview(self) -> None:
        if self.preview is None:
            self.generate_preview()
        if self.preview is not None and (self.preview.video_urls or self.preview.clips):
            self.accept()


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
        classification_rules: list[ClassificationRule],
        clip_padding: ClipPadding,
        video_speed: float = DEFAULT_VIDEO_SPEED,
        volume_percent: int = DEFAULT_VOLUME_PERCENT,
    ) -> None:
        super().__init__()
        self.video_processor = video_processor
        self.source_request = source_request
        self.project_name = project_name
        self.clip_rows = clip_rows
        self.classification_rules = classification_rules
        self.clip_padding = clip_padding
        self.video_speed = video_speed
        self.volume_percent = volume_percent

    @Slot()
    def run(self) -> None:
        try:
            processing_result = self.video_processor.process_project(
                self.source_request,
                self.project_name,
                self.clip_rows,
                progress_callback=self.progress.emit,
                classification_rules=self.classification_rules,
                clip_padding=self.clip_padding,
                video_speed=self.video_speed,
                volume_percent=self.volume_percent,
            )
        except (VideoSourceError, VideoProcessingError, ExportError) as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"خطأ: {error}")
        else:
            self.succeeded.emit(str(processing_result.project_output_folder))
        finally:
            self.finished.emit()


class QueueProcessingWorker(QObject):
    """Runs queued local/YouTube jobs sequentially without blocking the main window."""

    progress = Signal(str)
    job_updated = Signal(int)
    finished = Signal()

    def __init__(
        self,
        jobs: list[VideoJob],
        video_processor: VideoProcessor,
        classification_rules: list[ClassificationRule],
    ) -> None:
        super().__init__()
        self.jobs = jobs
        self.video_processor = video_processor
        self.classification_rules = classification_rules
        self.processor: SequentialQueueProcessor | None = None

    @Slot()
    def run(self) -> None:
        self.processor = SequentialQueueProcessor(
            self.jobs,
            process_job=self._process_queue_job,
            progress_callback=self.progress.emit,
        )
        try:
            self.processor.run_until_idle()
        finally:
            for row in range(len(self.jobs)):
                self.job_updated.emit(row)
            self.finished.emit()

    @Slot()
    def request_stop(self) -> None:
        if self.processor is not None:
            self.processor.request_stop()

    def _process_queue_job(self, job: VideoJob) -> None:
        row = self._job_row(job)
        if row is not None:
            self.job_updated.emit(row)

        source_request = self._source_request_from_job(job)
        progress_callback = self._progress_callback_for_job(job)
        try:
            result = self.video_processor.process_project(
                source_request,
                job.title,
                self._clip_rows_from_job(job),
                progress_callback=progress_callback,
                classification_rules=self.classification_rules,
                clip_padding=ClipPadding(
                    pre_seconds=job.settings.pre_roll_seconds,
                    post_seconds=job.settings.post_roll_seconds,
                ),
                video_speed=self._effective_job_video_speed(job),
                volume_percent=self._effective_job_volume_percent(job),
            )
        except Exception as error:
            if job.source_type == QueueVideoSourceType.YOUTUBE:
                raise VideoProcessingError(f"فشل تحميل أو معالجة رابط يوتيوب: {error}") from error
            raise
        self.progress.emit(f"تم حفظ النتائج داخل: {result.project_output_folder}")

        row = self._job_row(job)
        if row is not None:
            self.job_updated.emit(row)

    def _effective_job_video_speed(self, job: VideoJob) -> float:
        return job.settings.speed if job.settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED

    def _effective_job_volume_percent(self, job: VideoJob) -> int:
        return job.settings.volume_percent if job.settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT

    def _source_request_from_job(self, job: VideoJob) -> VideoSourceRequest:
        if job.source_type == QueueVideoSourceType.LOCAL:
            return VideoSourceRequest(VideoSourceType.LOCAL_FILE, job.source)
        if job.source_type == QueueVideoSourceType.YOUTUBE:
            return VideoSourceRequest(
                VideoSourceType.YOUTUBE,
                job.source,
                use_browser_cookies=job.settings.use_browser_login,
                browser=job.settings.browser_name,
            )
        raise VideoProcessingError(AR_URL_QUEUE_PROCESSING_LATER)

    def _progress_callback_for_job(self, job: VideoJob):
        if job.source_type != QueueVideoSourceType.YOUTUBE:
            return self.progress.emit

        self.progress.emit("جاري تحميل الفيديو في الخلفية")
        cutting_message_sent = False

        def emit_progress(message: str) -> None:
            nonlocal cutting_message_sent
            self.progress.emit(message)
            if not cutting_message_sent and "تم تنزيل الفيديو" in message:
                cutting_message_sent = True
                self.progress.emit("جاري قص المقاطع في الخلفية")

        return emit_progress

    def _clip_rows_from_job(self, job: VideoJob) -> list[ClipRowInput]:
        return [
            ClipRowInput(
                row_number=index,
                title=clip.title,
                start=clip.start,
                end=clip.end,
                exclusions=clip.exclusions,
            )
            for index, clip in enumerate(job.clips, start=1)
        ]

    def _job_row(self, job: VideoJob) -> int | None:
        try:
            return self.jobs.index(job)
        except ValueError:
            return None


class MainWindow(QMainWindow):
    """Arabic-friendly initial application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.output_root = Path.cwd() / "output"
        self.video_processor = VideoProcessor(self.output_root)
        self.job_queue: list[VideoJob] = []
        self._processing_thread: QThread | None = None
        self._processing_worker: ProcessingWorker | None = None
        self._queue_processing_thread: QThread | None = None
        self._queue_processing_worker: QueueProcessingWorker | None = None
        self._queue_auto_continue_after_worker = False
        self._editing_queue_job: VideoJob | None = None
        self._last_output_folder: Path | None = None

        self.setWindowTitle(APP_NAME)
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1100, 820)

        self.youtube_radio = QRadioButton("رابط يوتيوب")
        self.local_file_radio = QRadioButton("فيديو من الجهاز")
        self.youtube_input = QLineEdit()
        self.local_file_input = QLineEdit()
        self.browse_button = QPushButton("اختيار فيديو")
        self.source_status_label = QLabel()
        self.use_browser_cookies_checkbox = QCheckBox("استخدام تسجيل الدخول من المتصفح")
        self.browser_combo = QComboBox()
        self.browser_cookies_help_label = QLabel()
        self.project_name_input = QLineEdit()
        self.paste_message_input = QTextEdit()
        self.smart_paste_button = QPushButton("استيراد ذكي")
        self.parse_message_button = QPushButton("تحويل بسيط إلى جدول")
        self.queue_table = QTableWidget(0, 6)
        self.add_current_work_to_queue_button = QPushButton("إضافة العمل الحالي إلى قائمة الانتظار")
        self.add_queue_local_video_button = QPushButton("إضافة فيديو محلي")
        self.add_queue_url_button = QPushButton("إضافة رابط")
        self.save_queue_clips_button = QPushButton("حفظ مقاطع المهمة المحددة")
        self.load_queue_clips_button = QPushButton("تحميل مقاطع المهمة المحددة")
        self.load_queue_job_workspace_button = QPushButton("تعديل المهمة المنتظرة")
        self.save_queue_job_edits_button = QPushButton("حفظ التعديلات على المهمة")
        self.cancel_queue_job_edit_button = QPushButton("إلغاء تعديل المهمة")
        self.save_queue_state_button = QPushButton("حفظ قائمة الانتظار")
        self.load_queue_state_button = QPushButton("تحميل قائمة انتظار")
        self.add_and_run_queue_job_button = QPushButton("إضافة وتشغيل في قائمة الانتظار")
        self.start_queue_processing_button = QPushButton("بدء معالجة قائمة الانتظار")
        self.stop_queue_after_current_button = QPushButton("إيقاف بعد المهمة الحالية")
        self.run_selected_queue_job_button = QPushButton("تشغيل المهمة المحددة")
        self.run_all_queue_simulation_button = QPushButton("فحص/محاكاة القائمة فقط")
        self.validate_queue_job_button = QPushButton("إعادة فحص المحدد")
        self.validate_all_queue_jobs_button = QPushButton("فحص كل قائمة الانتظار")
        self.delete_queue_job_button = QPushButton("إزالة المهمة المحددة")
        self.clear_queue_button = QPushButton("مسح القائمة")
        self.queue_selected_job_details_label = QLabel("اختر مهمة من قائمة الانتظار لعرض تفاصيلها.")
        self.queue_edit_status_label = QLabel("")
        self.queue_advanced_toggle_button = QPushButton("إدارة قائمة الانتظار المتقدمة")
        self.queue_advanced_group = QGroupBox("إدارة قائمة الانتظار المتقدمة")
        self.queue_advanced_controls_widget = QWidget()
        self.clips_table = QTableWidget(0, 5)
        self.classification_rules_table = QTableWidget(0, 4)
        self.add_row_button = QPushButton("إضافة مقطع")
        self.import_excel_button = QPushButton("استيراد من Excel")
        self.delete_row_button = QPushButton("حذف المقطع المحدد")
        self.clear_table_button = QPushButton("مسح الجدول")
        self.preview_clip_start_button = QPushButton("معاينة بداية المقطع")
        self.preview_clip_end_button = QPushButton("معاينة نهاية المقطع")
        self.preview_selected_clip_button = QPushButton("معاينة المقطع المحدد")
        self.add_classification_button = QPushButton("إضافة تصنيف")
        self.delete_classification_button = QPushButton("حذف التصنيف المحدد")
        self.reset_classification_button = QPushButton("استعادة الافتراضي")
        self.pre_padding_input = QDoubleSpinBox()
        self.post_padding_input = QDoubleSpinBox()
        self.video_speed_enabled_checkbox = QCheckBox("تعديل سرعة الفيديو")
        self.video_speed_input = IntentionalDoubleSpinBox()
        self.reset_video_speed_button = QPushButton("إعادة السرعة إلى 1.00x")
        self.video_speed_status_label = QLabel("الإعدادات الافتراضية آمنة")
        self.volume_enabled_checkbox = QCheckBox("تعديل مستوى الصوت")
        self.volume_input = IntentionalSpinBox()
        self.reset_volume_button = QPushButton("إعادة الصوت إلى 100%")
        self.volume_status_label = QLabel("الإعدادات الافتراضية آمنة")
        self.readiness_button = QPushButton("فحص جاهزية البرنامج")
        self.smart_validation_button = QPushButton("فحص ذكي قبل القص")
        self.validate_button = QPushButton("فحص ذكي قبل القص")
        self.start_button = QPushButton("بدء القص")
        self.direct_cut_button = QPushButton("بدء القص المباشر - وضع قديم")
        self.open_output_button = QPushButton("فتح مجلد النتائج")
        self.processing_status_label = QLabel("الحالة: جاهز")
        self.log_area = QTextEdit()
        self.scroll_area = QScrollArea()

        self._apply_branding()
        self.setCentralWidget(self._build_scrollable_ui())
        self._connect_signals()
        self._reset_classification_rules(log=False)
        self._update_source_inputs()
        self._update_speed_volume_controls()
        self._update_queue_edit_controls()
        self.open_output_button.setEnabled(False)
        self.stop_queue_after_current_button.setEnabled(False)

    def _build_scrollable_ui(self) -> QScrollArea:
        content = self._build_ui()
        self.scroll_area.setWidget(content)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return self.scroll_area

    def _build_ui(self) -> QWidget:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_video_source_section())
        layout.addWidget(self._build_project_section())
        layout.addWidget(self._build_help_section())
        layout.addWidget(self._build_paste_section())
        layout.addWidget(self._build_clips_section(), stretch=1)
        layout.addWidget(self._build_classification_section())
        layout.addWidget(self._build_padding_section())
        layout.addWidget(self._build_queue_section())
        layout.addWidget(self._build_action_section())
        layout.addWidget(self._build_log_section(), stretch=1)

        return central


    def _asset_path(self, filename: str) -> Path:
        # Works both from source and from a PyInstaller bundle.
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root) / "assets" / filename
        return Path(__file__).resolve().parent.parent / "assets" / filename

    def _apply_branding(self) -> None:
        icon_path = self._asset_path("icon.ico")
        if not icon_path.exists():
            icon_path = self._asset_path("icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_header_section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("appHeader")
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setObjectName("appLogo")
        logo_path = self._asset_path("logo.png")
        if not logo_path.exists():
            logo_path = self._asset_path("icon.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(160, 160)
        logo.setAlignment(Qt.AlignCenter)

        title_layout = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("appSubtitle")
        subtitle.setStyleSheet("font-size: 13px; color: #555;")
        subtitle.setWordWrap(True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        layout.addWidget(logo)
        layout.addLayout(title_layout, stretch=1)

        return frame

    def _build_video_source_section(self) -> QGroupBox:
        group = QGroupBox("مصدر الفيديو")
        layout = QGridLayout(group)

        source_group = QButtonGroup(self)
        source_group.addButton(self.youtube_radio)
        source_group.addButton(self.local_file_radio)
        self.youtube_radio.setChecked(True)

        self.youtube_input.setPlaceholderText("ضع رابط يوتيوب هنا")
        self.local_file_input.setPlaceholderText("اختر ملف فيديو من جهازك")
        self.local_file_input.setReadOnly(True)
        self.source_status_label.setText("المصدر النشط: رابط يوتيوب")
        self.browser_combo.addItems(["Chrome", "Edge", "Brave", "Firefox"])
        self.browser_cookies_help_label.setText(
            "إذا ظهر خطأ يوتيوب يطلب تسجيل الدخول أو التأكد أنك لست روبوتًا، "
            "فعّل هذا الخيار واختر المتصفح الذي تستخدمه لتسجيل الدخول إلى يوتيوب. "
            "يفضّل إغلاق المتصفح قبل بدء التنزيل."
        )
        self.browser_cookies_help_label.setWordWrap(True)

        layout.addWidget(self.youtube_radio, 0, 0)
        layout.addWidget(self.youtube_input, 0, 1, 1, 2)
        layout.addWidget(self.local_file_radio, 1, 0)
        layout.addWidget(self.local_file_input, 1, 1)
        layout.addWidget(self.browse_button, 1, 2)
        layout.addWidget(self.source_status_label, 2, 0, 1, 3)
        layout.addWidget(self.use_browser_cookies_checkbox, 3, 0)
        layout.addWidget(QLabel("المتصفح"), 3, 1)
        layout.addWidget(self.browser_combo, 3, 2)
        layout.addWidget(self.browser_cookies_help_label, 4, 0, 1, 3)
        layout.setColumnStretch(1, 1)

        return group

    def _build_project_section(self) -> QGroupBox:
        group = QGroupBox("اسم المشروع")
        layout = QGridLayout(group)

        self.project_name_input.setPlaceholderText("مثال: درس الجبر - الوحدة الأولى")

        layout.addWidget(QLabel("اسم المشروع"), 0, 0)
        layout.addWidget(self.project_name_input, 0, 1)
        layout.setColumnStretch(1, 1)

        return group

    def _build_queue_section(self) -> QGroupBox:
        group = QGroupBox("قائمة الانتظار")
        layout = QVBoxLayout(group)

        self.queue_table.setHorizontalHeaderLabels(
            ["المصدر", "العنوان", "عدد المقاطع", "الحالة", "أولوية عالية", "الإجراء"]
        )
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setMinimumHeight(130)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_SOURCE_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_TITLE_COLUMN, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_CLIP_COUNT_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_STATUS_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_HIGH_PRIORITY_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_ACTION_COLUMN, QHeaderView.Stretch)

        self.queue_selected_job_details_label.setWordWrap(True)
        self.queue_edit_status_label.setWordWrap(True)

        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(self.load_queue_job_workspace_button)
        edit_buttons.addWidget(self.save_queue_job_edits_button)
        edit_buttons.addWidget(self.cancel_queue_job_edit_button)
        edit_buttons.addStretch(1)

        self.queue_advanced_toggle_button.setCheckable(True)
        self.queue_advanced_toggle_button.setChecked(False)
        advanced_group_layout = QVBoxLayout(self.queue_advanced_group)
        advanced_controls_layout = QGridLayout(self.queue_advanced_controls_widget)
        advanced_buttons = [
            self.add_current_work_to_queue_button,
            self.add_queue_local_video_button,
            self.add_queue_url_button,
            self.validate_queue_job_button,
            self.validate_all_queue_jobs_button,
            self.run_selected_queue_job_button,
            self.run_all_queue_simulation_button,
            self.save_queue_clips_button,
            self.load_queue_clips_button,
            self.save_queue_state_button,
            self.load_queue_state_button,
            self.start_queue_processing_button,
            self.stop_queue_after_current_button,
            self.delete_queue_job_button,
            self.clear_queue_button,
            self.readiness_button,
            self.direct_cut_button,
        ]
        for index, button in enumerate(advanced_buttons):
            advanced_controls_layout.addWidget(button, index // 4, index % 4)
        advanced_controls_layout.setColumnStretch(4, 1)
        advanced_group_layout.addWidget(self.queue_advanced_controls_widget)
        self.queue_advanced_controls_widget.setVisible(False)
        self.queue_advanced_toggle_button.toggled.connect(self.queue_advanced_controls_widget.setVisible)

        layout.addWidget(self.queue_table)
        layout.addWidget(self.queue_selected_job_details_label)
        layout.addWidget(self.queue_edit_status_label)
        layout.addLayout(edit_buttons)
        layout.addWidget(self.queue_advanced_toggle_button)
        layout.addWidget(self.queue_advanced_group)

        return group

    def _build_help_section(self) -> QGroupBox:
        group = QGroupBox("تعليمات سريعة")
        layout = QVBoxLayout(group)

        help_text = QLabel(
            "اختر مصدر الفيديو، ثم أدخل اسم المشروع.\n"
            "أضف المقاطع يدويًا، أو استورد Excel، أو الصق رسالة.\n"
            "اضغط بدء القص عند جاهزية الجدول لإضافة المهمة إلى قائمة الانتظار.\n"
            "يمكن إنشاء أكثر من مجلد حسب مدة المقطع.\n"
            "مثال: من 0 إلى 3 دقائق = ريلز.\n"
            "مثال: من 3 إلى مفتوح = فوائد.\n"
            "يمكن إضافة تصنيفات أكثر مثل Shorts أو فوائد طويلة أو دروس."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        return group

    def _build_classification_section(self) -> QGroupBox:
        group = QGroupBox("إعدادات التصنيف والمجلدات")
        layout = QVBoxLayout(group)

        self.classification_rules_table.setHorizontalHeaderLabels(
            ["اسم التصنيف", "من دقيقة", "إلى دقيقة", "اسم المجلد"]
        )
        self.classification_rules_table.verticalHeader().setVisible(False)
        self.classification_rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.classification_rules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.classification_rules_table.setAlternatingRowColors(True)
        self.classification_rules_table.setMinimumHeight(110)
        self.classification_rules_table.horizontalHeader().setSectionResizeMode(RULE_NAME_COLUMN, QHeaderView.Stretch)
        self.classification_rules_table.horizontalHeader().setSectionResizeMode(RULE_MIN_COLUMN, QHeaderView.ResizeToContents)
        self.classification_rules_table.horizontalHeader().setSectionResizeMode(RULE_MAX_COLUMN, QHeaderView.ResizeToContents)
        self.classification_rules_table.horizontalHeader().setSectionResizeMode(RULE_FOLDER_COLUMN, QHeaderView.Stretch)

        button_row = QHBoxLayout()
        button_row.addWidget(self.add_classification_button)
        button_row.addWidget(self.delete_classification_button)
        button_row.addWidget(self.reset_classification_button)
        button_row.addStretch(1)

        layout.addWidget(self.classification_rules_table)
        layout.addLayout(button_row)

        return group

    def _build_paste_section(self) -> QGroupBox:
        group = QGroupBox("الصق الرسالة هنا")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("الصق الرسالة هنا"))
        self.paste_message_input.setPlaceholderText("الصق رسالة واتساب أو تيليجرام كاملة، ويمكن أن تحتوي على رابط الفيديو والمقاطع.")
        self.paste_message_input.setMinimumHeight(80)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.smart_paste_button)

        layout.addWidget(self.paste_message_input)
        layout.addLayout(button_row)

        return group

    def _build_padding_section(self) -> QGroupBox:
        group = QGroupBox("إعدادات القص")
        layout = QGridLayout(group)

        self._configure_padding_input(self.pre_padding_input)
        self._configure_padding_input(self.post_padding_input)
        self._configure_video_speed_input(self.video_speed_input)
        self._configure_volume_input(self.volume_input)

        layout.addWidget(QLabel("وقت قبل بداية المقطع"), 0, 0)
        layout.addWidget(self.pre_padding_input, 0, 1)
        layout.addWidget(QLabel("وقت بعد نهاية المقطع"), 0, 2)
        layout.addWidget(self.post_padding_input, 0, 3)
        layout.addWidget(self.video_speed_enabled_checkbox, 1, 0)
        layout.addWidget(QLabel("سرعة الفيديو"), 1, 1)
        layout.addWidget(self.video_speed_input, 1, 2)
        layout.addWidget(self.reset_video_speed_button, 1, 3)
        layout.addWidget(self.video_speed_status_label, 1, 4)
        layout.addWidget(self.volume_enabled_checkbox, 2, 0)
        layout.addWidget(QLabel("مستوى الصوت"), 2, 1)
        layout.addWidget(self.volume_input, 2, 2)
        layout.addWidget(self.reset_volume_button, 2, 3)
        layout.addWidget(self.volume_status_label, 2, 4)
        layout.setColumnStretch(4, 1)
        self.video_speed_status_label.setWordWrap(True)
        self.volume_status_label.setWordWrap(True)

        return group

    def _configure_padding_input(self, widget: QDoubleSpinBox) -> None:
        widget.setRange(0.0, 3600.0)
        widget.setDecimals(2)
        widget.setSingleStep(0.5)
        widget.setValue(0.0)
        widget.setSuffix(" ثانية")
        widget.setToolTip("الافتراضي: 0 ثانية")

    def _configure_video_speed_input(self, widget: QDoubleSpinBox) -> None:
        widget.setRange(0.75, 2.0)
        widget.setDecimals(2)
        widget.setSingleStep(0.05)
        widget.setValue(DEFAULT_VIDEO_SPEED)
        widget.setSuffix("x")
        widget.setToolTip("السرعة الافتراضية: 1.00x")
        widget.setFocusPolicy(Qt.StrongFocus)

    def _configure_volume_input(self, widget: QSpinBox) -> None:
        widget.setRange(75, 200)
        widget.setSingleStep(25)
        widget.setValue(DEFAULT_VOLUME_PERCENT)
        widget.setSuffix("%")
        widget.setToolTip("الصوت الافتراضي: 100%")
        widget.setFocusPolicy(Qt.StrongFocus)

    def reset_video_speed(self) -> None:
        self.video_speed_input.setValue(DEFAULT_VIDEO_SPEED)
        self._update_speed_volume_controls()

    def reset_volume(self) -> None:
        self.volume_input.setValue(DEFAULT_VOLUME_PERCENT)
        self._update_speed_volume_controls()

    def _update_speed_volume_controls(self, *_args) -> None:
        speed_enabled = self.video_speed_enabled_checkbox.isChecked()
        self.video_speed_input.setEnabled(speed_enabled)
        if not speed_enabled:
            self.video_speed_status_label.setText("الإعدادات الافتراضية آمنة")
        elif self.video_speed_input.value() < DEFAULT_VIDEO_SPEED:
            self.video_speed_status_label.setText("تبطيء الفيديو سيجعل مدة المقطع أطول")
        elif self.video_speed_input.value() > DEFAULT_VIDEO_SPEED:
            self.video_speed_status_label.setText("تسريع الفيديو قد يؤثر على وضوح الكلام إذا كانت القيمة عالية")
        else:
            self.video_speed_status_label.setText("السرعة الافتراضية")

        volume_enabled = self.volume_enabled_checkbox.isChecked()
        self.volume_input.setEnabled(volume_enabled)
        if not volume_enabled:
            self.volume_status_label.setText("الإعدادات الافتراضية آمنة")
        elif self.volume_input.value() < DEFAULT_VOLUME_PERCENT:
            self.volume_status_label.setText("مستوى الصوت أقل من الطبيعي وقد يجعل المقطع منخفض الصوت")
        elif self.volume_input.value() > DEFAULT_VOLUME_PERCENT:
            self.volume_status_label.setText("رفع الصوت قد يسبب تشويشًا إذا كان الصوت الأصلي عاليًا")
        else:
            self.volume_status_label.setText("الصوت الافتراضي")

    def _build_clips_section(self) -> QGroupBox:
        group = QGroupBox("جدول المقاطع")
        layout = QVBoxLayout(group)

        self.clips_table.setHorizontalHeaderLabels(["الرقم", "العنوان", "البداية", "النهاية", "استثناءات"])
        self.clips_table.verticalHeader().setVisible(False)
        self.clips_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.clips_table.setAlternatingRowColors(True)
        self.clips_table.setMinimumHeight(180)
        self.clips_table.horizontalHeader().setSectionResizeMode(NUMBER_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(TITLE_COLUMN, QHeaderView.Stretch)
        self.clips_table.horizontalHeader().setSectionResizeMode(START_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(END_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(EXCLUSIONS_COLUMN, QHeaderView.Stretch)

        table_buttons = QHBoxLayout()
        table_buttons.addWidget(self.add_row_button)
        table_buttons.addWidget(self.delete_row_button)
        table_buttons.addWidget(self.clear_table_button)
        table_buttons.addStretch(1)
        table_buttons.addWidget(self.import_excel_button)

        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(self.preview_clip_start_button)
        preview_buttons.addWidget(self.preview_clip_end_button)
        preview_buttons.addWidget(self.preview_selected_clip_button)
        preview_buttons.addStretch(1)

        layout.addWidget(self.clips_table)
        layout.addLayout(table_buttons)
        layout.addLayout(preview_buttons)

        return group

    def _build_action_section(self) -> QGroupBox:
        group = QGroupBox("أزرار التشغيل")
        layout = QHBoxLayout(group)

        layout.addWidget(self.start_button)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.open_output_button)
        layout.addStretch(1)
        layout.addWidget(self.processing_status_label)
        self.add_and_run_queue_job_button.setVisible(False)

        return group

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("سجل الحالة")
        layout = QVBoxLayout(group)

        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("ستظهر رسائل الفحص والتقدم هنا.")
        layout.addWidget(self.log_area)

        return group

    def _connect_signals(self) -> None:
        self.youtube_radio.toggled.connect(self._update_source_inputs)
        self.local_file_radio.toggled.connect(self._update_source_inputs)
        self.use_browser_cookies_checkbox.toggled.connect(self._update_source_inputs)
        self.browse_button.clicked.connect(self._browse_local_video)
        self.add_row_button.clicked.connect(self.add_clip_row)
        self.import_excel_button.clicked.connect(self.import_from_excel)
        self.delete_row_button.clicked.connect(self.delete_selected_row)
        self.clear_table_button.clicked.connect(self.clear_table)
        self.preview_clip_start_button.clicked.connect(self.preview_selected_clip_start)
        self.preview_clip_end_button.clicked.connect(self.preview_selected_clip_end)
        self.preview_selected_clip_button.clicked.connect(self.preview_selected_clip)
        self.add_classification_button.clicked.connect(self.add_classification_rule)
        self.delete_classification_button.clicked.connect(self.delete_selected_classification_rule)
        self.reset_classification_button.clicked.connect(self.reset_classification_rules)
        self.video_speed_enabled_checkbox.toggled.connect(self._update_speed_volume_controls)
        self.video_speed_input.valueChanged.connect(self._update_speed_volume_controls)
        self.reset_video_speed_button.clicked.connect(self.reset_video_speed)
        self.volume_enabled_checkbox.toggled.connect(self._update_speed_volume_controls)
        self.volume_input.valueChanged.connect(self._update_speed_volume_controls)
        self.reset_volume_button.clicked.connect(self.reset_volume)
        self.add_current_work_to_queue_button.clicked.connect(self.add_current_work_to_queue)
        self.add_queue_local_video_button.clicked.connect(self.add_local_video_to_queue)
        self.add_queue_url_button.clicked.connect(self.add_url_to_queue)
        self.save_queue_clips_button.clicked.connect(self.save_clips_to_selected_queue_job)
        self.load_queue_clips_button.clicked.connect(self.load_clips_from_selected_queue_job)
        self.load_queue_job_workspace_button.clicked.connect(self.edit_waiting_queue_job)
        self.save_queue_job_edits_button.clicked.connect(self.save_waiting_queue_job_edits)
        self.cancel_queue_job_edit_button.clicked.connect(self.cancel_waiting_queue_job_edit)
        self.save_queue_state_button.clicked.connect(self.save_queue_state)
        self.load_queue_state_button.clicked.connect(self.load_queue_state)
        self.add_and_run_queue_job_button.clicked.connect(self.add_current_work_and_start_queue)
        self.start_queue_processing_button.clicked.connect(self.start_queue_processing)
        self.stop_queue_after_current_button.clicked.connect(self.stop_queue_after_current_job)
        self.run_selected_queue_job_button.clicked.connect(self.run_selected_queue_job)
        self.run_all_queue_simulation_button.clicked.connect(self.run_all_queue_simulation)
        self.validate_queue_job_button.clicked.connect(self.validate_selected_queue_job)
        self.validate_all_queue_jobs_button.clicked.connect(self.validate_all_queue_jobs)
        self.delete_queue_job_button.clicked.connect(self.delete_selected_queue_job)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.queue_table.itemChanged.connect(self._sync_queue_high_priority)
        self.queue_table.itemSelectionChanged.connect(self._update_queue_edit_controls)
        self.queue_table.currentCellChanged.connect(self._update_queue_edit_controls)
        self.smart_paste_button.clicked.connect(self.import_smart_paste_message)
        self.parse_message_button.clicked.connect(self.convert_pasted_text_to_table)
        self.readiness_button.clicked.connect(self.check_readiness)
        self.smart_validation_button.clicked.connect(self.validate_before_cutting)
        self.validate_button.clicked.connect(self.validate_before_cutting)
        self.start_button.clicked.connect(self.add_current_work_and_start_queue)
        self.direct_cut_button.clicked.connect(self.start_direct_processing_with_confirmation)
        self.open_output_button.clicked.connect(self.open_output_folder)


    def add_clip_row(self) -> None:
        self._insert_clip_row(
            number=self.clips_table.rowCount() + 1,
            title="",
            start="",
            end="",
            exclusions="",
        )
        self.clips_table.setCurrentCell(self.clips_table.rowCount() - 1, TITLE_COLUMN)

    def _insert_clip_row(self, number: int, title: str, start: str, end: str, exclusions: str = "") -> None:
        row = self.clips_table.rowCount()
        self.clips_table.insertRow(row)

        number_item = QTableWidgetItem(str(number))
        number_item.setFlags(number_item.flags() & ~Qt.ItemIsEditable)
        number_item.setTextAlignment(Qt.AlignCenter)

        self.clips_table.setItem(row, NUMBER_COLUMN, number_item)
        self.clips_table.setItem(row, TITLE_COLUMN, QTableWidgetItem(title))
        self.clips_table.setItem(row, START_COLUMN, QTableWidgetItem(start))
        self.clips_table.setItem(row, END_COLUMN, QTableWidgetItem(end))
        self.clips_table.setItem(row, EXCLUSIONS_COLUMN, QTableWidgetItem(exclusions))

    def preview_selected_clip_start(self) -> None:
        self._preview_selected_clip(ClipPreviewKind.START)

    def preview_selected_clip_end(self) -> None:
        self._preview_selected_clip(ClipPreviewKind.END)

    def preview_selected_clip(self) -> None:
        self._preview_selected_clip(ClipPreviewKind.FULL)

    def add_local_video_to_queue(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "إضافة فيديو محلي إلى قائمة الانتظار",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.webm);;All Files (*.*)",
        )
        if not file_path:
            return

        self._add_queue_local_file_job(file_path)
        self._write_log("تمت إضافة فيديو محلي إلى قائمة الانتظار. لن يبدأ التحميل أو القص تلقائيًا.")

    def add_url_to_queue(self) -> None:
        url, accepted = QInputDialog.getText(
            self,
            "إضافة رابط إلى قائمة الانتظار",
            "أدخل رابط الفيديو",
        )
        if not accepted or not url.strip():
            return

        self._add_queue_url_job(url.strip())
        self._write_log("تمت إضافة الرابط إلى قائمة الانتظار. لن يبدأ التحميل أو القص تلقائيًا.")

    def _add_queue_local_file_job(self, file_path: str) -> VideoJob:
        path = Path(file_path)
        title = path.stem or path.name or "فيديو محلي"
        return self._add_queue_job(QueueVideoSourceType.LOCAL, str(path), title)

    def _add_queue_url_job(self, url: str, title: str | None = None) -> VideoJob:
        source_type = self._infer_queue_url_source_type(url)
        job_title = title or self.project_name_input.text().strip() or url
        return self._add_queue_job(source_type, url, job_title)

    def _add_queue_job(
        self,
        source_type: QueueVideoSourceType | str,
        source: str,
        title: str,
        clips: list[ClipJob] | None = None,
        settings: JobSettings | None = None,
        status: JobStatus = JobStatus.DRAFT,
    ) -> VideoJob:
        job = VideoJob(
            source_type=source_type,
            source=source,
            title=title.strip() or source,
            clips=list(clips or []),
            settings=settings or JobSettings(),
            status=status,
        )
        self.job_queue.append(job)
        self._insert_queue_job_row(job)
        return job

    def add_current_work_to_queue(self) -> None:
        source_snapshot = self._current_work_queue_source()
        if source_snapshot is None:
            return

        source_type, source, title = source_snapshot
        if self.clips_table.rowCount() == 0:
            if not self._ask_add_current_work_without_clips_confirmation():
                self._write_log("لا توجد مقاطع في الجدول")
                return
            log_prefix = "لا توجد مقاطع في الجدول\n"
        else:
            log_prefix = ""

        job = self._add_queue_job(
            source_type,
            source,
            title,
            clips=self._clip_jobs_from_current_table(),
            settings=self._current_job_settings_snapshot(),
        )
        self.queue_table.setCurrentCell(self.job_queue.index(job), QUEUE_SOURCE_COLUMN)
        self._write_log(
            f"{log_prefix}تم إضافة العمل الحالي إلى قائمة الانتظار\n"
            "لم يتم بدء أي قص أو تحميل"
        )

    def add_current_work_and_start_queue(self) -> None:
        if self._editing_queue_job is not None:
            if self._ask_save_waiting_job_edit_instead_confirmation():
                if self.save_waiting_queue_job_edits():
                    self.start_queue_processing()
            else:
                self._write_log("لم يتم إنشاء مهمة جديدة")
            return

        source_snapshot = self._current_work_queue_source()
        if source_snapshot is None:
            return

        source_type, source, title = source_snapshot
        if self.clips_table.rowCount() == 0:
            if not self._ask_add_current_work_without_clips_confirmation():
                self._write_log("لا توجد مقاطع في الجدول")
                return
            log_prefix = "لا توجد مقاطع في الجدول\n"
        else:
            log_prefix = ""

        job = self._add_queue_job(
            source_type,
            source,
            title,
            clips=self._clip_jobs_from_current_table(),
            settings=self._current_job_settings_snapshot(),
            status=JobStatus.QUEUED,
        )
        self.queue_table.setCurrentCell(self.job_queue.index(job), QUEUE_SOURCE_COLUMN)
        self._write_log(
            f"{log_prefix}{AR_QUEUE_JOB_ADDED}\n"
            f"{AR_QUEUE_JOB_WAITING}\n"
            f"{AR_QUEUE_CAN_PREPARE_NEXT}"
        )
        self.start_queue_processing()

    def _ask_save_waiting_job_edit_instead_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("حفظ التعديلات على المهمة")
        dialog.setText("أنت تعدل مهمة منتظرة. هل تريد حفظ التعديلات على المهمة بدل إضافة مهمة جديدة؟")
        save_button = dialog.addButton("حفظ التعديلات", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(save_button)
        dialog.exec()
        return dialog.clickedButton() == save_button

    def _current_work_queue_source(self) -> tuple[QueueVideoSourceType, str, str] | None:
        project_title = self.project_name_input.text().strip()

        if self.local_file_radio.isChecked():
            source = self.local_file_input.text().strip()
            if not source:
                self._write_log("لا يوجد مصدر فيديو لإضافته")
                return None
            title = project_title or Path(source).stem or Path(source).name or "فيديو محلي"
            return QueueVideoSourceType.LOCAL, source, title

        source = self.youtube_input.text().strip()
        if not source:
            self._write_log("لا يوجد مصدر فيديو لإضافته")
            return None

        source_type = self._supported_queue_url_source_type(source)
        if source_type is None:
            if self._has_youtube_host(source):
                self._write_log("رابط يوتيوب غير صالح")
            else:
                self._write_log("الرابط غير مدعوم حاليًا")
            return None

        return source_type, source, project_title or source

    def _supported_queue_url_source_type(self, url: str) -> QueueVideoSourceType | None:
        if self._is_supported_youtube_video_url(url):
            return QueueVideoSourceType.YOUTUBE
        lowered_url = url.lower()
        if "facebook.com" in lowered_url or "fb.watch" in lowered_url:
            return QueueVideoSourceType.FACEBOOK
        return None

    def _is_supported_youtube_video_url(self, url: str) -> bool:
        normalized_url = url.strip()
        if "://" not in normalized_url:
            normalized_url = f"https://{normalized_url}"

        parts = urlsplit(normalized_url)
        host = parts.netloc.lower()
        path = parts.path.strip("/")
        if host.startswith("www."):
            host = host[4:]
        if host.startswith("m."):
            host = host[2:]

        if host == "youtu.be":
            return bool(path)
        if host != "youtube.com":
            return False
        if path == "watch":
            return bool(parse_qs(parts.query).get("v", [""])[0].strip())
        return path.startswith("live/") or path.startswith("shorts/")

    def _has_youtube_host(self, url: str) -> bool:
        lowered_url = url.lower()
        return "youtube.com" in lowered_url or "youtu.be" in lowered_url

    def _ask_add_current_work_without_clips_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("إضافة العمل الحالي إلى قائمة الانتظار")
        dialog.setText("لا توجد مقاطع في الجدول. هل تريد إضافة المهمة بدون مقاطع؟")
        add_button = dialog.addButton("إضافة", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(add_button)
        dialog.exec()
        return dialog.clickedButton() == add_button

    def _insert_queue_job_row(self, job: VideoJob) -> None:
        row = self.queue_table.rowCount()
        self.queue_table.blockSignals(True)
        try:
            self.queue_table.insertRow(row)
            self.queue_table.setItem(row, QUEUE_SOURCE_COLUMN, self._readonly_table_item(self._queue_source_label(job)))
            self.queue_table.item(row, QUEUE_SOURCE_COLUMN).setToolTip(job.source)
            self.queue_table.setItem(row, QUEUE_TITLE_COLUMN, self._readonly_table_item(job.title))
            self.queue_table.setItem(row, QUEUE_CLIP_COUNT_COLUMN, self._readonly_table_item(str(job.clip_count)))
            self.queue_table.setItem(row, QUEUE_STATUS_COLUMN, self._readonly_table_item(self._queue_status_label(job.status)))

            priority_item = self._readonly_table_item("")
            priority_item.setCheckState(Qt.Checked if job.settings.high_priority else Qt.Unchecked)
            priority_item.setTextAlignment(Qt.AlignCenter)
            self.queue_table.setItem(row, QUEUE_HIGH_PRIORITY_COLUMN, priority_item)

            self.queue_table.setItem(row, QUEUE_ACTION_COLUMN, self._readonly_table_item(self._queue_settings_summary(job)))
        finally:
            self.queue_table.blockSignals(False)
        self._update_queue_edit_controls()

    def _readonly_table_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _infer_queue_url_source_type(self, url: str) -> QueueVideoSourceType:
        lowered_url = url.lower()
        if "facebook.com" in lowered_url or "fb.watch" in lowered_url:
            return QueueVideoSourceType.FACEBOOK
        return QueueVideoSourceType.YOUTUBE

    def _queue_source_label(self, job: VideoJob) -> str:
        labels = {
            QueueVideoSourceType.LOCAL: "فيديو محلي",
            QueueVideoSourceType.YOUTUBE: "رابط يوتيوب",
            QueueVideoSourceType.FACEBOOK: "رابط Facebook",
        }
        return labels[job.source_type]

    def _queue_status_label(self, status: JobStatus) -> str:
        labels = {
            JobStatus.DRAFT: "مسودة",
            JobStatus.READY: "جاهز",
            JobStatus.VALIDATION_ERROR: "خطأ في الفحص",
            JobStatus.WARNING: "تحذير",
            JobStatus.QUEUED: "في الانتظار",
            JobStatus.DOWNLOADING: "جاري التحميل",
            JobStatus.CUTTING: "جاري القص",
            JobStatus.VERIFYING: "جاري التحقق",
            JobStatus.DONE: "مكتمل",
            JobStatus.FAILED: "فشل",
            JobStatus.SKIPPED: "تم تجاوزه",
            JobStatus.CANCELLED: "ملغى",
        }
        return labels[status]

    def _queue_settings_summary(self, job: VideoJob) -> str:
        speed_state = "مفعّلة" if job.settings.speed_adjustment_enabled else "غير مفعّلة"
        speed_value = job.settings.speed if job.settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED
        volume_state = "مفعّل" if job.settings.volume_adjustment_enabled else "غير مفعّل"
        volume_value = job.settings.volume_percent if job.settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT
        return (
            f"السرعة: {speed_state} ({speed_value:.2f}x) | "
            f"الصوت: {volume_state} ({volume_value}%)"
        )

    def _queue_job_can_be_edited(self, job: VideoJob) -> bool:
        return job.status in QUEUE_EDITABLE_STATUSES and not self._queue_job_is_running(job)

    def _queue_job_edit_block_reason(self, job: VideoJob) -> str | None:
        if self._queue_job_is_running(job):
            return "لا يمكن تعديل المهمة الجارية"
        if job.status in QUEUE_TERMINAL_STATUSES:
            return "لا يمكن تعديل مهمة مكتملة. أعد إضافتها كمهمة جديدة."
        if job.status not in QUEUE_EDITABLE_STATUSES:
            return "لا يمكن تعديل مهمة مكتملة. أعد إضافتها كمهمة جديدة."
        return None

    def _update_queue_edit_controls(self, *_args) -> None:
        row = self._selected_queue_row()
        selected_job = self.job_queue[row] if row is not None and 0 <= row < len(self.job_queue) else None
        editing_active = self._editing_queue_job is not None
        editing_job_in_queue = any(job is self._editing_queue_job for job in self.job_queue)
        editing_job_can_be_saved = (
            self._editing_queue_job is not None
            and editing_job_in_queue
            and self._queue_job_can_be_edited(self._editing_queue_job)
        )

        self.load_queue_job_workspace_button.setEnabled(
            selected_job is not None and self._queue_job_can_be_edited(selected_job)
        )
        self.save_queue_job_edits_button.setEnabled(editing_job_can_be_saved)
        self.cancel_queue_job_edit_button.setEnabled(editing_active)

        if selected_job is None:
            self.queue_selected_job_details_label.setText("اختر مهمة من قائمة الانتظار لعرض تفاصيلها.")
        else:
            self.queue_selected_job_details_label.setText(
                "\n".join(
                    [
                        f"المهمة المحددة: {selected_job.title}",
                        self._queue_settings_summary(selected_job),
                        f"الحالة: {self._queue_status_label(selected_job.status)}",
                    ]
                )
            )

        if editing_active:
            if editing_job_can_be_saved:
                self.queue_edit_status_label.setText("أنت تعدل مهمة منتظرة من قائمة الانتظار")
            else:
                self.queue_edit_status_label.setText("لا يمكن تعديل المهمة بعد بدء معالجتها")
        else:
            self.queue_edit_status_label.setText("")

    def _sync_queue_high_priority(self, item: QTableWidgetItem) -> None:
        if item.column() != QUEUE_HIGH_PRIORITY_COLUMN:
            return
        row = item.row()
        if 0 <= row < len(self.job_queue):
            job = self.job_queue[row]
            if self._queue_job_is_running(job):
                self.queue_table.blockSignals(True)
                try:
                    item.setCheckState(Qt.Checked if job.settings.high_priority else Qt.Unchecked)
                finally:
                    self.queue_table.blockSignals(False)
                self._append_log("لا يمكن تعديل المهمة الجارية")
                return
            job.settings.high_priority = item.checkState() == Qt.Checked
            self._update_queue_edit_controls()

    def validate_selected_queue_job(self) -> None:
        row = self._selected_queue_row()
        if row is None:
            self._write_log("لا توجد مهمة محددة")
            return

        job = self.job_queue[row]
        if self._queue_job_is_running(job):
            self._write_log("لا يمكن تعديل المهمة الجارية")
            return

        result = validate_queue_job(job)
        apply_queue_validation_result(job, result)
        self._refresh_queue_job_row(row)
        self._write_log("تم فحص المهمة المحددة\n" + format_queue_validation_result_ar(result))

    def validate_all_queue_jobs(self) -> None:
        if not self.job_queue:
            self._write_log("لا توجد مهام في قائمة الانتظار")
            return

        ready_count = 0
        warning_count = 0
        error_count = 0
        error_jobs: list[str] = []
        for row, job in enumerate(self.job_queue):
            if self._queue_job_is_running(job):
                warning_count += 1
                self._refresh_queue_job_row(row)
                continue

            result = validate_queue_job(job)
            apply_queue_validation_result(job, result)
            self._refresh_queue_job_row(row)
            if result.status == JobStatus.READY:
                ready_count += 1
            elif result.status == JobStatus.WARNING:
                warning_count += 1
            elif result.status == JobStatus.VALIDATION_ERROR:
                error_count += 1
                error_jobs.append(f"{row + 1} - {job.title}: لا يمكن بدء المهمة قبل إصلاح الأخطاء")

        self._write_log(
            self._format_validate_all_queue_summary(
                total=len(self.job_queue),
                ready=ready_count,
                warnings=warning_count,
                errors=error_count,
                error_jobs=error_jobs,
            )
        )

    def _format_validate_all_queue_summary(
        self,
        *,
        total: int,
        ready: int,
        warnings: int,
        errors: int,
        error_jobs: list[str],
    ) -> str:
        lines = [
            "تم فحص كل قائمة الانتظار",
            f"عدد المهام: {total}",
            f"المهام الجاهزة: {ready}",
            f"المهام التي فيها تحذيرات: {warnings}",
            f"المهام التي فيها أخطاء: {errors}",
        ]
        if errors:
            lines.extend(error_jobs)
            lines.append("لا يمكن تشغيل القائمة قبل إصلاح الأخطاء")
        else:
            lines.append("يمكن تشغيل القائمة لاحقًا")
        lines.append("لم يتم بدء أي قص أو تحميل")
        return "\n".join(lines)

    def save_clips_to_selected_queue_job(self) -> None:
        row = self._selected_queue_row()
        if row is None:
            self._write_log("لا توجد مهمة محددة")
            return

        if self.clips_table.rowCount() == 0:
            self._write_log("لا توجد مقاطع لحفظها")
            return

        job = self.job_queue[row]
        if self._queue_job_is_running(job):
            self._write_log("لا يمكن تعديل المهمة الجارية")
            return

        if job.clips and not self._ask_replace_queue_clips_confirmation():
            return

        job.clips = self._clip_jobs_from_current_table()
        self._refresh_queue_job_row(row)
        self._write_log(
            "تم حفظ المقاطع للمهمة المحددة\n"
            "تم تحديث عدد المقاطع\n"
            "لم يتم بدء أي قص أو تحميل"
        )

    def _clip_jobs_from_current_table(self) -> list[ClipJob]:
        return [
            ClipJob(
                title=self._cell_text(row, TITLE_COLUMN),
                start=self._cell_text(row, START_COLUMN),
                end=self._cell_text(row, END_COLUMN),
                exclusions=self._cell_text(row, EXCLUSIONS_COLUMN),
            )
            for row in range(self.clips_table.rowCount())
        ]

    def _current_job_settings_snapshot(self) -> JobSettings:
        return JobSettings(
            pre_roll_seconds=self.pre_padding_input.value(),
            post_roll_seconds=self.post_padding_input.value(),
            speed_adjustment_enabled=self.video_speed_enabled_checkbox.isChecked(),
            speed=self._collect_video_speed(),
            volume_adjustment_enabled=self.volume_enabled_checkbox.isChecked(),
            volume_percent=self._collect_volume_percent(),
            use_browser_login=self.use_browser_cookies_checkbox.isChecked(),
            browser_name=self._selected_browser_identifier(),
        )

    def _ask_replace_queue_clips_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("استبدال المقاطع المحفوظة")
        dialog.setText("هذه المهمة تحتوي على مقاطع محفوظة. هل تريد استبدالها؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(replace_button)
        dialog.exec()
        return dialog.clickedButton() == replace_button

    def load_clips_from_selected_queue_job(self) -> None:
        row = self._selected_queue_row()
        if row is None:
            self._write_log("لا توجد مهمة محددة")
            return

        job = self.job_queue[row]
        if not job.clips:
            self._write_log("لا توجد مقاطع محفوظة لهذه المهمة")
            return

        replaced_existing = False
        if self.clips_table.rowCount() > 0:
            if not self._ask_replace_current_clip_table_confirmation():
                return
            replaced_existing = True

        self.clips_table.setRowCount(0)
        for index, clip in enumerate(job.clips, start=1):
            self._insert_clip_row(
                index,
                clip.title,
                clip.start,
                clip.end,
                clip.exclusions,
            )

        messages = []
        if replaced_existing:
            messages.append("تم استبدال مقاطع الجدول")
        messages.extend(["تم تحميل مقاطع المهمة المحددة", "لم يتم بدء أي قص أو تحميل"])
        self._write_log("\n".join(messages))

    def _ask_replace_current_clip_table_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("تحميل مقاطع المهمة المحددة")
        dialog.setText("يوجد مقاطع حالية في الجدول. هل تريد استبدالها؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(replace_button)
        dialog.exec()
        return dialog.clickedButton() == replace_button

    def load_selected_queue_job_to_workspace(self) -> None:
        self.edit_waiting_queue_job()

    def edit_waiting_queue_job(self) -> None:
        row = self._selected_queue_row()
        if row is None:
            self._write_log("لا توجد مهمة محددة")
            return

        job = self.job_queue[row]
        block_reason = self._queue_job_edit_block_reason(job)
        if block_reason:
            self._write_log(block_reason)
            self._update_queue_edit_controls()
            return

        if not job.source.strip():
            self._write_log("لا يوجد مصدر محفوظ لهذه المهمة")
            return

        replaced_source = self._workspace_source_has_data(job)
        if replaced_source and not self._ask_replace_workspace_source_confirmation():
            return

        replaced_clips = False
        missing_clips = False
        if job.clips:
            if self.clips_table.rowCount() > 0:
                if not self._ask_replace_current_clip_table_confirmation():
                    return
                replaced_clips = True
        else:
            missing_clips = True

        self._apply_queue_job_source_to_workspace(job)
        if job.clips:
            self._load_clip_jobs_to_table(job.clips)

        if job.title.strip():
            self.project_name_input.setText(job.title.strip())
        self._apply_queue_job_settings_to_workspace(job.settings)
        self._editing_queue_job = job

        messages = []
        if replaced_source:
            messages.append("تم استبدال مصدر الفيديو الحالي")
        if replaced_clips:
            messages.append("تم استبدال مقاطع الجدول")
        if missing_clips:
            messages.append("لا توجد مقاطع محفوظة لهذه المهمة")
        messages.extend(["أنت تعدل مهمة منتظرة من قائمة الانتظار", "لم يتم بدء أي قص أو تحميل"])
        self._write_log("\n".join(messages))
        self._update_queue_edit_controls()

    def save_waiting_queue_job_edits(self) -> bool:
        job = self._editing_queue_job
        if job is None:
            self._write_log("لا توجد مهمة محددة")
            return False

        row = next((index for index, queued_job in enumerate(self.job_queue) if queued_job is job), None)
        if row is None:
            self._editing_queue_job = None
            self._write_log("لا توجد مهمة محددة")
            self._update_queue_edit_controls()
            return False

        if self._queue_job_is_running(job):
            self._editing_queue_job = None
            self._write_log("لا يمكن تعديل المهمة بعد بدء معالجتها")
            self._update_queue_edit_controls()
            return False

        block_reason = self._queue_job_edit_block_reason(job)
        if block_reason:
            self._editing_queue_job = None
            self._write_log(block_reason)
            self._update_queue_edit_controls()
            return False

        high_priority = job.settings.high_priority
        if not self._replace_queue_job_snapshot_from_workspace(job):
            return False
        job.settings.high_priority = high_priority
        self._refresh_queue_job_row(row)
        self._editing_queue_job = None
        self._write_log("تم حفظ التعديلات على المهمة\nلم يتم بدء أي قص أو تحميل")
        self._update_queue_edit_controls()
        return True

    def cancel_waiting_queue_job_edit(self) -> None:
        if self._editing_queue_job is None:
            self._write_log("لا توجد مهمة محددة")
            return

        self._editing_queue_job = None
        self._write_log("تم إلغاء تعديل المهمة")
        self._update_queue_edit_controls()

    def _replace_queue_job_snapshot_from_workspace(self, job: VideoJob) -> bool:
        source_snapshot = self._current_work_queue_source()
        if source_snapshot is None:
            return False

        source_type, source, title = source_snapshot
        job.source_type = source_type
        job.source = source
        job.title = title
        job.clips = self._clip_jobs_from_current_table()
        job.settings = self._current_job_settings_snapshot()
        return True

    def _load_clip_jobs_to_table(self, clips: list[ClipJob]) -> None:
        self.clips_table.setRowCount(0)
        for index, clip in enumerate(clips, start=1):
            self._insert_clip_row(
                index,
                clip.title,
                clip.start,
                clip.end,
                clip.exclusions,
            )

    def _workspace_source_has_data(self, job: VideoJob) -> bool:
        current_sources = [
            self.youtube_input.text().strip(),
            self.local_file_input.text().strip(),
        ]
        return any(source and source != job.source for source in current_sources)

    def _apply_queue_job_source_to_workspace(self, job: VideoJob) -> None:
        if job.source_type == QueueVideoSourceType.LOCAL:
            self.local_file_radio.setChecked(True)
            self.local_file_input.setText(job.source)
        else:
            self.youtube_radio.setChecked(True)
            self.youtube_input.setText(job.source)
        self._update_source_inputs()

    def _apply_queue_job_settings_to_workspace(self, settings: JobSettings) -> None:
        self.pre_padding_input.setValue(max(0.0, settings.pre_roll_seconds))
        self.post_padding_input.setValue(max(0.0, settings.post_roll_seconds))
        self.use_browser_cookies_checkbox.setChecked(settings.use_browser_login)
        self._set_browser_combo_from_identifier(settings.browser_name)
        self.video_speed_enabled_checkbox.setChecked(settings.speed_adjustment_enabled)
        self.video_speed_input.setValue(settings.speed if settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED)
        self.volume_enabled_checkbox.setChecked(settings.volume_adjustment_enabled)
        self.volume_input.setValue(
            settings.volume_percent if settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT
        )
        self._update_speed_volume_controls()
        self._update_source_inputs()

    def _set_browser_combo_from_identifier(self, browser_name: str) -> None:
        labels = {
            "chrome": "Chrome",
            "edge": "Edge",
            "brave": "Brave",
            "firefox": "Firefox",
        }
        self.browser_combo.setCurrentText(labels.get(browser_name.lower(), "Chrome"))

    def _ask_replace_workspace_source_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("تعديل المهمة المنتظرة")
        dialog.setText("يوجد مصدر فيديو حالي. هل تريد استبداله؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(replace_button)
        dialog.exec()
        return dialog.clickedButton() == replace_button

    def save_queue_state(self) -> None:
        if not self.job_queue:
            self._write_log("لا توجد مهام لحفظها")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "حفظ قائمة الانتظار",
            "queue.json",
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            save_queue_jobs(self.job_queue, self._json_file_path(file_path))
        except QueueStorageError as exc:
            self._write_log(f"فشل حفظ قائمة الانتظار: {exc}")
            return

        self._write_log("تم حفظ قائمة الانتظار\nلم يتم بدء أي قص أو تحميل")

    def load_queue_state(self) -> None:
        if any(self._queue_job_is_running(job) for job in self.job_queue):
            self._write_log("لا يمكن تعديل المهمة الجارية")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "تحميل قائمة انتظار",
            "",
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        if self.job_queue and not self._ask_replace_queue_state_confirmation():
            return

        try:
            jobs = load_queue_jobs(file_path)
        except QueueStorageError as exc:
            self._write_log(f"فشل تحميل قائمة الانتظار: {exc}")
            return

        self._replace_queue_jobs(jobs)
        self._write_log("تم تحميل قائمة الانتظار\nلم يتم بدء أي قص أو تحميل")

    def _replace_queue_jobs(self, jobs: list[VideoJob]) -> None:
        self._editing_queue_job = None
        self.job_queue = jobs
        self.queue_table.setRowCount(0)
        for job in self.job_queue:
            self._insert_queue_job_row(job)
        self._update_queue_edit_controls()

    def _json_file_path(self, file_path: str) -> Path:
        path = Path(file_path)
        return path if path.suffix.lower() == ".json" else path.with_suffix(".json")

    def _ask_replace_queue_state_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("تحميل قائمة انتظار")
        dialog.setText("توجد قائمة انتظار حالية. هل تريد استبدالها؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(replace_button)
        dialog.exec()
        return dialog.clickedButton() == replace_button

    def run_selected_queue_job(self) -> None:
        row = self._selected_queue_row()
        if row is None:
            self._write_log("لا توجد مهمة محددة")
            return

        summary = run_dry_queue([self.job_queue[row]])
        self._refresh_queue_job_row(row)
        self._write_log(
            "تشغيل قائمة الانتظار سيتم تفعيله في مرحلة لاحقة\n"
            + format_queue_run_summary_ar(summary)
        )

    def run_all_queue_simulation(self) -> None:
        if not self.job_queue:
            self._write_log("لا توجد مهام في قائمة الانتظار")
            return

        warning_count = sum(
            1 for job in self.job_queue if job.status == JobStatus.WARNING or bool(job.warnings)
        )
        summary = run_dry_queue(self.job_queue)
        for row in range(len(self.job_queue)):
            self._refresh_queue_job_row(row)

        self._write_log(
            self._format_run_all_queue_simulation_summary(
                summary,
                warnings=warning_count,
            )
        )

    def _format_run_all_queue_simulation_summary(
        self,
        summary,
        *,
        warnings: int,
    ) -> str:
        visible_error_count = summary.failed_jobs + summary.skipped_jobs
        lines = [
            *summary.messages,
            f"عدد المهام: {summary.total_jobs}",
            f"تمت محاكاتها: {summary.completed_simulated_jobs}",
            f"تم تخطيها: {summary.skipped_jobs}",
            f"فيها أخطاء: {visible_error_count}",
            f"فيها تحذيرات: {warnings}",
        ]
        return "\n".join(lines)

    def start_queue_processing(self) -> None:
        if self._queue_processing_thread is not None:
            self._append_log(f"{AR_QUEUE_JOB_WAITING}\n{AR_QUEUE_CAN_PREPARE_NEXT}")
            return

        if not self.job_queue:
            self._write_log("لا توجد مهام في قائمة الانتظار")
            return

        classification_errors = format_classification_errors_ar(
            validate_classification_rules(self._collect_classification_rules())
        )
        if classification_errors:
            self._write_log(
                "تعذر فحص قواعد التصنيف:\n" + "\n".join(f"- {error}" for error in classification_errors)
            )
            return

        self._prepare_queue_jobs_for_processing()
        if not self._has_runnable_queue_job():
            self._write_log(
                "لا توجد مهمة جاهزة للمعالجة الآن\n"
                f"{AR_URL_QUEUE_PROCESSING_LATER if self._has_waiting_unsupported_url_queue_job() else 'راجع أخطاء قائمة الانتظار أولًا'}"
            )
            return

        self._append_log(f"جاري معالجة المهمة في الخلفية\n{AR_QUEUE_CAN_PREPARE_NEXT}")
        self._queue_auto_continue_after_worker = True
        self._set_queue_processing_controls_running(True)
        self._start_queue_processing_worker(self._collect_classification_rules())

    def stop_queue_after_current_job(self) -> None:
        if self._queue_processing_worker is None:
            self._write_log("لا توجد مهمة قيد المعالجة")
            return

        self._queue_processing_worker.request_stop()
        self._queue_auto_continue_after_worker = False
        self._append_log("سيتم الإيقاف بعد المهمة الحالية")

    def _prepare_queue_jobs_for_processing(self) -> None:
        for row, job in enumerate(self.job_queue):
            if self._queue_job_is_running(job):
                continue

            if job.status in {JobStatus.DRAFT, JobStatus.READY, JobStatus.WARNING, JobStatus.QUEUED}:
                result = validate_queue_job(job)
                apply_queue_validation_result(job, result)

            if not job.clips and job.status != JobStatus.VALIDATION_ERROR:
                job.mark_status(JobStatus.VALIDATION_ERROR)
                if "لا توجد مقاطع محفوظة لهذه المهمة" not in job.errors:
                    job.errors.append("لا توجد مقاطع محفوظة لهذه المهمة")

            if self._queue_source_can_process_in_background(job) and job.can_start:
                job.mark_status(JobStatus.QUEUED)
            elif not self._queue_source_can_process_in_background(job) and job.status in {
                JobStatus.READY,
                JobStatus.WARNING,
                JobStatus.QUEUED,
            }:
                job.mark_status(JobStatus.QUEUED)
                if AR_URL_QUEUE_PROCESSING_LATER not in job.warnings:
                    job.warnings.append(AR_URL_QUEUE_PROCESSING_LATER)

            self._refresh_queue_job_row(row)

    def _has_runnable_queue_job(self) -> bool:
        return any(
            self._queue_source_can_process_in_background(job) and job.can_start
            for job in self.job_queue
        )

    def _has_waiting_unsupported_url_queue_job(self) -> bool:
        return any(
            not self._queue_source_can_process_in_background(job) and job.status == JobStatus.QUEUED
            for job in self.job_queue
        )

    def _queue_source_can_process_in_background(self, job: VideoJob) -> bool:
        return job.source_type in {QueueVideoSourceType.LOCAL, QueueVideoSourceType.YOUTUBE}

    def _start_queue_processing_worker(self, classification_rules: list[ClassificationRule]) -> None:
        thread = QThread(self)
        worker = QueueProcessingWorker(
            jobs=self.job_queue,
            video_processor=self.video_processor,
            classification_rules=classification_rules,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.job_updated.connect(self._refresh_queue_job_row)
        worker.finished.connect(self._finish_queue_processing)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_queue_processing_worker)

        self._queue_processing_thread = thread
        self._queue_processing_worker = worker
        thread.start()

    @Slot()
    def _finish_queue_processing(self) -> None:
        self._queue_auto_continue_after_worker = self._should_auto_continue_after_worker()
        for row in range(len(self.job_queue)):
            self._refresh_queue_job_row(row)
        self._append_log(AR_QUEUE_FINISHED)
        self._set_queue_processing_controls_running(False)

    @Slot()
    def _clear_queue_processing_worker(self) -> None:
        self._queue_processing_thread = None
        self._queue_processing_worker = None
        self._continue_queue_processing_if_needed()

    def _should_auto_continue_after_worker(self) -> bool:
        worker = self._queue_processing_worker
        processor = worker.processor if worker is not None else None
        if processor is None:
            return False
        return not processor.stop_requested and processor.state != QueueProcessorState.FAILED

    def _continue_queue_processing_if_needed(self) -> None:
        if not self._queue_auto_continue_after_worker or self._queue_processing_thread is not None:
            return

        self._prepare_queue_jobs_for_processing()
        if not self._has_runnable_queue_job():
            self._queue_auto_continue_after_worker = False
            return

        self._append_log(AR_QUEUE_NEXT_JOB_STARTED)
        self.start_queue_processing()

    def _set_queue_processing_controls_running(self, running: bool) -> None:
        guarded_runtime_widgets = [
            self.run_selected_queue_job_button,
            self.run_all_queue_simulation_button,
            self.direct_cut_button,
        ]
        for widget in guarded_runtime_widgets:
            widget.setEnabled(not running)

        self.start_queue_processing_button.setEnabled(not running)
        self.stop_queue_after_current_button.setEnabled(running)
        self.processing_status_label.setText(
            "الحالة: جاري معالجة قائمة الانتظار..." if running else "الحالة: جاهز"
        )
        self.processing_status_label.repaint()
        self._update_queue_edit_controls()

    def delete_selected_queue_job(self) -> None:
        row_numbers = self._selected_queue_rows()
        if not row_numbers:
            self._write_log("لا توجد مهمة محددة")
            return

        removed_count = 0
        for row_index in sorted(set(row_numbers), reverse=True):
            if not 0 <= row_index < len(self.job_queue):
                continue
            if self._queue_job_is_running(self.job_queue[row_index]):
                self._append_log("لا يمكن تعديل المهمة الجارية")
                continue
            removed_job = self.job_queue[row_index]
            if removed_job is self._editing_queue_job:
                self._editing_queue_job = None
            del self.job_queue[row_index]
            self.queue_table.removeRow(row_index)
            removed_count += 1

        if removed_count:
            self._write_log("تم حذف المهمة المحددة")
        else:
            self._write_log("لا توجد مهمة محددة")
        self._update_queue_edit_controls()

    def clear_queue(self) -> None:
        if not self.job_queue:
            self._write_log("تم مسح قائمة الانتظار")
            return

        if any(self._queue_job_is_running(job) for job in self.job_queue):
            self._write_log("لا يمكن تعديل المهمة الجارية")
            return

        if not self._ask_clear_queue_confirmation():
            self._write_log("تم إلغاء مسح قائمة الانتظار")
            return

        self.job_queue.clear()
        self._editing_queue_job = None
        self.queue_table.setRowCount(0)
        self._write_log("تم مسح قائمة الانتظار")
        self._update_queue_edit_controls()

    def _ask_clear_queue_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("مسح قائمة الانتظار")
        dialog.setText("هل تريد مسح كل المهام من قائمة الانتظار؟")
        clear_button = dialog.addButton("مسح القائمة", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(clear_button)
        dialog.exec()
        return dialog.clickedButton() == clear_button

    def _selected_queue_row(self) -> int | None:
        row_numbers = self._selected_queue_rows()
        return row_numbers[0] if row_numbers else None

    def _selected_queue_rows(self) -> list[int]:
        selected_rows = self.queue_table.selectionModel().selectedRows()
        row_numbers = [index.row() for index in selected_rows]
        if not row_numbers and self.queue_table.currentRow() >= 0:
            row_numbers = [self.queue_table.currentRow()]
        return sorted(set(row_numbers))

    def _queue_job_is_running(self, job: VideoJob) -> bool:
        return job.status in {JobStatus.DOWNLOADING, JobStatus.CUTTING, JobStatus.VERIFYING}

    def _refresh_queue_job_row(self, row: int) -> None:
        if not 0 <= row < len(self.job_queue):
            return

        job = self.job_queue[row]
        self.queue_table.blockSignals(True)
        try:
            self.queue_table.item(row, QUEUE_SOURCE_COLUMN).setText(self._queue_source_label(job))
            self.queue_table.item(row, QUEUE_SOURCE_COLUMN).setToolTip(job.source)
            self.queue_table.item(row, QUEUE_TITLE_COLUMN).setText(job.title)
            self.queue_table.item(row, QUEUE_CLIP_COUNT_COLUMN).setText(str(job.clip_count))
            self.queue_table.item(row, QUEUE_STATUS_COLUMN).setText(self._queue_status_label(job.status))
            self.queue_table.item(row, QUEUE_HIGH_PRIORITY_COLUMN).setCheckState(
                Qt.Checked if job.settings.high_priority else Qt.Unchecked
            )
            self.queue_table.item(row, QUEUE_ACTION_COLUMN).setText(self._queue_settings_summary(job))
        finally:
            self.queue_table.blockSignals(False)
        self._update_queue_edit_controls()

    def add_classification_rule(self) -> None:
        self._insert_classification_rule(
            ClassificationRule(
                name="",
                min_minutes=0,
                max_minutes=None,
                folder_name="",
            )
        )
        self.classification_rules_table.setCurrentCell(
            self.classification_rules_table.rowCount() - 1,
            RULE_NAME_COLUMN,
        )

    def delete_selected_classification_rule(self) -> None:
        selected_rows = self.classification_rules_table.selectionModel().selectedRows()
        if not selected_rows:
            self._write_log("اختر تصنيفًا من الجدول أولًا.")
            return

        for row_index in sorted((index.row() for index in selected_rows), reverse=True):
            self.classification_rules_table.removeRow(row_index)

        self._write_log("تم حذف التصنيف المحدد.")

    def reset_classification_rules(self) -> None:
        self._reset_classification_rules(log=True)

    def _reset_classification_rules(self, log: bool) -> None:
        self.classification_rules_table.setRowCount(0)
        for rule in get_default_classification_rules():
            self._insert_classification_rule(rule)

        if log:
            self._write_log("تمت استعادة قواعد التصنيف الافتراضية.")

    def _insert_classification_rule(self, rule: ClassificationRule) -> None:
        row = self.classification_rules_table.rowCount()
        self.classification_rules_table.insertRow(row)
        self.classification_rules_table.setItem(row, RULE_NAME_COLUMN, QTableWidgetItem(rule.name))
        self.classification_rules_table.setItem(
            row,
            RULE_MIN_COLUMN,
            QTableWidgetItem(format_rule_minutes(rule.min_minutes)),
        )
        self.classification_rules_table.setItem(
            row,
            RULE_MAX_COLUMN,
            QTableWidgetItem(format_rule_minutes(rule.max_minutes)),
        )
        self.classification_rules_table.setItem(row, RULE_FOLDER_COLUMN, QTableWidgetItem(rule.folder_name))

    def delete_selected_row(self) -> None:
        selected_row_numbers = self._selected_clip_rows()
        if not selected_row_numbers:
            self._write_log("لا يوجد مقطع محدد")
            return

        for row_index in sorted(set(selected_row_numbers), reverse=True):
            self.clips_table.removeRow(row_index)

        self._renumber_rows()
        self._write_log("تم حذف الصف المحدد.")

    def _selected_clip_row(self) -> int | None:
        selected_rows = self._selected_clip_rows()
        return selected_rows[0] if selected_rows else None

    def _selected_clip_rows(self) -> list[int]:
        selected_row_numbers = [index.row() for index in self.clips_table.selectionModel().selectedRows()]
        if not selected_row_numbers:
            selected_row_numbers = [index.row() for index in self.clips_table.selectedIndexes()]
        if not selected_row_numbers and self.clips_table.currentRow() >= 0:
            selected_row_numbers = [self.clips_table.currentRow()]
        return sorted(set(row for row in selected_row_numbers if 0 <= row < self.clips_table.rowCount()))

    def clear_table(self) -> None:
        if self.clips_table.rowCount() == 0:
            self._write_log("الجدول فارغ بالفعل.")
            return

        if not self._ask_clear_table_confirmation():
            self._append_log("تم إلغاء مسح الجدول.")
            return

        self.clips_table.setRowCount(0)
        self._write_log("تم مسح الجدول.")

    def _ask_clear_table_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("مسح الجدول")
        dialog.setText("هل تريد مسح كل المقاطع؟")
        clear_button = dialog.addButton("مسح الجدول", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(clear_button)
        dialog.exec()

        return dialog.clickedButton() == clear_button

    def convert_pasted_text_to_table(self) -> None:
        pasted_text = self.paste_message_input.toPlainText()
        if not pasted_text.strip():
            self._write_log("لا يوجد نص لتحويله.")
            return

        parse_result = parse_clip_message(pasted_text)
        if not parse_result.clips:
            self._write_log("\n".join(warning.message_ar for warning in parse_result.warnings))
            return

        import_mode = "replace"
        if self._table_has_clip_data():
            import_mode = self._ask_table_import_mode("تحويل بسيط إلى جدول")
            if import_mode is None:
                self._append_log("تم إلغاء تحويل النص.")
                return

        self._insert_clip_lines(parse_result.clips, append=import_mode == "append")

        messages = [f"تم تحويل {len(parse_result.clips)} مقطع إلى الجدول."]
        messages.extend(warning.message_ar for warning in parse_result.warnings)
        self._write_log("\n".join(messages))

    def import_smart_paste_message(self) -> None:
        pasted_text = self.paste_message_input.toPlainText()
        dialog = SmartPasteImportDialog(
            self,
            initial_text=pasted_text,
            auto_generate=bool(pasted_text.strip()),
        )
        if dialog.exec() != QDialog.Accepted or dialog.preview is None:
            self._append_log("تم إلغاء الاستيراد الذكي من الرسالة.")
            return

        self._apply_smart_paste_preview(dialog.preview)

    def import_from_excel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "استيراد من Excel",
            str(Path.home()),
            "Excel and CSV files (*.xlsx *.xls *.csv);;All files (*.*)",
        )
        if not file_path:
            return

        try:
            imported_rows = import_clip_rows(file_path)
        except ClipImportError as error:
            self._write_log(str(error))
            return

        if not imported_rows:
            self._write_log("لم يتم العثور على مقاطع في الملف.")
            return

        import_mode = "replace"
        if self._table_has_clip_data():
            import_mode = self._ask_table_import_mode("استيراد من Excel")
            if import_mode is None:
                self._append_log("تم إلغاء الاستيراد.")
                return

        self._insert_clip_lines(imported_rows, append=import_mode == "append")
        self._write_log(f"تم استيراد {len(imported_rows)} مقطع من Excel.")

    def validate_inputs(self) -> bool:
        errors = self._collect_validation_errors()
        if errors:
            self._write_validation_errors(errors)
            return False

        self._normalize_clip_table_times()
        self._write_log("تم فحص البيانات بنجاح. يمكنك بدء المعالجة.")
        return True

    def validate_before_cutting(self) -> bool:
        if not self.validate_inputs():
            return False

        report = validate_clips_before_cutting(
            self._collect_clip_rows(),
            known_video_duration_seconds=self._known_video_duration_for_smart_validation(),
        )
        self._append_log(format_smart_validation_report_ar(report))
        return report.can_start_cutting

    def check_readiness(self) -> None:
        project_folder = self.output_root / sanitize_project_name(self.project_name_input.text())
        temp_folder = project_folder / TEMP_SEGMENTS_FOLDER_NAME
        selected_paths: list[Path] = [project_folder, temp_folder]
        if self.local_file_radio.isChecked() and self.local_file_input.text().strip():
            selected_paths.append(Path(self.local_file_input.text().strip()))

        report = run_readiness_check(
            project_folder,
            temp_folder,
            selected_paths=selected_paths,
        )
        self._write_log("نتيجة فحص جاهزية البرنامج:\n" + format_readiness_report_ar(report))

    def run_smart_pre_cut_validation(self) -> None:
        report = validate_clips_before_cutting(
            self._collect_clip_rows(),
            known_video_duration_seconds=self._known_video_duration_for_smart_validation(),
        )
        self._write_log(format_smart_validation_report_ar(report))

    def start_processing(self) -> None:
        if self._processing_thread is not None:
            self._append_log("المعالجة قيد التشغيل بالفعل.")
            return

        if self._queue_processing_thread is not None:
            self._append_log(f"جاري معالجة المهمة في الخلفية\n{AR_QUEUE_CAN_PREPARE_NEXT}")
            return

        errors = self._collect_base_validation_errors()
        if errors:
            self._write_validation_errors(errors)
            return

        self._normalize_clip_table_times()
        clip_rows = self._collect_clip_rows()
        classification_rules = self._collect_classification_rules()
        clip_padding = self._collect_clip_padding()
        video_speed = self._collect_video_speed()
        volume_percent = self._collect_volume_percent()

        try:
            project_name = validate_required_text(self.project_name_input.text(), "Project name")
        except ValueError:
            self._write_validation_errors(["أدخل اسم المشروع."])
            return

        self.log_area.clear()
        self._write_log("جاري فحص قواعد التصنيف")
        classification_errors = self._collect_classification_validation_errors(clip_rows, classification_rules)
        if classification_errors:
            self._append_log(
                "تعذر فحص قواعد التصنيف:\n" + "\n".join(f"- {error}" for error in classification_errors)
            )
            return

        self._append_log("تم قبول قواعد التصنيف")
        self._append_log("بدأ القص. يرجى الانتظار حتى تنتهي المعالجة.")
        self._last_output_folder = None
        self.processing_status_label.setText("الحالة: جاري المعالجة...")
        self.processing_status_label.repaint()
        self._flush_log_update()
        self._set_processing_enabled(False)
        self._start_processing_worker(
            source_request=self._current_video_source(),
            project_name=project_name,
            clip_rows=clip_rows,
            classification_rules=classification_rules,
            clip_padding=clip_padding,
            video_speed=video_speed,
            volume_percent=volume_percent,
        )

    def start_direct_processing_with_confirmation(self) -> None:
        if not self._ask_direct_cut_fallback_confirmation():
            return
        self.start_processing()

    def _ask_direct_cut_fallback_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("بدء القص المباشر - وضع قديم")
        dialog.setText(
            "القص المباشر وضع قديم وقد يجعل الواجهة أقل استجابة. الأفضل استخدام بدء القص العادي."
        )
        start_button = dialog.addButton("بدء القص المباشر - وضع قديم", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(start_button)
        dialog.exec()
        return dialog.clickedButton() == start_button

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

    def _preview_selected_clip(self, preview_kind: ClipPreviewKind) -> None:
        row = self._selected_clip_row()
        if row is None:
            self._write_log("لا يوجد مقطع محدد")
            return

        input_video_path = self._current_preview_video_path()
        if input_video_path is None:
            return

        try:
            clip_number = self._row_number(row)
            clip_start_seconds = parse_timestamp(self._cell_text(row, START_COLUMN))
            clip_end_seconds = parse_timestamp(self._cell_text(row, END_COLUMN))
            video_duration_seconds = self._preview_video_duration(input_video_path)
            preview_range = calculate_preview_range(
                preview_kind,
                clip_start_seconds,
                clip_end_seconds,
                video_duration_seconds=video_duration_seconds,
                clip_padding=self._collect_clip_padding() if preview_kind is ClipPreviewKind.FULL else ClipPadding(),
            )
        except ValueError as error:
            self._write_log(f"فشل إنشاء المعاينة: {error}")
            return

        if (
            preview_kind is ClipPreviewKind.FULL
            and preview_range.duration_seconds > MAX_FULL_CLIP_PREVIEW_SECONDS
            and not self._ask_long_clip_preview_confirmation(preview_range.duration_seconds)
        ):
            self._write_log("تم إلغاء إنشاء المعاينة.")
            return

        messages = ["جاري إنشاء المعاينة"]
        if preview_kind is ClipPreviewKind.FULL and self._cell_text(row, EXCLUSIONS_COLUMN):
            messages.append("ملاحظة: المعاينة لا تطبق الاستثناءات في هذه النسخة")
        self._write_log("\n".join(messages))

        try:
            preview_path = create_preview_clip(
                input_video_path,
                preview_range,
                clip_number=clip_number,
                preview_kind=preview_kind,
            )
        except ClipPreviewError as error:
            self._append_log(f"فشل إنشاء المعاينة: {error}")
            return

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(preview_path))):
            self._append_log(f"تم فتح المعاينة: {preview_path}")
        else:
            self._append_log("فشل إنشاء المعاينة: تعذر فتح ملف المعاينة")

    def _current_preview_video_path(self) -> Path | None:
        if self.local_file_radio.isChecked():
            try:
                return validate_local_video_file(self.local_file_input.text())
            except VideoSourceError:
                self._write_log("يجب اختيار فيديو محلي أو تنزيل الفيديو أولًا")
                return None

        project_folder = self.output_root / sanitize_project_name(self.project_name_input.text())
        input_video_path = project_folder / INPUT_VIDEO_NAME
        if input_video_path.is_file():
            return input_video_path

        self._write_log("يجب تنزيل الفيديو أولًا قبل المعاينة")
        return None

    def _preview_video_duration(self, input_video_path: Path) -> float | None:
        try:
            return probe_media_duration_seconds(input_video_path)
        except Exception:
            return None

    def _ask_long_clip_preview_confirmation(self, duration_seconds: float) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("معاينة المقطع المحدد")
        dialog.setText(
            "المقطع المحدد طويل وقد يستغرق إنشاء المعاينة وقتًا. هل تريد إنشاء المعاينة؟"
        )
        preview_button = dialog.addButton("إنشاء المعاينة", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(preview_button)
        dialog.exec()
        return dialog.clickedButton() == preview_button

    def _open_output_folder_automatically(self) -> None:
        """Open the output folder immediately after a successful run."""

        try:
            output_dir = validate_output_folder_path(self._last_output_folder)
        except ExportError as error:
            self._append_log(str(error))
            return

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir))):
            self._append_log("تم فتح مجلد النتائج تلقائيًا")
        else:
            self._append_log("خطأ: فشل فتح مجلد النتائج تلقائيًا")

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
        use_browser_cookies = use_youtube and self.use_browser_cookies_checkbox.isChecked()
        self.youtube_input.setEnabled(use_youtube)
        self.local_file_input.setEnabled(not use_youtube)
        self.browse_button.setEnabled(not use_youtube)
        self.use_browser_cookies_checkbox.setEnabled(use_youtube)
        self.browser_combo.setEnabled(use_browser_cookies)
        self.browser_cookies_help_label.setEnabled(use_youtube)
        self.source_status_label.setText(
            "المصدر النشط: رابط يوتيوب" if use_youtube else "المصدر النشط: فيديو من الجهاز"
        )
        self.youtube_input.setStyleSheet("" if use_youtube else "background-color: #f2f2f2;")
        self.local_file_input.setStyleSheet("" if not use_youtube else "background-color: #f2f2f2;")

    def _collect_clip_rows(self) -> list[ClipRowInput]:
        rows: list[ClipRowInput] = []
        for row in range(self.clips_table.rowCount()):
            rows.append(
                ClipRowInput(
                    row_number=self._row_number(row),
                    title=self._cell_text(row, TITLE_COLUMN),
                    start=self._cell_text(row, START_COLUMN),
                    end=self._cell_text(row, END_COLUMN),
                    exclusions=self._cell_text(row, EXCLUSIONS_COLUMN),
                )
            )

        return rows

    def _collect_clip_padding(self) -> ClipPadding:
        return ClipPadding(
            pre_seconds=self.pre_padding_input.value(),
            post_seconds=self.post_padding_input.value(),
        )

    def _collect_video_speed(self) -> float:
        if not self.video_speed_enabled_checkbox.isChecked():
            return DEFAULT_VIDEO_SPEED
        return normalize_video_speed(self.video_speed_input.value())

    def _collect_volume_percent(self) -> int:
        if not self.volume_enabled_checkbox.isChecked():
            return DEFAULT_VOLUME_PERCENT
        return normalize_volume_percent(self.volume_input.value())

    def _collect_validation_errors(self) -> list[str]:
        errors = self._collect_base_validation_errors()
        clip_rows = self._collect_clip_rows()
        errors.extend(
            self._collect_classification_validation_errors(
                clip_rows,
                self._collect_classification_rules(),
            )
        )
        return errors

    def _collect_base_validation_errors(self) -> list[str]:
        errors: list[str] = []

        try:
            validate_required_text(self.project_name_input.text(), "Project name")
        except ValueError:
            errors.append("أدخل اسم المشروع.")

        try:
            self._collect_video_speed()
        except VideoSpeedError:
            errors.append(AR_INVALID_VIDEO_SPEED)

        try:
            self._collect_volume_percent()
        except VideoVolumeError:
            errors.append(AR_INVALID_VOLUME_PERCENT)

        try:
            if self.youtube_radio.isChecked():
                validate_youtube_url(self.youtube_input.text())
            else:
                validate_local_video_file(self.local_file_input.text())
        except VideoSourceError as error:
            errors.append(str(error))

        errors.extend(
            error.message_ar
            for error in validate_clip_rows(
                self._collect_clip_rows(),
                clip_padding=self._collect_clip_padding(),
            )
        )
        return errors

    def _collect_classification_rules(self) -> list[ClassificationRule]:
        rules: list[ClassificationRule] = []
        for row in range(self.classification_rules_table.rowCount()):
            rules.append(
                ClassificationRule(
                    name=self._classification_cell_text(row, RULE_NAME_COLUMN),
                    min_minutes=self._parse_rule_minutes(
                        self._classification_cell_text(row, RULE_MIN_COLUMN),
                        allow_open=False,
                    ),
                    max_minutes=self._parse_rule_minutes(
                        self._classification_cell_text(row, RULE_MAX_COLUMN),
                        allow_open=True,
                    ),
                    folder_name=self._classification_cell_text(row, RULE_FOLDER_COLUMN),
                )
            )

        return rules

    def _collect_classification_validation_errors(
        self,
        clip_rows: list[ClipRowInput],
        classification_rules: list[ClassificationRule],
    ) -> list[str]:
        errors = format_classification_errors_ar(validate_classification_rules(classification_rules))
        if errors:
            return errors

        try:
            clip_definitions = self.video_processor.build_clip_definitions(clip_rows)
        except ValueError:
            return []

        for clip in clip_definitions:
            try:
                classify_duration(clip.duration_seconds, classification_rules)
            except ClassificationRuleError:
                errors.append(f"لا توجد قاعدة تصنيف مناسبة للمقطع رقم {clip.number}")

        return errors

    def _current_video_source(self) -> VideoSourceRequest:
        if self.youtube_radio.isChecked():
            return VideoSourceRequest(
                VideoSourceType.YOUTUBE,
                self.youtube_input.text(),
                use_browser_cookies=self.use_browser_cookies_checkbox.isChecked(),
                browser=self._selected_browser_identifier(),
            )

        return VideoSourceRequest(VideoSourceType.LOCAL_FILE, self.local_file_input.text())

    def _known_video_duration_for_smart_validation(self) -> float | None:
        if not self.local_file_radio.isChecked():
            return None
        try:
            local_video_path = validate_local_video_file(self.local_file_input.text())
            return probe_media_duration_seconds(local_video_path)
        except Exception:
            return None

    def _selected_browser_identifier(self) -> str:
        mapping = {
            "Chrome": "chrome",
            "Edge": "edge",
            "Brave": "brave",
            "Firefox": "firefox",
        }
        return mapping.get(self.browser_combo.currentText(), "chrome")

    def _cell_text(self, row: int, column: int) -> str:
        item = self.clips_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _classification_cell_text(self, row: int, column: int) -> str:
        item = self.classification_rules_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _parse_rule_minutes(self, value: str, allow_open: bool) -> float | None | str:
        text = value.strip()
        if allow_open and (not text or text in {AR_OPEN_MINUTES, "open", "Open", "none", "None", "∞"}):
            return None

        try:
            return float(text)
        except ValueError:
            return text

    def _row_number(self, row: int) -> int:
        try:
            return int(self._cell_text(row, NUMBER_COLUMN))
        except ValueError:
            return row + 1

    def _insert_clip_lines(self, clips: list[ParsedClipLine] | list[ImportedClipRow], append: bool) -> None:
        if not append:
            self.clips_table.setRowCount(0)
        elif not self._table_has_clip_data():
            self.clips_table.setRowCount(0)

        for clip in clips:
            self._insert_clip_row(
                number=clip.number,
                title=clip.title,
                start=clip.start,
                end=clip.end,
                exclusions=clip.exclusions,
            )

    def _apply_smart_paste_preview(self, preview: SmartPastePreview) -> bool:
        if not preview.video_urls and not preview.clips:
            self._write_log("لم يتم العثور على رابط أو مقاطع مفهومة")
            return False

        apply_mode = self._ask_smart_paste_apply_mode(preview)
        if apply_mode is None:
            self._append_log("تم إلغاء تطبيق نتائج الاستيراد الذكي.")
            return False

        if apply_mode == "queue":
            return self._add_smart_paste_preview_to_queue(preview)

        applied_messages: list[str] = []
        if preview.project_title and (apply_mode == "replace" or not self.project_name_input.text().strip()):
            self.project_name_input.setText(preview.project_title)
            applied_messages.append("تم تطبيق عنوان المشروع المكتشف.")

        if apply_mode == "replace" and preview.video_urls:
            self.youtube_radio.setChecked(True)
            self.youtube_input.setText(preview.video_urls[0])
            applied_messages.append("تم تطبيق رابط الفيديو المكتشف.")
        elif apply_mode == "append" and preview.video_urls and not self.youtube_input.text().strip():
            self.youtube_radio.setChecked(True)
            self.youtube_input.setText(preview.video_urls[0])
            applied_messages.append("تم تطبيق رابط الفيديو المكتشف.")
        if len(preview.video_urls) > 1:
            applied_messages.append("تم اكتشاف أكثر من رابط فيديو. تم تطبيق أول رابط فقط في هذه النسخة.")

        regular_clips = [clip for clip in preview.clips if not clip.multi_part]
        multi_part_clips = [clip for clip in preview.clips if clip.multi_part]

        if regular_clips:
            self._insert_clip_lines(
                [self._smart_paste_clip_to_parsed_clip(clip) for clip in regular_clips],
                append=apply_mode == "append",
            )
            applied_messages.append(f"تم تطبيق {len(regular_clips)} مقطع من الاستيراد الذكي.")
        if multi_part_clips:
            applied_messages.append(
                f"تم إبقاء {len(multi_part_clips)} مقطع مركب في المعاينة فقط لأن الجدول الحالي لا يدعم أكثر من جزء."
            )

        if preview.warnings:
            applied_messages.append(f"تم التطبيق مع {len(preview.warnings)} تحذير.")
        if preview.unparsed_lines:
            applied_messages.append(f"بقي {len(preview.unparsed_lines)} سطر لم يتم فهمه.")
        if not applied_messages:
            applied_messages.append("لم يتم العثور على رابط أو مقاطع قابلة للتطبيق.")

        self._write_log("\n".join(applied_messages))
        return True

    def _ask_smart_paste_apply_mode(self, preview: SmartPastePreview) -> str | None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("استيراد ذكي")
        dialog.setText("اختر طريقة تطبيق نتائج الاستيراد الذكي.")
        replace_button = dialog.addButton(SMART_PASTE_REPLACE_LABEL, QMessageBox.AcceptRole)
        append_button = dialog.addButton(SMART_PASTE_APPEND_LABEL, QMessageBox.ActionRole)
        queue_button = dialog.addButton(SMART_PASTE_QUEUE_LABEL, QMessageBox.ActionRole)
        dialog.addButton(SMART_PASTE_CANCEL_LABEL, QMessageBox.RejectRole)
        dialog.setDefaultButton(append_button if self._table_has_clip_data() else replace_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button == replace_button:
            return "replace"
        if clicked_button == append_button:
            return "append"
        if clicked_button == queue_button:
            return "queue"
        return None

    def _add_smart_paste_preview_to_queue(self, preview: SmartPastePreview) -> bool:
        source_snapshot = self._smart_paste_queue_source(preview)
        if source_snapshot is None:
            return False

        source_type, source, title = source_snapshot
        regular_clips = [clip for clip in preview.clips if not clip.multi_part]
        multi_part_count = len(preview.clips) - len(regular_clips)
        job = self._add_queue_job(
            source_type,
            source,
            title,
            clips=self._smart_paste_clip_jobs(regular_clips),
            settings=self._current_job_settings_snapshot(),
        )
        self.queue_table.setCurrentCell(self.job_queue.index(job), QUEUE_SOURCE_COLUMN)

        messages = [
            "تمت إضافة الاستيراد الذكي كمهمة جديدة في قائمة الانتظار",
            "لم يتم بدء أي قص أو تحميل",
        ]
        if multi_part_count:
            messages.append(
                f"تم إبقاء {multi_part_count} مقطع مركب في المعاينة فقط لأن القص المركب لم يتم تفعيله بعد."
            )
        if preview.warnings:
            messages.append(f"تمت الإضافة مع {len(preview.warnings)} تحذير.")
        if preview.unparsed_lines:
            messages.append(f"بقي {len(preview.unparsed_lines)} سطر لم يتم فهمه.")
        self._write_log("\n".join(messages))
        return True

    def _smart_paste_queue_source(self, preview: SmartPastePreview) -> tuple[QueueVideoSourceType, str, str] | None:
        title = preview.project_title or self.project_name_input.text().strip()
        if preview.video_urls:
            source = preview.video_urls[0]
            source_type = self._supported_queue_url_source_type(source)
            if source_type is None:
                self._write_log("الرابط غير مدعوم حاليًا")
                return None
            if len(preview.video_urls) > 1:
                self._append_log("تم اكتشاف أكثر من رابط فيديو. سيتم استخدام أول رابط فقط في هذه النسخة.")
            return source_type, source, title or source

        current_source = self._current_work_queue_source()
        if current_source is None:
            return None
        source_type, source, current_title = current_source
        return source_type, source, title or current_title

    def _smart_paste_clip_jobs(self, clips: list[SmartPasteClip]) -> list[ClipJob]:
        return [
            ClipJob(
                title=clip.title,
                start=clip.start,
                end=clip.end,
                exclusions=clip.exclusions_text,
                notes=[clip.notes_text] if clip.notes_text else [],
            )
            for clip in clips
        ]

    def _smart_paste_clip_to_parsed_clip(self, clip: SmartPasteClip) -> ParsedClipLine:
        return ParsedClipLine(
            number=clip.number,
            title=clip.title,
            start=clip.start,
            end=clip.end,
            exclusions=clip.exclusions_text,
        )

    def _normalize_clip_table_times(self) -> None:
        for row in range(self.clips_table.rowCount()):
            for column in (START_COLUMN, END_COLUMN):
                item = self.clips_table.item(row, column)
                if item is not None:
                    item.setText(normalize_timestamp_text(item.text()))

            exclusions_item = self.clips_table.item(row, EXCLUSIONS_COLUMN)
            if exclusions_item is not None:
                exclusions_item.setText(
                    normalize_clip_exclusions(
                        self._cell_text(row, START_COLUMN),
                        self._cell_text(row, END_COLUMN),
                        exclusions_item.text(),
                        clip_padding=self._collect_clip_padding(),
                    )
                )

    def _table_has_clip_data(self) -> bool:
        for row in range(self.clips_table.rowCount()):
            if (
                self._cell_text(row, TITLE_COLUMN)
                or self._cell_text(row, START_COLUMN)
                or self._cell_text(row, END_COLUMN)
                or self._cell_text(row, EXCLUSIONS_COLUMN)
            ):
                return True

        return False

    def _ask_table_import_mode(self, title: str = "استيراد") -> str | None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText("الجدول يحتوي على بيانات. هل تريد استبدال الصفوف الحالية أم إضافة الصفوف الجديدة؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        append_button = dialog.addButton("إضافة", QMessageBox.ActionRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(replace_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button == replace_button:
            return "replace"
        if clicked_button == append_button:
            return "append"

        return None

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
        self.log_area.setPlainText(self._format_log_message(message))
        self._flush_log_update()

    def _append_log(self, message: str) -> None:
        self.log_area.append(self._format_log_message(message))
        self._flush_log_update()

    def _flush_log_update(self) -> None:
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.log_area.repaint()
        self.processing_status_label.repaint()
        QApplication.processEvents()

    def _write_validation_errors(self, errors: list[str]) -> None:
        self._write_log("تعذر فحص البيانات:\n" + "\n".join(f"- {error}" for error in errors))

    def _format_log_message(self, message: str) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S")
        lines = message.splitlines() or [message]
        return "\n".join(f"[{timestamp}] {line}" if line else f"[{timestamp}]" for line in lines)

    def _start_processing_worker(
        self,
        source_request: VideoSourceRequest,
        project_name: str,
        clip_rows: list[ClipRowInput],
        classification_rules: list[ClassificationRule],
        clip_padding: ClipPadding,
        video_speed: float = DEFAULT_VIDEO_SPEED,
        volume_percent: int = DEFAULT_VOLUME_PERCENT,
    ) -> None:
        thread = QThread(self)
        worker = ProcessingWorker(
            video_processor=self.video_processor,
            source_request=source_request,
            project_name=project_name,
            clip_rows=clip_rows,
            classification_rules=classification_rules,
            clip_padding=clip_padding,
            video_speed=video_speed,
            volume_percent=volume_percent,
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
        self.processing_status_label.setText("الحالة: تم الانتهاء بنجاح")
        self._flush_log_update()
        self._open_output_folder_automatically()

    @Slot(str)
    def _handle_processing_failure(self, message: str) -> None:
        self._last_output_folder = None
        self._append_log(message or "حدث خطأ أثناء المعالجة.")
        self.processing_status_label.setText("الحالة: فشل التنفيذ")
        self._flush_log_update()

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
            self.use_browser_cookies_checkbox,
            self.browser_combo,
            self.project_name_input,
            self.paste_message_input,
            self.smart_paste_button,
            self.parse_message_button,
            self.queue_table,
            self.add_current_work_to_queue_button,
            self.add_queue_local_video_button,
            self.add_queue_url_button,
            self.save_queue_clips_button,
            self.load_queue_clips_button,
            self.load_queue_job_workspace_button,
            self.save_queue_job_edits_button,
            self.cancel_queue_job_edit_button,
            self.save_queue_state_button,
            self.load_queue_state_button,
            self.add_and_run_queue_job_button,
            self.start_queue_processing_button,
            self.stop_queue_after_current_button,
            self.run_selected_queue_job_button,
            self.run_all_queue_simulation_button,
            self.validate_queue_job_button,
            self.validate_all_queue_jobs_button,
            self.delete_queue_job_button,
            self.clear_queue_button,
            self.queue_advanced_toggle_button,
            self.queue_selected_job_details_label,
            self.queue_edit_status_label,
            self.queue_advanced_group,
            self.queue_advanced_controls_widget,
            self.clips_table,
            self.classification_rules_table,
            self.add_row_button,
            self.import_excel_button,
            self.delete_row_button,
            self.clear_table_button,
            self.preview_clip_start_button,
            self.preview_clip_end_button,
            self.preview_selected_clip_button,
            self.add_classification_button,
            self.delete_classification_button,
            self.reset_classification_button,
            self.pre_padding_input,
            self.post_padding_input,
            self.video_speed_enabled_checkbox,
            self.video_speed_input,
            self.reset_video_speed_button,
            self.video_speed_status_label,
            self.volume_enabled_checkbox,
            self.volume_input,
            self.reset_volume_button,
            self.volume_status_label,
            self.readiness_button,
            self.smart_validation_button,
            self.validate_button,
            self.start_button,
            self.direct_cut_button,
            self.open_output_button,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

        if enabled:
            self._update_source_inputs()
            self._update_speed_volume_controls()
            self.start_button.setText("بدء القص")
            self.direct_cut_button.setText("بدء القص المباشر - وضع قديم")
        else:
            self.processing_status_label.setText("الحالة: جاري المعالجة...")
            self.start_button.setText("جاري المعالجة...")
            self.direct_cut_button.setText("جاري المعالجة...")

        self.processing_status_label.repaint()
        QApplication.processEvents()

        self.open_output_button.setEnabled(enabled and self._last_output_folder is not None)
        self.stop_queue_after_current_button.setEnabled(enabled and self._queue_processing_thread is not None)
