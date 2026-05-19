"""Main window for the desktop application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
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
from src.export_utils import ExportError, validate_output_folder_path
from src.import_utils import ClipImportError, ImportedClipRow, import_clip_rows
from src.message_parser import ParsedClipLine, parse_clip_message
from src.readiness import format_readiness_report_ar, run_readiness_check
from src.smart_paste_parser import SmartPasteClip, SmartPastePreview, parse_smart_paste_message
from src.smart_validation import format_smart_validation_report_ar, validate_clips_before_cutting
from src.time_utils import normalize_timestamp_text
from src.version import APP_NAME, APP_SUBTITLE
from src.validation import ClipRowInput, normalize_clip_exclusions, validate_clip_rows, validate_required_text
from src.video_processor import (
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
AR_OPEN_MINUTES = "مفتوح"


class SmartPasteImportDialog(QDialog):
    """Preview-only dialog for smart paste imports."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview: SmartPastePreview | None = None

        self.setWindowTitle("استيراد ذكي من رسالة")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(760, 620)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("الصق الرسالة كاملة هنا، بما في ذلك رابط الفيديو والمقاطع.")
        self.message_input.setMinimumHeight(120)

        self.summary_label = QLabel("الصق الرسالة ثم اضغط فحص الرسالة.")
        self.summary_label.setWordWrap(True)

        self.clips_preview_table = QTableWidget(0, 3)
        self.clips_preview_table.setHorizontalHeaderLabels(["العنوان", "البداية", "النهاية"])
        self.clips_preview_table.verticalHeader().setVisible(False)
        self.clips_preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.clips_preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

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
        layout.addWidget(QLabel("الأسطر التي لم يتم فهمها"))
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
        self.summary_label.setText(
            "\n".join(
                [
                    f"عدد الروابط: {len(preview.video_urls)}",
                    f"عدد المقاطع: {len(preview.clips)}",
                    f"عدد التحذيرات: {len(preview.warnings)}",
                    f"الأسطر التي لم يتم فهمها: {len(preview.unparsed_lines)}",
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
    ) -> None:
        super().__init__()
        self.video_processor = video_processor
        self.source_request = source_request
        self.project_name = project_name
        self.clip_rows = clip_rows
        self.classification_rules = classification_rules

    @Slot()
    def run(self) -> None:
        try:
            processing_result = self.video_processor.process_project(
                self.source_request,
                self.project_name,
                self.clip_rows,
                progress_callback=self.progress.emit,
                classification_rules=self.classification_rules,
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
        self.smart_paste_button = QPushButton("استيراد ذكي من رسالة")
        self.parse_message_button = QPushButton("تحويل النص إلى جدول")
        self.clips_table = QTableWidget(0, 5)
        self.classification_rules_table = QTableWidget(0, 4)
        self.add_row_button = QPushButton("إضافة مقطع")
        self.import_excel_button = QPushButton("استيراد من Excel")
        self.delete_row_button = QPushButton("حذف المحدد")
        self.clear_table_button = QPushButton("مسح الجدول")
        self.add_classification_button = QPushButton("إضافة تصنيف")
        self.delete_classification_button = QPushButton("حذف التصنيف المحدد")
        self.reset_classification_button = QPushButton("استعادة الافتراضي")
        self.readiness_button = QPushButton("فحص جاهزية البرنامج")
        self.smart_validation_button = QPushButton("فحص ذكي قبل القص")
        self.validate_button = QPushButton("فحص الجدول")
        self.start_button = QPushButton("بدء القص")
        self.open_output_button = QPushButton("فتح مجلد النتائج")
        self.processing_status_label = QLabel("الحالة: جاهز")
        self.log_area = QTextEdit()
        self.scroll_area = QScrollArea()

        self._apply_branding()
        self.setCentralWidget(self._build_scrollable_ui())
        self._connect_signals()
        self._reset_classification_rules(log=False)
        self._update_source_inputs()
        self.open_output_button.setEnabled(False)

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
        layout.addWidget(self._build_clips_section(), stretch=1)
        layout.addWidget(self._build_classification_section())
        layout.addWidget(self._build_paste_section())
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

    def _build_help_section(self) -> QGroupBox:
        group = QGroupBox("تعليمات سريعة")
        layout = QVBoxLayout(group)

        help_text = QLabel(
            "اختر مصدر الفيديو، ثم أدخل اسم المشروع.\n"
            "أضف المقاطع يدويًا، أو استورد Excel، أو الصق رسالة.\n"
            "اضغط بدء القص عند جاهزية الجدول.\n"
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
        group = QGroupBox("لصق قائمة المقاطع")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("الصق قائمة المقاطع هنا"))
        self.paste_message_input.setPlaceholderText("مثال: 1- 9:16 - 9:50 عنوان المقطع")
        self.paste_message_input.setMinimumHeight(80)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.smart_paste_button)
        button_row.addWidget(self.parse_message_button)

        layout.addWidget(self.paste_message_input)
        layout.addLayout(button_row)

        return group

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

        layout.addWidget(self.clips_table)
        layout.addLayout(table_buttons)

        return group

    def _build_action_section(self) -> QGroupBox:
        group = QGroupBox("أزرار التشغيل")
        layout = QHBoxLayout(group)

        layout.addWidget(self.readiness_button)
        layout.addWidget(self.smart_validation_button)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.start_button)
        layout.addWidget(self.open_output_button)
        layout.addStretch(1)
        layout.addWidget(self.processing_status_label)

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
        self.add_classification_button.clicked.connect(self.add_classification_rule)
        self.delete_classification_button.clicked.connect(self.delete_selected_classification_rule)
        self.reset_classification_button.clicked.connect(self.reset_classification_rules)
        self.smart_paste_button.clicked.connect(self.import_smart_paste_message)
        self.parse_message_button.clicked.connect(self.convert_pasted_text_to_table)
        self.readiness_button.clicked.connect(self.check_readiness)
        self.smart_validation_button.clicked.connect(self.run_smart_pre_cut_validation)
        self.validate_button.clicked.connect(self.validate_inputs)
        self.start_button.clicked.connect(self.start_processing)
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
        selected_rows = self.clips_table.selectionModel().selectedRows()
        if not selected_rows:
            self._write_log("اختر صفًا من الجدول أولًا.")
            return

        for row_index in sorted((index.row() for index in selected_rows), reverse=True):
            self.clips_table.removeRow(row_index)

        self._renumber_rows()
        self._write_log("تم حذف الصف المحدد.")

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
        dialog.setText("هل تريد مسح كل المقاطع من الجدول؟")
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
            import_mode = self._ask_table_import_mode("تحويل النص إلى جدول")
            if import_mode is None:
                self._append_log("تم إلغاء تحويل النص.")
                return

        self._insert_clip_lines(parse_result.clips, append=import_mode == "append")

        messages = [f"تم تحويل {len(parse_result.clips)} مقطع إلى الجدول."]
        messages.extend(warning.message_ar for warning in parse_result.warnings)
        self._write_log("\n".join(messages))

    def import_smart_paste_message(self) -> None:
        dialog = SmartPasteImportDialog(self)
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

        errors = self._collect_base_validation_errors()
        if errors:
            self._write_validation_errors(errors)
            return

        self._normalize_clip_table_times()
        clip_rows = self._collect_clip_rows()
        classification_rules = self._collect_classification_rules()

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
            if self.youtube_radio.isChecked():
                validate_youtube_url(self.youtube_input.text())
            else:
                validate_local_video_file(self.local_file_input.text())
        except VideoSourceError as error:
            errors.append(str(error))

        errors.extend(error.message_ar for error in validate_clip_rows(self._collect_clip_rows()))
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
        url_mode = self._resolve_smart_paste_url_mode(preview)
        if url_mode is None:
            self._append_log("تم إلغاء تطبيق نتائج الاستيراد الذكي.")
            return False

        clip_mode = self._resolve_smart_paste_clip_mode(preview)
        if clip_mode is None:
            self._append_log("تم إلغاء تطبيق نتائج الاستيراد الذكي.")
            return False

        applied_messages: list[str] = []
        if url_mode in {"set", "replace"} and len(preview.video_urls) == 1:
            self.youtube_radio.setChecked(True)
            self.youtube_input.setText(preview.video_urls[0])
            applied_messages.append("تم تطبيق رابط الفيديو المكتشف.")
        elif len(preview.video_urls) > 1:
            applied_messages.append("تم اكتشاف أكثر من رابط فيديو. لم يتم تطبيق أي رابط تلقائيًا.")

        if clip_mode in {"append", "replace"} and preview.clips:
            self._insert_clip_lines(
                [self._smart_paste_clip_to_parsed_clip(clip) for clip in preview.clips],
                append=clip_mode == "append",
            )
            applied_messages.append(f"تم تطبيق {len(preview.clips)} مقطع من الاستيراد الذكي.")

        if preview.warnings:
            applied_messages.append(f"تم التطبيق مع {len(preview.warnings)} تحذير.")
        if preview.unparsed_lines:
            applied_messages.append(f"بقي {len(preview.unparsed_lines)} سطر لم يتم فهمه.")
        if not applied_messages:
            applied_messages.append("لم يتم العثور على رابط أو مقاطع قابلة للتطبيق.")

        self._write_log("\n".join(applied_messages))
        return True

    def _resolve_smart_paste_url_mode(self, preview: SmartPastePreview) -> str | None:
        if len(preview.video_urls) != 1:
            return "skip"
        if not self.youtube_input.text().strip():
            return "set"
        return self._ask_smart_paste_url_mode()

    def _resolve_smart_paste_clip_mode(self, preview: SmartPastePreview) -> str | None:
        if not preview.clips:
            return "skip"
        if self._table_has_clip_data():
            return self._ask_smart_paste_clip_mode()
        return "replace"

    def _ask_smart_paste_url_mode(self) -> str | None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("استيراد ذكي من رسالة")
        dialog.setText("حقل رابط يوتيوب يحتوي على رابط. هل تريد استبداله بالرابط المكتشف؟")
        replace_button = dialog.addButton("استبدال", QMessageBox.AcceptRole)
        keep_button = dialog.addButton("عدم استبدال", QMessageBox.ActionRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(keep_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button == replace_button:
            return "replace"
        if clicked_button == keep_button:
            return "keep"
        return None

    def _ask_smart_paste_clip_mode(self) -> str | None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("استيراد ذكي من رسالة")
        dialog.setText("جدول المقاطع يحتوي على بيانات. كيف تريد تطبيق المقاطع المكتشفة؟")
        append_button = dialog.addButton("إضافة المقاطع الجديدة", QMessageBox.AcceptRole)
        replace_button = dialog.addButton("استبدال الجدول الحالي", QMessageBox.ActionRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(append_button)
        dialog.exec()

        clicked_button = dialog.clickedButton()
        if clicked_button == append_button:
            return "append"
        if clicked_button == replace_button:
            return "replace"
        return None

    def _smart_paste_clip_to_parsed_clip(self, clip: SmartPasteClip) -> ParsedClipLine:
        return ParsedClipLine(
            number=clip.number,
            title=clip.title,
            start=clip.start,
            end=clip.end,
            exclusions="",
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
    ) -> None:
        thread = QThread(self)
        worker = ProcessingWorker(
            video_processor=self.video_processor,
            source_request=source_request,
            project_name=project_name,
            clip_rows=clip_rows,
            classification_rules=classification_rules,
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
            self.clips_table,
            self.classification_rules_table,
            self.add_row_button,
            self.import_excel_button,
            self.delete_row_button,
            self.clear_table_button,
            self.add_classification_button,
            self.delete_classification_button,
            self.reset_classification_button,
            self.readiness_button,
            self.smart_validation_button,
            self.validate_button,
            self.start_button,
            self.open_output_button,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

        if enabled:
            self._update_source_inputs()
            self.start_button.setText("بدء القص")
        else:
            self.processing_status_label.setText("الحالة: جاري المعالجة...")
            self.start_button.setText("جاري المعالجة...")

        self.processing_status_label.repaint()
        QApplication.processEvents()

        self.open_output_button.setEnabled(enabled and self._last_output_folder is not None)
