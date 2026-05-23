"""Main window for the desktop application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
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
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.app_paths import (
    AR_OUTPUT_CREATE_FAILED,
    OutputPathError,
    documents_output_root,
    resolve_output_root,
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
from src.smart_paste_parser import (
    SmartPasteClip,
    SmartPastePreview,
    format_smart_paste_debug_report,
    parse_smart_paste_message,
)
from src.smart_validation import format_smart_validation_report_ar, validate_clips_before_cutting
from src.time_utils import normalize_timestamp_text, parse_timestamp
from src.version import APP_NAME, APP_VERSION
from src.validation import ClipRowInput, normalize_clip_exclusions, validate_clip_rows, validate_required_text
from src.video_speed import AR_INVALID_VIDEO_SPEED, DEFAULT_VIDEO_SPEED, VideoSpeedError, normalize_video_speed
from src.video_volume import (
    AR_INVALID_VOLUME_PERCENT,
    DEFAULT_VOLUME_PERCENT,
    VideoVolumeError,
    normalize_volume_percent,
)
from src.video_black_flash import (
    ClipBlackFlash,
    DEFAULT_BLACK_FLASH_SECONDS,
    normalize_black_flash_duration,
)
from src.video_fade import (
    ClipFade,
    DEFAULT_FADE_IN_SECONDS,
    DEFAULT_FADE_OUT_SECONDS,
    normalize_fade_duration,
)
from src.video_export_quality import (
    DEFAULT_ENABLED_QUALITY_PRESET,
    DEFAULT_EXPORT_QUALITY_PRESET,
    DEFAULT_RESOLUTION_LIMIT,
    ExportQualityError,
    ExportQualitySettings,
    QUALITY_PRESET_LABELS_AR,
    RESOLUTION_LIMIT_LABELS_AR,
    normalize_export_quality_settings,
    normalize_quality_preset,
    normalize_resolution_limit,
    quality_preset_label_ar,
    resolution_limit_label_ar,
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
APP_STYLE_SHEET = """
QMainWindow, QScrollArea, QWidget {
    background: #07111d;
    color: #edf2f7;
    font-size: 11px;
}
QScrollArea {
    border: none;
}
QLabel {
    background: transparent;
}
QFrame#appHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #173553, stop:0.42 #0d243c, stop:1 #061522);
    border: 1px solid #315f7f;
    border-radius: 28px;
}
QFrame#logoHalo {
    background: qradialgradient(cx:0.5, cy:0.42, radius:0.72, fx:0.45, fy:0.34, stop:0 #1d5d93, stop:0.45 #12375d, stop:1 #071725);
    border: 1px solid #3f80a9;
    border-radius: 31px;
}
QLabel#appTitle {
    background: transparent;
    border: none;
    color: #f8fafc;
    font-size: 22px;
    font-weight: 800;
    min-height: 34px;
}
QLabel#appSubtitle {
    background: transparent;
    border: none;
    color: #d5e2ef;
    font-size: 12.5px;
    font-weight: 650;
}
QLabel#appVersion {
    background: transparent;
    border: none;
    color: #aabdd0;
    font-size: 11.5px;
    font-weight: 600;
}
QLabel#appLogo {
    background: transparent;
    border: none;
    border-radius: 24px;
}
QLabel#sectionHelpText, QLabel#statusHelperLabel {
    color: #aebdd0;
}
QFrame#pageHeading {
    background: transparent;
    border: none;
}
QLabel#pageTitle {
    color: #f8fafc;
    font-size: 22px;
    font-weight: 800;
}
QLabel#pageSubtitle {
    color: #aebdd0;
    font-size: 12px;
}
QGroupBox {
    background: #102034;
    border: 1px solid #20394f;
    border-radius: 18px;
    margin-top: 0;
    padding: 42px 16px 16px 16px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    top: 12px;
    right: 16px;
    padding: 3px 11px;
    color: #f4f8fd;
    background: #122840;
    border: 1px solid #243f57;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 750;
}
QGroupBox#dashboardCard {
    background: #102034;
}
QGroupBox#mainActionsCard {
    background: #102238;
    border-color: #24435d;
    border-radius: 18px;
    padding: 7px 12px;
}
QGroupBox#mainActionsCard::title {
    color: transparent;
    background: transparent;
    border: none;
    padding: 0;
}
QGroupBox#clipsCard {
    border-color: #345c7a;
}
QGroupBox#queueCard {
    border-color: #2e536e;
}
QGroupBox#queueControlCard {
    background: #0f1b29;
    border-color: #2a4c66;
}
QGroupBox#smartImportCard {
    background: #101f31;
    border-color: #2d5777;
    padding-top: 46px;
}
QGroupBox#smartImportCard::title {
    color: #f8fafc;
    font-size: 16px;
}
QGroupBox#importSideCard {
    background: #101b29;
    border-color: #294a64;
}
QGroupBox#importSummaryCard {
    background: #101b29;
    border-color: #294a64;
    padding-top: 42px;
}
QGroupBox#nestedSettingsGroup, QGroupBox#jobDetailsCard {
    background: #102238;
    border-color: #33506a;
    border-radius: 12px;
    padding-top: 34px;
}
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget {
    background: #0f2236;
    border: 1px solid #2b4054;
    border-radius: 11px;
    color: #f4f7fb;
    selection-background-color: #2d6cdf;
    selection-color: #ffffff;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 24px;
    padding: 3px 8px;
}
QTextEdit {
    padding: 8px;
}
QTextEdit#pasteBox {
    min-height: 190px;
    background: #0e2236;
    border: 1px dashed #3b6688;
    border-radius: 17px;
    padding: 12px;
}
QTextEdit#logArea {
    background: #0d1f32;
    border-color: #31465b;
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
    line-height: 1.35;
}
QTextEdit#warningArea {
    background: #15170c;
    border-color: #7a6022;
    color: #ffe6a3;
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
}
QTextEdit#reviewArea {
    background: #0d1f32;
    border-color: #31465b;
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
}
QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background: #172331;
    color: #7e8fa3;
    border-color: #26384a;
}
QTableWidget {
    gridline-color: #26394b;
    alternate-background-color: #102438;
    border-radius: 12px;
}
QTableWidget::item {
    padding: 6px;
}
QTableWidget::item:selected {
    background: #1f5f9f;
    color: #ffffff;
}
QHeaderView::section {
    background: #17283a;
    color: #e7eef8;
    border: 0;
    border-left: 1px solid #2b4054;
    padding: 6px 9px;
    font-weight: 600;
}
QPushButton {
    background: #1b2e42;
    border: 1px solid #365a76;
    border-radius: 11px;
    color: #f2f6fb;
    padding: 5px 10px;
    min-height: 25px;
}
QPushButton:hover {
    background: #253d56;
    border-color: #5783a8;
}
QPushButton:pressed {
    background: #132638;
    border-color: #7aa7ca;
    padding-top: 6px;
    padding-bottom: 4px;
}
QPushButton:disabled {
    background: #121f2e;
    border-color: #28394a;
    color: #718196;
}
QPushButton#primaryActionButton {
    background: #2679e8;
    border-color: #69abff;
    color: #ffffff;
    font-weight: 700;
    min-height: 34px;
    padding: 7px 18px;
    font-size: 12px;
}
QPushButton#primaryActionButton:hover {
    background: #3a90ff;
}
QPushButton#primaryActionButton:pressed {
    background: #155fb8;
    border-color: #b8d9ff;
}
QPushButton#smartImportButton {
    background: #236fdb;
    border-color: #65a9ff;
    font-weight: 700;
}
QPushButton#smartImportButton:pressed {
    background: #155fb8;
    border-color: #b8d9ff;
}
QPushButton#navButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 19px;
    color: #d5e2ef;
    padding: 9px 16px;
    text-align: right;
    min-height: 42px;
    font-size: 13.5px;
    font-weight: 750;
    icon-size: 20px;
}
QPushButton#navButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2169ad, stop:0.55 #174c82, stop:1 #103459);
    color: #ffffff;
    border: 1px solid #66b3ff;
}
QPushButton#navButton:hover {
    background: #123351;
    border-color: #315c7c;
    color: #ffffff;
}
QPushButton#futureNavButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #102840, stop:1 #081b2e);
    border: 1px solid #2a4c68;
    border-radius: 20px;
    color: #9aacbf;
    padding: 8px 12px;
    text-align: center;
    min-height: 33px;
    font-size: 12.5px;
    font-weight: 650;
}
QPushButton#futureNavButton:disabled {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0e2338, stop:1 #071928);
    border-color: #24435d;
    color: #8497aa;
}
QPushButton#topNavButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #17314c, stop:0.52 #10253b, stop:1 #0c1d30);
    border: 1px solid #315671;
    border-radius: 20px;
    color: #d2dfed;
    padding: 9px 22px;
    min-height: 38px;
    min-width: 146px;
    font-size: 12.5px;
    font-weight: 700;
}
QPushButton#topNavButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f86f4, stop:0.58 #236bd2, stop:1 #164a8b);
    color: #ffffff;
    border-color: #76b8ff;
}
QPushButton#topNavButton:hover {
    background: #142f4d;
    border-color: #4d8bc1;
    color: #ffffff;
}
QPushButton#topNavButton:pressed {
    background: #0f3766;
    border-color: #a4d4ff;
    padding-top: 9px;
    padding-bottom: 7px;
}
QGroupBox#mainActionsCard[topActions="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #17324d, stop:0.48 #10263d, stop:1 #0b1e31);
    border: 1px solid #315b78;
    border-radius: 24px;
    padding: 9px 14px;
}
QPushButton[topAction="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d3b56, stop:1 #142f49);
    border: 1px solid #477897;
    border-radius: 17px;
    color: #f1f8ff;
    padding: 9px 18px;
    min-height: 40px;
    min-width: 108px;
    font-size: 12.5px;
    font-weight: 750;
}
QPushButton[topAction="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #275074, stop:1 #1a3d5d);
    border-color: #78aacb;
}
QPushButton[topAction="true"]:pressed {
    background: #15334f;
    border-color: #8ab8d8;
    padding-top: 10px;
    padding-bottom: 8px;
}
QPushButton[topAction="true"]:disabled {
    background: #14263a;
    border-color: #2f485f;
    color: #8093a6;
}
QPushButton#smartImportButton[topAction="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26a66d, stop:0.55 #188655, stop:1 #116541);
    border-color: #72d9a6;
    color: #f2fff8;
}
QPushButton#smartImportButton[topAction="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #31bc7d, stop:0.55 #209b64, stop:1 #15734a);
    border-color: #9be8bf;
}
QPushButton#smartImportButton[topAction="true"]:pressed {
    background: #0f5d3d;
    border-color: #bdf3d2;
}
QPushButton#primaryActionButton[topAction="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f8dff, stop:0.55 #2679e8, stop:1 #1b5eb8);
    border-color: #8ac3ff;
    border-radius: 19px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 800;
    min-height: 42px;
    min-width: 152px;
    padding: 10px 26px;
}
QPushButton#primaryActionButton[topAction="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4aa0ff, stop:0.55 #2d86f5, stop:1 #2169ca);
}
QPushButton#primaryActionButton[topAction="true"]:pressed {
    background: #155fb8;
    border-color: #c2e0ff;
}
QPushButton#newWorkButton, QPushButton#validateActionButton, QPushButton#openOutputButton {
    background: #1a334b;
    border-color: #416886;
}
QPushButton#newWorkButton[topAction="true"], QPushButton#validateActionButton[topAction="true"], QPushButton#openOutputButton[topAction="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d3b56, stop:1 #142f49);
    border-color: #477897;
    border-radius: 17px;
}
QPushButton#newWorkButton[topAction="true"]:hover, QPushButton#validateActionButton[topAction="true"]:hover, QPushButton#openOutputButton[topAction="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #244760, stop:1 #17334c);
    border-color: #6c9ec2;
}
QPushButton#newWorkButton[topAction="true"]:pressed, QPushButton#validateActionButton[topAction="true"]:pressed, QPushButton#openOutputButton[topAction="true"]:pressed {
    background: #10283f;
    border-color: #9fc8e6;
}
QPushButton#openOutputButton[topAction="true"]:disabled {
    background: #14263a;
    border-color: #2f485f;
    color: #8093a6;
}
QPushButton#advancedToggleButton {
    background: #122235;
    border-style: dashed;
}
QLabel#processingStatusLabel, QLabel#logHeaderLabel {
    background: #10263c;
    border: 1px solid #2b4054;
    border-radius: 999px;
    padding: 5px 11px;
    font-weight: 600;
    color: #d9e7f7;
}
QLabel#queueEditStatusLabel {
    color: #f1d18a;
}
QLabel#queueSummaryLabel {
    color: #d7e5f6;
    background: #102236;
    border: 1px solid #243d54;
    border-radius: 12px;
    padding: 8px 10px;
}
QLabel#queueDetailsLabel {
    color: #e4edf8;
    background: #0e2033;
    border: 1px solid #253f56;
    border-radius: 12px;
    padding: 9px 11px;
    line-height: 1.35;
}
QLabel#metricValue {
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1b3a56, stop:1 #132c45);
    border: 1px solid #345a75;
    border-radius: 14px;
    padding: 8px 10px;
    min-height: 34px;
}
QLabel#metricCaption {
    color: #aebdd0;
    background: #11283e;
    border: 1px solid #2a4861;
    border-radius: 12px;
    padding: 5px 9px;
    min-height: 24px;
}
QLabel#emptyStateLabel {
    color: #aebdd0;
    background: #0f2337;
    border: 1px dashed #2e4b64;
    border-radius: 16px;
    padding: 14px;
}
QFrame#dashboardShell, QFrame#sideRail, QFrame#topNav, QFrame#topNavStrip, QFrame#bottomStatusBar {
    background: #07111d;
}
QFrame#sideRail {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #071525, stop:0.5 #050f1c, stop:1 #07121f);
    border-left: 1px solid #1a344b;
    border-radius: 0;
}
QFrame#sidebarNavGroup {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #142f4c, stop:0.46 #0d2238, stop:1 #071827);
    border: 1px solid #2b536f;
    border-radius: 27px;
}
QFrame#sidebarCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #142d49, stop:0.46 #0c2137, stop:1 #061725);
    border: 1px solid #2a4f69;
    border-radius: 27px;
}
QFrame#sidebarCard[sidebarRole="future"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #15304c, stop:0.48 #0d2238, stop:1 #071725);
    border-color: #2b536d;
}
QFrame#sidebarCard[sidebarRole="status"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #16334f, stop:0.43 #0c243a, stop:1 #061624);
    border-color: #315b78;
}
QFrame#sidebarCard[sidebarRole="appearance"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #173452, stop:0.42 #0c243c, stop:1 #061725);
    border-color: #315f82;
}
QFrame#sidebarReadyFooter {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #12304a, stop:0.55 #0a2136, stop:1 #061725);
    border: 1px solid #2e5874;
    border-radius: 23px;
}
QLabel#sidebarCardTitle {
    background: transparent;
    border: none;
    color: #f6fbff;
    font-size: 14px;
    font-weight: 800;
    min-height: 24px;
}
QLabel#sidebarStatusLabel, QLabel#sidebarThemeLabel, QLabel#sidebarStatusValue {
    color: #c9d8e6;
    background: transparent;
    line-height: 1.35;
    font-size: 12.5px;
    min-height: 22px;
}
QLabel#sidebarStatusValue {
    color: #f5fbff;
    font-weight: 750;
}
QFrame#sidebarStatusRow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #132d47, stop:0.55 #0d2237, stop:1 #091a2b);
    border: 1px solid #2a506d;
    border-radius: 20px;
    min-height: 34px;
}
QLabel#sidebarGreenDot {
    background: #40e287;
    border: 1px solid #8ff0bc;
    border-radius: 5px;
    min-width: 10px;
    min-height: 10px;
    max-width: 10px;
    max-height: 10px;
}
QFrame#appearancePanel {
    background: qradialgradient(cx:0.82, cy:0.22, radius:0.95, fx:0.82, fy:0.22, stop:0 #1e5e95, stop:0.34 #123b62, stop:1 #071827);
    border: 1px solid #3a77a0;
    border-radius: 24px;
    min-height: 126px;
}
QLabel#appearanceIndicator {
    background: qradialgradient(cx:0.35, cy:0.3, radius:0.78, fx:0.35, fy:0.3, stop:0 #7ec7ff, stop:0.45 #2c79bf, stop:1 #123d6d);
    border: 1px solid #83c9ff;
    border-radius: 20px;
    color: #ffffff;
    font-size: 18px;
    font-weight: 800;
    min-width: 40px;
    min-height: 40px;
    max-width: 40px;
    max-height: 40px;
}
QLabel#appearanceText {
    background: transparent;
    border: none;
    color: #f3f8ff;
    font-size: 13px;
    font-weight: 750;
    min-height: 24px;
}
QLabel#appearanceHint {
    background: transparent;
    border: none;
    color: #a9bdd1;
    font-size: 11.5px;
    font-weight: 600;
    min-height: 22px;
}
QLabel#appearanceModePill {
    background: #17466f;
    border: 1px solid #5da6dc;
    border-radius: 16px;
    color: #dceeff;
    font-size: 11.5px;
    font-weight: 750;
    padding: 6px 16px;
    min-width: 78px;
    min-height: 36px;
}
QLabel#readyIndicator {
    background: #40e287;
    border: 1px solid #8ff0bc;
    border-radius: 6px;
    min-width: 12px;
    min-height: 12px;
    max-width: 12px;
    max-height: 12px;
}
QLabel#sidebarReadyText {
    color: #f2fbf6;
    background: transparent;
    font-size: 13px;
    font-weight: 800;
}
QFrame#topNav {
    background: transparent;
    border: none;
}
QFrame#topNavStrip {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #173450, stop:0.5 #10283f, stop:1 #0c2034);
    border: 1px solid #345d78;
    border-radius: 26px;
}
QFrame#bottomStatusBar {
    background: #07111d;
    border-top: 1px solid #1d3448;
}
QCheckBox, QRadioButton {
    spacing: 8px;
}
QRadioButton {
    background: #0b1724;
    border: 1px solid #243d54;
    border-radius: 11px;
    color: #d9e7f7;
    padding: 7px 12px;
    min-height: 28px;
}
QRadioButton:hover {
    border-color: #4d7fa7;
    background: #102237;
}
QRadioButton:checked {
    background: #173f73;
    border-color: #2d87f0;
    color: #ffffff;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
}
QRadioButton::indicator {
    width: 0;
    height: 0;
}
QScrollBar:vertical {
    background: #07111d;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #355169;
    min-height: 28px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #4d6f8b;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: #07111d;
    height: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #355169;
    min-width: 28px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #4d6f8b;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: transparent;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""

QUEUE_STATUS_COLORS: dict[JobStatus, tuple[str, str]] = {
    JobStatus.DRAFT: ("#243445", "#d9e7f7"),
    JobStatus.READY: ("#163f34", "#bff4dc"),
    JobStatus.WARNING: ("#4d3d18", "#ffe6a3"),
    JobStatus.VALIDATION_ERROR: ("#4d2525", "#ffc4c4"),
    JobStatus.QUEUED: ("#273545", "#d9e7f7"),
    JobStatus.DOWNLOADING: ("#1d4773", "#d2ecff"),
    JobStatus.CUTTING: ("#1d4773", "#d2ecff"),
    JobStatus.VERIFYING: ("#1d4773", "#d2ecff"),
    JobStatus.DONE: ("#173f2a", "#c7f6d8"),
    JobStatus.FAILED: ("#542929", "#ffd1d1"),
    JobStatus.SKIPPED: ("#40364d", "#ead8ff"),
    JobStatus.CANCELLED: ("#343a43", "#d2d9e2"),
}

URL_IN_LOG_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
SMART_PASTE_BLOCKING_WARNING_MARKERS = (
    "نهاية المقطع قبل بدايته",
    "وقت الاستثناء غير صحيح",
)


def safe_log_text(message: str) -> str:
    """Remove sensitive URL query details from runtime logs."""

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url
        query_suffix = "?…" if parts.query else ""
        return f"{parts.scheme}://{parts.netloc}{parts.path}{query_suffix}"

    return URL_IN_LOG_PATTERN.sub(replace_url, str(message))


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
        self.setStyleSheet(APP_STYLE_SHEET)

        self.message_input = QTextEdit()
        self.message_input.setObjectName("pasteBox")
        self.message_input.setPlaceholderText("الصق الرسالة كاملة هنا، بما في ذلك رابط الفيديو والمقاطع.")
        self.message_input.setMinimumHeight(120)

        self.summary_label = QLabel("الصق الرسالة ثم اضغط فحص الرسالة.")
        self.summary_label.setWordWrap(True)
        self.review_status_label = QLabel("")
        self.review_status_label.setWordWrap(True)
        self.detected_url_label = QLabel("غير مكتشف")
        self.detected_url_label.setWordWrap(True)
        self.detected_project_label = QLabel("غير مكتشف")
        self.detected_project_label.setWordWrap(True)

        self.clips_preview_table = QTableWidget(0, 6)
        self.clips_preview_table.setShowGrid(False)
        self.clips_preview_table.verticalHeader().setDefaultSectionSize(34)
        self.clips_preview_table.setHorizontalHeaderLabels(
            ["الرقم", "العنوان", "البداية", "النهاية", "الاستثناءات", "الحالة / الملاحظات"]
        )
        self.clips_preview_table.verticalHeader().setVisible(False)
        self.clips_preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.clips_preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.clips_preview_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.warnings_area = QTextEdit()
        self.warnings_area.setObjectName("warningArea")
        self.warnings_area.setReadOnly(True)
        self.warnings_area.setMaximumHeight(95)

        self.unparsed_area = QTextEdit()
        self.unparsed_area.setObjectName("reviewArea")
        self.unparsed_area.setReadOnly(True)
        self.unparsed_area.setMaximumHeight(95)

        self.analysis_details_area = QTextEdit()
        self.analysis_details_area.setObjectName("reviewArea")
        self.analysis_details_area.setReadOnly(True)
        self.analysis_details_area.setMaximumHeight(130)

        self.parse_button = QPushButton("فحص الرسالة")
        self.apply_button = QPushButton("تطبيق النتائج")
        self.copy_debug_button = QPushButton("نسخ تقرير التحليل")
        self.cancel_button = QPushButton("إلغاء")
        self.parse_button.setObjectName("smartImportButton")
        self.apply_button.setObjectName("primaryActionButton")
        self.review_status_label.setObjectName("statusHelperLabel")
        self.apply_button.setEnabled(False)
        self.copy_debug_button.setEnabled(False)

        self._build_ui()
        self.parse_button.clicked.connect(self.generate_preview)
        self.apply_button.clicked.connect(self._accept_preview)
        self.copy_debug_button.clicked.connect(self.copy_debug_report)
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

        summary_group = QGroupBox("ملخص الاستيراد")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.addWidget(self.summary_label)
        summary_layout.addWidget(self.review_status_label)
        layout.addWidget(summary_group)

        source_group = QGroupBox("المصدر المكتشف")
        source_layout = QGridLayout(source_group)
        source_layout.addWidget(QLabel("رابط الفيديو"), 0, 0)
        source_layout.addWidget(self.detected_url_label, 0, 1)
        source_layout.addWidget(QLabel("اسم المشروع"), 1, 0)
        source_layout.addWidget(self.detected_project_label, 1, 1)
        source_layout.setColumnStretch(1, 1)
        layout.addWidget(source_group)

        layout.addWidget(QLabel("المقاطع المكتشفة"))
        layout.addWidget(self.clips_preview_table, stretch=1)
        layout.addWidget(QLabel("التحذيرات"))
        layout.addWidget(self.warnings_area)
        layout.addWidget(QLabel("أسطر تحتاج مراجعة"))
        layout.addWidget(self.unparsed_area)
        layout.addWidget(QLabel("تفاصيل التحليل"))
        layout.addWidget(self.analysis_details_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.copy_debug_button)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

    def generate_preview(self) -> SmartPastePreview:
        self.preview = parse_smart_paste_message(self.message_input.toPlainText())
        self._show_preview(self.preview)
        return self.preview

    def _show_preview(self, preview: SmartPastePreview) -> None:
        needs_review = bool(preview.warnings or preview.unparsed_lines or any(clip.confidence != "high" for clip in preview.clips))
        blocking_errors = self._blocking_preview_errors(preview)
        self.summary_label.setText(
            "\n".join(
                [
                    f"عدد المقاطع المكتشفة: {len(preview.clips)}",
                    f"عدد التحذيرات: {len(preview.warnings)}",
                    f"عدد الأخطاء: {len(blocking_errors)}",
                    f"هل توجد أسطر تحتاج مراجعة: {'نعم' if preview.unparsed_lines else 'لا'}",
                    f"هل يوجد مقاطع تحتاج مراجعة: {'نعم' if needs_review else 'لا'}",
                ]
            )
        )
        self.review_status_label.setText(self._preview_review_status(preview, blocking_errors))
        self.detected_url_label.setText(self._safe_preview_url(preview.video_urls[0]) if preview.video_urls else "غير مكتشف")
        self.detected_project_label.setText(preview.project_title or "غير مكتشف")

        self.clips_preview_table.setRowCount(0)
        for clip in preview.clips:
            row = self.clips_preview_table.rowCount()
            self.clips_preview_table.insertRow(row)
            self.clips_preview_table.setItem(row, 0, QTableWidgetItem(str(clip.number)))
            self.clips_preview_table.setItem(row, 1, QTableWidgetItem(clip.title))
            self.clips_preview_table.setItem(row, 2, QTableWidgetItem(clip.start))
            self.clips_preview_table.setItem(row, 3, QTableWidgetItem(clip.end))
            self.clips_preview_table.setItem(row, 4, QTableWidgetItem(clip.exclusions_text))
            self.clips_preview_table.setItem(row, 5, QTableWidgetItem(self._clip_review_notes(clip, preview)))

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
        self.analysis_details_area.setPlainText(
            safe_log_text(format_smart_paste_debug_report(preview, self.message_input.toPlainText()))
        )
        self.apply_button.setEnabled(bool(preview.video_urls or preview.clips) and not blocking_errors)
        self.copy_debug_button.setEnabled(True)

    def _blocking_preview_errors(self, preview: SmartPastePreview) -> list[str]:
        return [
            warning.message_ar
            for warning in preview.warnings
            if any(marker in warning.message_ar for marker in SMART_PASTE_BLOCKING_WARNING_MARKERS)
        ]

    def _preview_review_status(self, preview: SmartPastePreview, blocking_errors: list[str]) -> str:
        if blocking_errors:
            return "توجد أخطاء تحتاج مراجعة قبل الاستيراد"
        if preview.warnings:
            return "توجد تحذيرات، راجعها قبل الاستيراد"
        return "لا توجد تحذيرات واضحة."

    def _safe_preview_url(self, url: str) -> str:
        return safe_log_text(url)

    def _clip_review_notes(self, clip: SmartPasteClip, preview: SmartPastePreview) -> str:
        notes: list[str] = []
        if clip.confidence != "high":
            notes.append("هذا المقطع يحتاج مراجعة قبل الاعتماد")
        if clip.multi_part:
            notes.append(f"مقطع مركب: {clip.parts_text}")
        if clip.notes_text:
            notes.append(clip.notes_text)

        source_line_numbers = {clip.line_number}
        for line_numbers in clip.source_lines.values():
            source_line_numbers.update(line_numbers)
        for warning in preview.warnings:
            if warning.line_number in source_line_numbers and warning.message_ar not in notes:
                notes.append(warning.message_ar)
        if clip.source_lines:
            notes.append(f"تفاصيل التحليل: {clip.source_lines}")
        return "\n".join(notes) if notes else "جاهز"

    def _accept_preview(self) -> None:
        if self.preview is None:
            self.generate_preview()
        if self.preview is None:
            return
        if self._blocking_preview_errors(self.preview):
            self.review_status_label.setText("توجد أخطاء تحتاج مراجعة قبل الاستيراد")
            self.apply_button.setEnabled(False)
            return
        if self.preview.video_urls or self.preview.clips:
            self.accept()

    def copy_debug_report(self) -> None:
        if self.preview is None:
            self.generate_preview()
        if self.preview is None:
            return
        QApplication.clipboard().setText(
            safe_log_text(format_smart_paste_debug_report(self.preview, self.message_input.toPlainText()))
        )
        self.review_status_label.setText("تم نسخ تقرير التحليل")


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
        clip_fade: ClipFade | None = None,
        clip_black_flash: ClipBlackFlash | None = None,
        export_quality: ExportQualitySettings | None = None,
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
        self.clip_fade = clip_fade or ClipFade()
        self.clip_black_flash = clip_black_flash or ClipBlackFlash()
        self.export_quality = export_quality or ExportQualitySettings()

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
                clip_fade=self.clip_fade,
                clip_black_flash=self.clip_black_flash,
                export_quality=self.export_quality,
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
        job.add_log("جاري معالجة المهمة في الخلفية")
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
                clip_fade=self._effective_job_clip_fade(job),
                clip_black_flash=self._effective_job_clip_black_flash(job),
                export_quality=self._effective_job_export_quality(job),
            )
        except Exception as error:
            if str(error).strip() == AR_OUTPUT_CREATE_FAILED:
                job.mark_failed(AR_OUTPUT_CREATE_FAILED, "output")
                self.progress.emit(AR_OUTPUT_CREATE_FAILED)
                raise VideoProcessingError(AR_OUTPUT_CREATE_FAILED) from error
            stage = job.failure_stage or ("download" if job.source_type == QueueVideoSourceType.YOUTUBE else "cutting")
            safe_error = safe_log_text(str(error))
            if job.source_type == QueueVideoSourceType.YOUTUBE:
                message = f"فشل تحميل أو معالجة رابط يوتيوب: {safe_error}"
                job.mark_failed(message, stage)
                self.progress.emit(message)
                raise VideoProcessingError(message) from error
            message = f"فشل قص المقاطع: {safe_error}"
            job.mark_failed(message, stage)
            self.progress.emit(message)
            raise
        job.output_folder = str(result.project_output_folder)
        success_message = f"تم حفظ النتائج داخل: {result.project_output_folder}"
        job.add_log(success_message)
        self.progress.emit(success_message)

        row = self._job_row(job)
        if row is not None:
            self.job_updated.emit(row)

    def _effective_job_video_speed(self, job: VideoJob) -> float:
        return job.settings.speed if job.settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED

    def _effective_job_volume_percent(self, job: VideoJob) -> int:
        return job.settings.volume_percent if job.settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT

    def _effective_job_clip_fade(self, job: VideoJob) -> ClipFade:
        if not job.settings.fade_enabled:
            return ClipFade()
        return ClipFade(
            enabled=True,
            fade_in_seconds=job.settings.fade_in_seconds,
            fade_out_seconds=job.settings.fade_out_seconds,
        )

    def _effective_job_clip_black_flash(self, job: VideoJob) -> ClipBlackFlash:
        if not job.settings.black_flash_enabled:
            return ClipBlackFlash()
        return ClipBlackFlash(
            enabled=True,
            duration_seconds=job.settings.black_flash_duration_seconds,
        )

    def _effective_job_export_quality(self, job: VideoJob) -> ExportQualitySettings:
        if not job.settings.export_quality_enabled:
            return ExportQualitySettings()
        return ExportQualitySettings(
            enabled=True,
            quality_preset=job.settings.quality_preset,
            resolution_limit=job.settings.resolution_limit,
        )

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
        def emit_job_progress(message: str) -> None:
            clean_message = safe_log_text(str(message).strip())
            if not clean_message:
                return
            job.add_log(clean_message)
            if "تنزيل" in clean_message or "تحميل" in clean_message:
                job.failure_stage = "download"
            if "قص" in clean_message or "تم تنزيل الفيديو" in clean_message:
                job.failure_stage = "cutting"
            self.progress.emit(clean_message)

        if job.source_type != QueueVideoSourceType.YOUTUBE:
            return emit_job_progress

        job.failure_stage = "download"
        job.add_log("جاري تحميل الفيديو في الخلفية")
        self.progress.emit("جاري تحميل الفيديو في الخلفية")
        cutting_message_sent = False

        def emit_progress(message: str) -> None:
            nonlocal cutting_message_sent
            emit_job_progress(message)
            if not cutting_message_sent and "تم تنزيل الفيديو" in message:
                cutting_message_sent = True
                job.failure_stage = "cutting"
                job.add_log("جاري قص المقاطع في الخلفية")
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
        self._output_root_warning = ""
        try:
            output_resolution = resolve_output_root()
            self.output_root = output_resolution.path
            self._output_root_warning = output_resolution.warning
        except OutputPathError as error:
            self.output_root = documents_output_root()
            self._output_root_warning = str(error)
        self.video_processor = VideoProcessor(self.output_root)
        self.job_queue: list[VideoJob] = []
        self._processing_thread: QThread | None = None
        self._processing_worker: ProcessingWorker | None = None
        self._queue_processing_thread: QThread | None = None
        self._queue_processing_worker: QueueProcessingWorker | None = None
        self._queue_auto_continue_after_worker = False
        self._editing_queue_job: VideoJob | None = None
        self._last_output_folder: Path | None = None
        self._window_state_before_fullscreen: Qt.WindowStates | None = None
        self._window_geometry_before_fullscreen: QByteArray | None = None

        self.setWindowTitle(APP_NAME)
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1180, 760)

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
        self.smart_paste_button = QPushButton("تحليل النص")
        self.global_smart_import_button = QPushButton("استيراد ذكي")
        self.clear_paste_text_button = QPushButton("مسح النص")
        self.replace_import_button = QPushButton("استبدال الجدول الحالي")
        self.append_import_button = QPushButton("إضافة إلى جدول المقاطع")
        self.queue_import_button = QPushButton("إضافة إلى قائمة الانتظار")
        self.import_summary_label = QLabel("سيظهر ملخص الاستيراد بعد تحليل النص أو تحميل مصدر.")
        self.import_extracted_clips_table = QTableWidget(0, 7)
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
        self.copy_queue_job_details_button = QPushButton("نسخ تفاصيل المهمة")
        self.queue_job_details_label = QLabel("لم يتم تحديد مهمة")
        self.queue_job_clips_table = QTableWidget(0, 5)
        self.queue_advanced_toggle_button = QPushButton("إدارة قائمة الانتظار المتقدمة")
        self.queue_advanced_group = QGroupBox("إدارة قائمة الانتظار المتقدمة")
        self.queue_advanced_controls_widget = QWidget()
        self.clips_table = QTableWidget(0, 5)
        self.classification_rules_table = QTableWidget(0, 4)
        self.add_row_button = QPushButton("إضافة مقطع")
        self.clips_import_shortcut_button = QPushButton("استيراد ذكي")
        self.clips_new_work_shortcut_button = QPushButton("عمل جديد")
        self.clips_clear_shortcut_button = QPushButton("مسح القائمة")
        self.clips_delete_shortcut_button = QPushButton("حذف المحدد")
        self.clips_point_shortcut_button = QPushButton("نقطة المقطع")
        self.clips_export_shortcut_button = QPushButton("تصدير")
        self.import_excel_button = QPushButton("استيراد من Excel / CSV")
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
        self.black_fade_enabled_checkbox = QCheckBox("إضافة بداية ونهاية سوداء تدريجية")
        self.fade_in_duration_combo = QComboBox()
        self.fade_out_duration_combo = QComboBox()
        self.black_fade_status_label = QLabel("الإعدادات الافتراضية آمنة")
        self.black_flash_enabled_checkbox = QCheckBox("إضافة وميض أسود عند الاستثناء")
        self.black_flash_duration_combo = QComboBox()
        self.black_flash_status_label = QLabel("الإعدادات الافتراضية آمنة")
        self.export_quality_enabled_checkbox = QCheckBox("تخصيص جودة التصدير")
        self.export_quality_preset_combo = QComboBox()
        self.resolution_limit_combo = QComboBox()
        self.export_quality_status_label = QLabel("الإعدادات الافتراضية آمنة")
        self.readiness_button = QPushButton("فحص جاهزية البرنامج")
        self.smart_validation_button = QPushButton("فحص ذكي قبل القص")
        self.validate_button = QPushButton("فحص ذكي قبل القص")
        self.start_button = QPushButton("بدء القص")
        self.new_work_button = QPushButton("عمل جديد")
        self.direct_cut_button = QPushButton("بدء القص المباشر - وضع قديم")
        self.open_output_button = QPushButton("فتح مجلد النتائج")
        self.processing_status_label = QLabel("الحالة: جاهز")
        self.show_global_log_button = QPushButton("عرض السجل العام")
        self.log_header_label = QLabel("سجل عام")
        self.log_area = QTextEdit()
        self.page_stack = QStackedWidget()
        self.nav_import_button = QPushButton("الاستيراد")
        self.nav_clips_button = QPushButton("المقاطع")
        self.nav_queue_button = QPushButton("قائمة الانتظار")
        self.nav_logs_button = QPushButton("السجل")
        self.top_nav_buttons: dict[str, QPushButton] = {}
        self.dashboard_source_label = QLabel()
        self.dashboard_clips_label = QLabel()
        self.dashboard_queue_label = QLabel()
        self.dashboard_status_label = QLabel()
        self.dashboard_output_label = QLabel()
        self.operations_log_table = QTableWidget(0, 5)
        self.queue_snapshot_table = QTableWidget(0, 4)
        self.current_work_label = QLabel()
        self.system_status_label = QLabel()
        self.selected_clip_details_label = QLabel("لم يتم تحديد مقطع")
        self.selected_clip_preview_label = QLabel("المعاينة المتقدمة قريبًا")
        self.queue_current_job_label = QLabel("لا توجد وظيفة قيد المعالجة الآن")
        self.queue_info_preview_label = QLabel("لا توجد معلومات إضافية متاحة")
        self.queue_job_log_area = QTextEdit()
        self.queue_stop_all_button = QPushButton("إيقاف الكل — قريبًا")
        self.queue_move_up_button = QPushButton("تحريك لأعلى — قريبًا")
        self.queue_move_down_button = QPushButton("تحريك لأسفل — قريبًا")
        self.queue_reorder_button = QPushButton("إعادة الترتيب — قريبًا")
        self.future_reports_button = QPushButton("تقارير متقدمة — قريبًا")
        self.future_schedule_button = QPushButton("الجدولة — قريبًا")
        self.future_templates_button = QPushButton("مشاركة القوالب — قريبًا")
        self.sidebar_engine_status_label = QLabel("جاهز")
        self.sidebar_smart_status_label = QLabel("جاهز")
        self.sidebar_last_job_label = QLabel("لا توجد")
        self.sidebar_queue_count_label = QLabel("0")
        self.sidebar_bottom_status_label = QLabel("جاهز")
        self.bottom_status_label = QLabel("جاهز")
        self.bottom_output_label = QLabel(str(self.output_root))
        self.scroll_area = QScrollArea()
        self._global_log_messages: list[str] = []
        self._active_log_job: VideoJob | None = None

        self._apply_branding()
        self._apply_visual_polish()
        self.setCentralWidget(self._build_scrollable_ui())
        self._connect_signals()
        self._reset_classification_rules(log=False)
        self._update_source_inputs()
        self._update_speed_volume_controls()
        self._update_queue_edit_controls()
        self._update_selected_queue_job_details()
        self.show_global_log()
        if self._output_root_warning:
            self._append_log(self._output_root_warning)
        self.open_output_button.setEnabled(False)
        self.stop_queue_after_current_button.setEnabled(False)

    def _build_scrollable_ui(self) -> QScrollArea:
        content = self._build_ui()
        self.scroll_area.setWidget(content)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return self.scroll_area

    def _build_ui(self) -> QWidget:
        shell = QFrame()
        shell.setObjectName("dashboardShell")
        layout = QHBoxLayout(shell)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 10, 12, 8)

        content = QFrame()
        content.setObjectName("mainContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addWidget(self._build_top_navigation())
        content_layout.addWidget(self._build_action_section())

        self.page_stack.addWidget(self._page_scroll("الاستيراد", self._build_import_page()))
        self.page_stack.addWidget(self._page_scroll("المقاطع", self._build_clips_page()))
        self.page_stack.addWidget(self._page_scroll("قائمة الانتظار", self._build_queue_dashboard_page()))
        self.page_stack.addWidget(self._page_scroll("السجل", self._build_logs_dashboard_page()))
        content_layout.addWidget(self.page_stack, stretch=1)
        content_layout.addWidget(self._build_bottom_status_bar())

        layout.addWidget(content, stretch=1)
        layout.addWidget(self._build_side_rail())

        self.switch_dashboard_page("logs")
        self._refresh_dashboard_overview()
        return shell

    def _page_scroll(self, name: str, page: QWidget) -> QScrollArea:
        page.setObjectName(f"{name}Page")
        scroll = QScrollArea()
        scroll.setObjectName("pageScrollArea")
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return scroll

    def _build_side_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("sideRail")
        rail.setFixedWidth(258)
        layout = QVBoxLayout(rail)
        layout.setSpacing(9)
        layout.setContentsMargins(12, 12, 12, 10)

        layout.addWidget(self._build_header_section())
        nav_group = QFrame()
        nav_group.setObjectName("sidebarNavGroup")
        nav_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        nav_group.setMaximumHeight(205)
        nav_layout = QVBoxLayout(nav_group)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(5)
        for button in (
            self.nav_import_button,
            self.nav_clips_button,
            self.nav_queue_button,
            self.nav_logs_button,
        ):
            nav_layout.addWidget(button)
        layout.addWidget(nav_group)
        layout.addWidget(self._build_sidebar_future_card())
        layout.addWidget(self._build_sidebar_status_card())
        layout.addWidget(self._build_sidebar_theme_card())
        layout.addStretch(1)
        layout.addWidget(self._build_sidebar_ready_footer())
        return rail

    def _build_sidebar_future_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebarCard")
        frame.setProperty("sidebarRole", "future")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        frame.setMaximumHeight(155)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(8)
        title = QLabel("ميزات قادمة")
        title.setObjectName("sidebarCardTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(self.future_reports_button)
        layout.addWidget(self.future_schedule_button)
        layout.addWidget(self.future_templates_button)
        return frame

    def _build_sidebar_status_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebarCard")
        frame.setProperty("sidebarRole", "status")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        frame.setMaximumHeight(220)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        title = QLabel("الحالة العامة")
        title.setObjectName("sidebarCardTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(self._build_sidebar_status_row("المحرك", self.sidebar_engine_status_label, show_dot=True))
        layout.addWidget(self._build_sidebar_status_row("الفحص الذكي", self.sidebar_smart_status_label, show_dot=True))
        layout.addWidget(self._build_sidebar_status_row("آخر مهمة", self.sidebar_last_job_label))
        layout.addWidget(self._build_sidebar_status_row("في قائمة الانتظار", self.sidebar_queue_count_label))
        return frame

    def _build_sidebar_status_row(self, label_text: str, value_label: QLabel, show_dot: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("sidebarStatusRow")
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        row.setMinimumHeight(34)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)
        label = QLabel(label_text)
        label.setObjectName("sidebarStatusLabel")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(22)
        value_label.setObjectName("sidebarStatusValue")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setMinimumHeight(22)
        layout.addWidget(value_label, stretch=1)
        layout.addWidget(label, stretch=1)
        if show_dot:
            dot = QLabel()
            dot.setObjectName("sidebarGreenDot")
            dot.setFixedSize(10, 10)
            layout.addWidget(dot)
        return row

    def _build_sidebar_theme_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebarCard")
        frame.setProperty("sidebarRole", "appearance")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        frame.setMaximumHeight(206)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel("المظهر")
        title.setObjectName("sidebarCardTitle")
        title.setAlignment(Qt.AlignCenter)
        appearance = QFrame()
        appearance.setObjectName("appearancePanel")
        appearance.setMinimumHeight(126)
        appearance_layout = QHBoxLayout(appearance)
        appearance_layout.setContentsMargins(13, 10, 13, 18)
        appearance_layout.setSpacing(10)
        moon = QLabel("◑")
        moon.setObjectName("appearanceIndicator")
        moon.setAlignment(Qt.AlignCenter)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        mode = QLabel("الوضع الحالي: داكن")
        mode.setObjectName("appearanceText")
        mode.setAlignment(Qt.AlignCenter)
        mode.setMinimumHeight(24)
        hint = QLabel("واجهة كحلية هادئة")
        hint.setObjectName("appearanceHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setMinimumHeight(22)
        state = QLabel("مفعّل")
        state.setObjectName("appearanceModePill")
        state.setAlignment(Qt.AlignCenter)
        state.setMinimumSize(78, 36)
        state.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(title)
        text_layout.addWidget(mode)
        text_layout.addWidget(hint)
        text_layout.addWidget(state, alignment=Qt.AlignCenter)
        appearance_layout.addLayout(text_layout, stretch=1)
        appearance_layout.addWidget(moon)
        layout.addWidget(appearance)
        return frame

    def _build_sidebar_ready_footer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebarReadyFooter")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        frame.setMaximumHeight(44)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(13, 8, 13, 8)
        layout.setSpacing(9)
        layout.addWidget(self.sidebar_bottom_status_label)
        layout.addStretch(1)
        indicator = QLabel()
        indicator.setObjectName("readyIndicator")
        indicator.setFixedSize(12, 12)
        layout.addWidget(indicator)
        return frame

    def _build_top_navigation(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topNav")
        frame.setMinimumHeight(76)
        frame.setMaximumHeight(76)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        strip = QFrame()
        strip.setObjectName("topNavStrip")
        strip.setMinimumHeight(72)
        strip.setMaximumHeight(72)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(7, 7, 7, 7)
        strip_layout.setSpacing(6)
        self.top_nav_buttons = {}
        for key, button in (
            ("logs", self.nav_logs_button),
            ("queue", self.nav_queue_button),
            ("clips", self.nav_clips_button),
            ("import", self.nav_import_button),
        ):
            top_button = QPushButton(button.text())
            top_button.setObjectName("topNavButton")
            top_button.setCheckable(True)
            top_button.setMinimumSize(146, 38)
            top_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            top_button.clicked.connect(lambda _checked=False, page=key: self.switch_dashboard_page(page))
            self.top_nav_buttons[key] = top_button
            strip_layout.addWidget(top_button)
        layout.addWidget(strip)
        layout.addStretch(1)
        return frame

    def _build_bottom_status_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("bottomStatusBar")
        frame.setMaximumHeight(24)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 1, 8, 1)
        layout.setSpacing(8)
        layout.addWidget(self.bottom_status_label)
        layout.addStretch(1)
        layout.addWidget(self.bottom_output_label)
        language_label = QLabel("العربية | داكن")
        language_label.setObjectName("sectionHelpText")
        layout.addWidget(language_label)
        return frame

    def switch_dashboard_page(self, page: str) -> None:
        page_indexes = {"import": 0, "clips": 1, "queue": 2, "logs": 3}
        if page not in page_indexes:
            return
        self.page_stack.setCurrentIndex(page_indexes[page])
        for key, button in {
            "import": self.nav_import_button,
            "clips": self.nav_clips_button,
            "queue": self.nav_queue_button,
            "logs": self.nav_logs_button,
        }.items():
            button.setChecked(key == page)
        for key, button in self.top_nav_buttons.items():
            button.setChecked(key == page)
        self._refresh_dashboard_overview()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.exit_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def enter_fullscreen(self) -> None:
        if self.isFullScreen():
            return
        self._window_state_before_fullscreen = self.windowState()
        self._window_geometry_before_fullscreen = self.saveGeometry()
        self.showFullScreen()

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        previous_state = self._window_state_before_fullscreen
        previous_geometry = self._window_geometry_before_fullscreen
        self.showNormal()
        if previous_geometry is not None:
            self.restoreGeometry(previous_geometry)
        if previous_state is not None:
            self.setWindowState(previous_state)
        self._window_state_before_fullscreen = None
        self._window_geometry_before_fullscreen = None

    def _build_import_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_page_heading(
                "الاستيراد",
                "استورد المقاطع بذكاء من روابط، ملفات، أو نصوص عربية واقعية.",
            ),
            0,
            0,
            1,
            3,
        )
        layout.addWidget(self._build_paste_section(), 1, 1, 1, 2)
        layout.addWidget(self._build_video_source_section(), 1, 0)
        layout.addWidget(self._build_import_summary_section(), 2, 0)
        layout.addWidget(self._build_import_extracted_clips_section(), 2, 1, 1, 2)
        layout.addWidget(self._build_import_apply_section(), 3, 0, 1, 3)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 2)
        layout.setRowStretch(1, 3)
        layout.setRowStretch(2, 2)
        return page

    def _build_clips_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_page_heading("المقاطع", "راجع جدول المقاطع، المعاينة، والإعدادات قبل إرسال العمل إلى قائمة الانتظار."),
            0,
            0,
            1,
            3,
        )
        layout.addWidget(self._build_clips_toolbar_section(), 1, 0, 1, 3)
        layout.addWidget(self._build_selected_clip_details_section(), 2, 0)
        layout.addWidget(self._build_clips_section(), 2, 1, 1, 2)
        layout.addWidget(self._build_padding_section(), 3, 0, 1, 2)
        layout.addWidget(self._build_clip_quick_actions_section(), 3, 2)
        layout.addWidget(self._build_classification_section(), 4, 0, 1, 3)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 2)
        layout.setRowStretch(2, 5)
        layout.setRowStretch(3, 2)
        return page

    def _build_queue_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_page_heading("قائمة الانتظار", "إدارة المقاطع بترتيب التنفيذ ومتابعة حالة كل مهمة بوضوح."),
            0,
            0,
            1,
            3,
        )
        layout.addWidget(self._build_current_job_card(), 1, 0, 1, 2)
        layout.addWidget(self._build_queue_controls_card(), 1, 2)
        layout.addWidget(self._build_queue_table_card(), 2, 0, 1, 3)
        layout.addWidget(self._build_queue_job_log_card(), 3, 0)
        layout.addWidget(self._build_queue_info_preview_card(), 3, 1)
        layout.addWidget(self._build_queue_task_details_card(), 3, 2)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 1)
        layout.setRowStretch(2, 3)
        layout.setRowStretch(3, 2)
        return page

    def _build_logs_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            self._build_page_heading("لوحة التشغيل الرئيسية", "نظرة شاملة على حالة العمل، قائمة الانتظار، وسجل التشغيل."),
            0,
            0,
            1,
            3,
        )
        layout.addWidget(self._build_dashboard_summary_section(), 1, 0, 1, 3)
        layout.addWidget(self._build_operations_log_section(), 2, 0, 2, 2)
        layout.addWidget(self._build_queue_snapshot_section(), 2, 2)
        layout.addWidget(self._build_current_work_section(), 3, 2)
        layout.addWidget(self._build_system_status_section(), 4, 0, 1, 3)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 2)
        layout.setRowStretch(2, 3)
        layout.setRowStretch(3, 1)
        layout.setRowStretch(4, 1)
        return page


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

    def _make_sidebar_icon(self, kind: str) -> QIcon:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        accent_pen = QPen(QColor("#66b3ff"), 2.4)
        accent_pen.setCapStyle(Qt.RoundCap)
        accent_pen.setJoinStyle(Qt.RoundJoin)
        pen = QPen(QColor("#ecf6ff"), 2.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if kind == "import":
            painter.drawRoundedRect(QRectF(10, 24, 20, 6), 3, 3)
            painter.drawLine(20, 8, 20, 21)
            painter.drawLine(13, 15, 20, 22)
            painter.drawLine(27, 15, 20, 22)
            painter.setPen(accent_pen)
            painter.drawLine(12, 30, 28, 30)
        elif kind == "clips":
            painter.drawRoundedRect(QRectF(9, 10, 22, 20), 4, 4)
            for x in (14, 26):
                painter.drawLine(x, 10, x, 30)
            painter.setPen(accent_pen)
            painter.drawLine(9, 16, 31, 16)
            painter.drawLine(9, 24, 31, 24)
        elif kind == "queue":
            for y in (11, 19, 27):
                painter.drawEllipse(QRectF(9, y - 2.2, 4.4, 4.4))
                painter.drawRoundedRect(QRectF(17, y - 2.4, 14, 4.8), 2.4, 2.4)
            painter.setPen(accent_pen)
            painter.drawLine(17, 11, 28, 11)
        elif kind == "logs":
            painter.drawRoundedRect(QRectF(11, 7, 18, 26), 4, 4)
            painter.drawLine(15, 15, 25, 15)
            painter.drawLine(15, 21, 25, 21)
            painter.setPen(accent_pen)
            painter.drawLine(15, 27, 22, 27)

        painter.end()
        return QIcon(pixmap)

    def _apply_visual_polish(self) -> None:
        self.setMinimumSize(980, 640)

        self.smart_paste_button.setObjectName("smartImportButton")
        self.global_smart_import_button.setObjectName("smartImportButton")
        self.start_button.setObjectName("primaryActionButton")
        self.new_work_button.setObjectName("newWorkButton")
        self.validate_button.setObjectName("validateActionButton")
        self.open_output_button.setObjectName("openOutputButton")
        self.queue_advanced_toggle_button.setObjectName("advancedToggleButton")
        self.processing_status_label.setObjectName("processingStatusLabel")
        self.log_header_label.setObjectName("logHeaderLabel")
        self.queue_edit_status_label.setObjectName("queueEditStatusLabel")
        self.queue_selected_job_details_label.setObjectName("queueSummaryLabel")
        self.queue_job_details_label.setObjectName("queueDetailsLabel")
        self.paste_message_input.setObjectName("pasteBox")
        self.log_area.setObjectName("logArea")
        self.queue_job_log_area.setObjectName("logArea")
        self.import_summary_label.setObjectName("queueSummaryLabel")
        self.selected_clip_details_label.setObjectName("queueDetailsLabel")
        self.selected_clip_preview_label.setObjectName("emptyStateLabel")
        self.current_work_label.setObjectName("queueDetailsLabel")
        self.system_status_label.setObjectName("queueDetailsLabel")
        self.queue_current_job_label.setObjectName("queueDetailsLabel")
        self.queue_info_preview_label.setObjectName("queueDetailsLabel")
        self.sidebar_bottom_status_label.setObjectName("sidebarReadyText")
        for button in (
            self.nav_import_button,
            self.nav_clips_button,
            self.nav_queue_button,
            self.nav_logs_button,
        ):
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            button.setIconSize(QSize(20, 20))
        nav_icons = (
            (self.nav_import_button, "import"),
            (self.nav_clips_button, "clips"),
            (self.nav_queue_button, "queue"),
            (self.nav_logs_button, "logs"),
        )
        for button, icon_kind in nav_icons:
            button.setIcon(self._make_sidebar_icon(icon_kind))
        for button in (
            self.future_reports_button,
            self.future_schedule_button,
            self.future_templates_button,
        ):
            button.setObjectName("futureNavButton")
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            button.setIcon(QIcon())

        self.smart_paste_button.setMinimumWidth(118)
        self.global_smart_import_button.setMinimumWidth(118)
        self.start_button.setMinimumWidth(145)
        self.validate_button.setMinimumWidth(120)
        self.new_work_button.setMinimumWidth(94)
        self.open_output_button.setMinimumWidth(118)
        self.processing_status_label.setMinimumWidth(140)
        for button in (
            self.new_work_button,
            self.global_smart_import_button,
            self.validate_button,
            self.start_button,
            self.open_output_button,
        ):
            button.setProperty("topAction", True)
            button.setMinimumHeight(42)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.start_button.setMinimumHeight(44)
        self.start_button.setMinimumWidth(152)

        for table in (
            self.queue_table,
            self.queue_job_clips_table,
            self.clips_table,
            self.classification_rules_table,
            self.import_extracted_clips_table,
            self.operations_log_table,
            self.queue_snapshot_table,
        ):
            self._apply_table_visual_defaults(table)

        self.queue_job_details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.queue_selected_job_details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.import_summary_label.setWordWrap(True)
        self.selected_clip_details_label.setWordWrap(True)
        self.selected_clip_preview_label.setWordWrap(True)
        self.selected_clip_preview_label.setAlignment(Qt.AlignCenter)
        self.current_work_label.setWordWrap(True)
        self.system_status_label.setWordWrap(True)
        self.queue_current_job_label.setWordWrap(True)
        self.queue_info_preview_label.setWordWrap(True)
        self.queue_job_log_area.setReadOnly(True)
        for button in (
            self.queue_stop_all_button,
            self.queue_move_up_button,
            self.queue_move_down_button,
            self.queue_reorder_button,
            self.future_reports_button,
            self.future_schedule_button,
            self.future_templates_button,
        ):
            button.setEnabled(False)
        self.log_area.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setStyleSheet(APP_STYLE_SHEET)

    def _apply_table_visual_defaults(self, table: QTableWidget) -> None:
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setMinimumSectionSize(58)

    def _style_card(self, group: QGroupBox, object_name: str = "dashboardCard") -> QGroupBox:
        group.setObjectName(object_name)
        shadow = QGraphicsDropShadowEffect(group)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 60))
        group.setGraphicsEffect(shadow)
        return group

    def _build_header_section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("appHeader")
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        frame.setMaximumHeight(190)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(5)

        logo = QLabel()
        logo.setObjectName("appLogo")
        logo_path = self._asset_path("logo.png")
        if not logo_path.exists():
            logo_path = self._asset_path("icon.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo.setPixmap(self._sidebar_logo_pixmap(pixmap, QSize(72, 72)))
        logo.setFixedSize(80, 80)
        logo.setAlignment(Qt.AlignCenter)
        logo_halo = QFrame()
        logo_halo.setObjectName("logoHalo")
        logo_halo.setFixedSize(96, 96)
        logo_layout = QVBoxLayout(logo_halo)
        logo_layout.setContentsMargins(8, 8, 8, 8)
        logo_layout.addWidget(logo, alignment=Qt.AlignCenter)

        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(False)
        title.setMinimumHeight(34)
        english_name = QLabel("AlmiqsAlBaseet")
        english_name.setObjectName("appSubtitle")
        english_name.setAlignment(Qt.AlignCenter)
        english_name.setWordWrap(False)
        layout.addWidget(logo_halo, alignment=Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(english_name)

        return frame

    def _sidebar_logo_pixmap(self, source: QPixmap, target_size: QSize) -> QPixmap:
        """Use the existing logo art, cropped and rounded to avoid a pasted-square look."""
        side = min(source.width(), source.height())
        crop_side = int(side * 0.58)
        crop_x = max(0, (source.width() - crop_side) // 2)
        crop_y = max(0, int(side * 0.12))
        if crop_y + crop_side > source.height():
            crop_y = max(0, source.height() - crop_side)
        cropped = source.copy(crop_x, crop_y, crop_side, crop_side)
        scaled = cropped.scaled(target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.width() != target_size.width() or scaled.height() != target_size.height():
            x = max(0, (scaled.width() - target_size.width()) // 2)
            y = max(0, (scaled.height() - target_size.height()) // 2)
            scaled = scaled.copy(x, y, target_size.width(), target_size.height())

        rounded = QPixmap(target_size)
        rounded.fill(Qt.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, target_size.width(), target_size.height()), 18, 18)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return rounded

    def _build_page_heading(self, title_text: str, subtitle_text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pageHeading")
        frame.setMaximumHeight(48)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(1)
        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return frame

    def _build_metric_card(self, title: str, value_label: QLabel, caption: str = "") -> QGroupBox:
        group = QGroupBox(title)
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setWordWrap(True)
        layout.addWidget(value_label)
        if caption:
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricCaption")
            caption_label.setAlignment(Qt.AlignCenter)
            caption_label.setWordWrap(True)
            layout.addWidget(caption_label)
        return group

    def _build_import_summary_section(self) -> QGroupBox:
        group = QGroupBox("ملخص الاستيراد")
        self._style_card(group, "importSummaryCard")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        self.import_summary_label.setWordWrap(True)
        layout.addWidget(self.import_summary_label)
        layout.addStretch(1)
        return group

    def _build_import_extracted_clips_section(self) -> QGroupBox:
        group = QGroupBox("المقاطع المستخرجة")
        self._style_card(group, "clipsCard")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        self.import_extracted_clips_table.setHorizontalHeaderLabels(
            ["", "#", "العنوان", "البداية", "النهاية", "الاستثناءات", "الحالة"]
        )
        self.import_extracted_clips_table.verticalHeader().setVisible(False)
        self.import_extracted_clips_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.import_extracted_clips_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.import_extracted_clips_table.setMinimumHeight(190)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.import_extracted_clips_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.import_empty_label = QLabel("لا توجد مقاطع بعد\nقم بلصق النص أو استيراد ملف أو إدخال رابط لبدء التحليل.")
        self.import_empty_label.setObjectName("emptyStateLabel")
        self.import_empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.import_extracted_clips_table)
        layout.addWidget(self.import_empty_label)
        return group

    def _build_import_apply_section(self) -> QGroupBox:
        group = QGroupBox("تطبيق النتائج")
        self._style_card(group, "mainActionsCard")
        group.setMaximumHeight(58)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)
        layout.addWidget(self.queue_import_button, stretch=1)
        layout.addWidget(self.append_import_button, stretch=1)
        layout.addWidget(self.replace_import_button, stretch=1)
        return group

    def _build_video_source_section(self) -> QGroupBox:
        group = QGroupBox("مصدر الاستيراد")
        self._style_card(group, "importSideCard")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)

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

        source_tabs = QHBoxLayout()
        source_tabs.setSpacing(8)
        source_tabs.addWidget(self.local_file_radio)
        source_tabs.addWidget(self.youtube_radio)
        layout.addLayout(source_tabs)

        youtube_label = QLabel("رابط يوتيوب")
        youtube_label.setObjectName("sectionHelpText")
        layout.addWidget(youtube_label)
        youtube_row = QHBoxLayout()
        youtube_row.setSpacing(8)
        youtube_row.addWidget(self.youtube_input, stretch=1)
        layout.addLayout(youtube_row)

        local_label = QLabel("ملف فيديو من الجهاز")
        local_label.setObjectName("sectionHelpText")
        layout.addWidget(local_label)
        local_row = QHBoxLayout()
        local_row.setSpacing(8)
        local_row.addWidget(self.local_file_input, stretch=1)
        local_row.addWidget(self.browse_button)
        layout.addLayout(local_row)

        project_label = QLabel("اسم المشروع")
        project_label.setObjectName("sectionHelpText")
        self.project_name_input.setPlaceholderText("مثال: درس الجبر - الوحدة الأولى")
        layout.addWidget(project_label)
        layout.addWidget(self.project_name_input)

        browser_row = QHBoxLayout()
        browser_row.setSpacing(8)
        browser_row.addWidget(QLabel("المتصفح"))
        browser_row.addWidget(self.browser_combo, stretch=1)
        layout.addLayout(browser_row)
        layout.addWidget(self.use_browser_cookies_checkbox)
        layout.addWidget(self.source_status_label)
        layout.addWidget(self.browser_cookies_help_label)
        layout.addStretch(1)

        return group

    def _build_project_section(self) -> QGroupBox:
        group = QGroupBox("اسم المشروع")
        self._style_card(group, "importSideCard")
        layout = QGridLayout(group)

        self.project_name_input.setPlaceholderText("مثال: درس الجبر - الوحدة الأولى")

        layout.addWidget(QLabel("اسم المشروع"), 0, 0)
        layout.addWidget(self.project_name_input, 0, 1)
        layout.setColumnStretch(1, 1)

        return group

    def _build_queue_section(self) -> QGroupBox:
        group = QGroupBox("قائمة الانتظار")
        self._style_card(group, "queueCard")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

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
        self.queue_job_details_label.setWordWrap(True)
        self.queue_job_clips_table.setHorizontalHeaderLabels(["الرقم", "العنوان", "البداية", "النهاية", "الاستثناءات"])
        self.queue_job_clips_table.verticalHeader().setVisible(False)
        self.queue_job_clips_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_job_clips_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.queue_job_clips_table.setAlternatingRowColors(True)
        self.queue_job_clips_table.setMinimumHeight(100)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(NUMBER_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(TITLE_COLUMN, QHeaderView.Stretch)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(START_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(END_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(EXCLUSIONS_COLUMN, QHeaderView.Stretch)

        details_group = QGroupBox("تفاصيل المهمة المحددة")
        details_group.setObjectName("jobDetailsCard")
        details_layout = QVBoxLayout(details_group)
        details_layout.setSpacing(10)
        details_layout.addWidget(self.queue_job_details_label)
        details_layout.addWidget(QLabel("مقاطع المهمة"))
        details_layout.addWidget(self.queue_job_clips_table)
        details_button_row = QHBoxLayout()
        details_button_row.addWidget(self.copy_queue_job_details_button)
        details_button_row.addStretch(1)
        details_layout.addLayout(details_button_row)

        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(self.load_queue_job_workspace_button)
        edit_buttons.addWidget(self.save_queue_job_edits_button)
        edit_buttons.addWidget(self.cancel_queue_job_edit_button)
        edit_buttons.addStretch(1)

        self.queue_advanced_toggle_button.setCheckable(True)
        self.queue_advanced_toggle_button.setChecked(False)
        advanced_group_layout = QVBoxLayout(self.queue_advanced_group)
        advanced_group_layout.setSpacing(10)
        advanced_controls_layout = QGridLayout(self.queue_advanced_controls_widget)
        advanced_controls_layout.setHorizontalSpacing(8)
        advanced_controls_layout.setVerticalSpacing(8)
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
        layout.addWidget(details_group)
        layout.addLayout(edit_buttons)
        layout.addWidget(self.queue_advanced_toggle_button)
        layout.addWidget(self.queue_advanced_group)

        return group

    def _build_help_section(self) -> QGroupBox:
        group = QGroupBox("تعليمات سريعة")
        self._style_card(group)
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
        help_text.setObjectName("sectionHelpText")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        return group

    def _build_classification_section(self) -> QGroupBox:
        group = QGroupBox("إعدادات التصنيف والمجلدات")
        self._style_card(group)
        layout = QVBoxLayout(group)

        self.classification_rules_table.setHorizontalHeaderLabels(
            ["اسم التصنيف", "من دقيقة", "إلى دقيقة", "اسم المجلد"]
        )
        self.classification_rules_table.verticalHeader().setVisible(False)
        self.classification_rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.classification_rules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.classification_rules_table.setAlternatingRowColors(True)
        self.classification_rules_table.setMinimumHeight(90)
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
        group = QGroupBox("الاستيراد الذكي")
        self._style_card(group, "smartImportCard")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(12)

        helper = QLabel("الصق نص المقاطع هنا لتحليلها تلقائيًا. يدعم الصيغ الشائعة مثل: [بداية:نهاية] العنوان")
        helper.setObjectName("sectionHelpText")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        self.paste_message_input.setPlaceholderText("الصق نص المقاطع هنا ...")
        self.paste_message_input.setMinimumHeight(260)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.clear_paste_text_button, stretch=1)
        button_row.addWidget(self.import_excel_button, stretch=2)
        button_row.addWidget(self.smart_paste_button, stretch=2)

        layout.addWidget(self.paste_message_input)
        layout.addLayout(button_row)

        return group

    def _build_padding_section(self) -> QGroupBox:
        group = QGroupBox("إعدادات المقطع")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self._configure_padding_input(self.pre_padding_input)
        self._configure_padding_input(self.post_padding_input)
        self._configure_video_speed_input(self.video_speed_input)
        self._configure_volume_input(self.volume_input)
        self._configure_fade_duration_input(self.fade_in_duration_combo)
        self._configure_fade_duration_input(self.fade_out_duration_combo)
        self._configure_black_flash_duration_input(self.black_flash_duration_combo)
        self._configure_export_quality_preset_input(self.export_quality_preset_combo)
        self._configure_resolution_limit_input(self.resolution_limit_combo)

        basic_group = QGroupBox("إعدادات القص الأساسية")
        basic_group.setObjectName("nestedSettingsGroup")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setHorizontalSpacing(12)
        basic_layout.setVerticalSpacing(8)
        basic_layout.addWidget(QLabel("وقت قبل بداية المقطع"), 0, 0)
        basic_layout.addWidget(self.pre_padding_input, 0, 1)
        basic_layout.addWidget(QLabel("وقت بعد نهاية المقطع"), 1, 0)
        basic_layout.addWidget(self.post_padding_input, 1, 1)
        basic_layout.setColumnStretch(1, 1)

        optional_group = QGroupBox("تعديلات اختيارية")
        optional_group.setObjectName("nestedSettingsGroup")
        optional_layout = QGridLayout(optional_group)
        optional_layout.setHorizontalSpacing(12)
        optional_layout.setVerticalSpacing(8)
        optional_layout.addWidget(self.video_speed_enabled_checkbox, 0, 0)
        optional_layout.addWidget(QLabel("سرعة الفيديو"), 0, 1)
        optional_layout.addWidget(self.video_speed_input, 0, 2)
        optional_layout.addWidget(self.reset_video_speed_button, 0, 3)
        optional_layout.addWidget(self.video_speed_status_label, 1, 0, 1, 4)
        optional_layout.addWidget(self.volume_enabled_checkbox, 2, 0)
        optional_layout.addWidget(QLabel("مستوى الصوت"), 2, 1)
        optional_layout.addWidget(self.volume_input, 2, 2)
        optional_layout.addWidget(self.reset_volume_button, 2, 3)
        optional_layout.addWidget(self.volume_status_label, 3, 0, 1, 4)
        optional_layout.setColumnStretch(2, 1)

        visual_group = QGroupBox("المؤثرات البصرية الاختيارية")
        visual_group.setObjectName("nestedSettingsGroup")
        visual_layout = QGridLayout(visual_group)
        visual_layout.setHorizontalSpacing(12)
        visual_layout.setVerticalSpacing(8)
        visual_layout.addWidget(self.black_fade_enabled_checkbox, 0, 0, 1, 4)
        visual_layout.addWidget(QLabel("مدة التدرج في البداية"), 1, 0)
        visual_layout.addWidget(self.fade_in_duration_combo, 1, 1)
        visual_layout.addWidget(QLabel("مدة التدرج في النهاية"), 2, 0)
        visual_layout.addWidget(self.fade_out_duration_combo, 2, 1)
        visual_layout.addWidget(self.black_fade_status_label, 1, 2, 2, 2)
        visual_layout.addWidget(self.black_flash_enabled_checkbox, 3, 0, 1, 4)
        visual_layout.addWidget(QLabel("مدة الوميض الأسود"), 4, 0)
        visual_layout.addWidget(self.black_flash_duration_combo, 4, 1)
        visual_layout.addWidget(self.black_flash_status_label, 4, 2, 1, 2)
        visual_layout.setColumnStretch(3, 1)

        export_group = QGroupBox("جودة التصدير")
        export_group.setObjectName("nestedSettingsGroup")
        export_layout = QGridLayout(export_group)
        export_layout.setHorizontalSpacing(12)
        export_layout.setVerticalSpacing(8)
        export_layout.addWidget(self.export_quality_enabled_checkbox, 0, 0, 1, 3)
        export_layout.addWidget(QLabel("إعداد الجودة"), 1, 0)
        export_layout.addWidget(self.export_quality_preset_combo, 1, 1)
        export_layout.addWidget(QLabel("حد الدقة"), 2, 0)
        export_layout.addWidget(self.resolution_limit_combo, 2, 1)
        export_layout.addWidget(self.export_quality_status_label, 1, 2, 2, 1)
        export_layout.setColumnStretch(2, 1)

        helper_label = QLabel("الإعدادات الاختيارية لا تؤثر على التصدير إلا عند تفعيلها.")
        helper_label.setObjectName("statusHelperLabel")
        helper_label.setWordWrap(True)

        layout.addWidget(basic_group)
        layout.addWidget(optional_group)
        layout.addWidget(visual_group)
        layout.addWidget(export_group)
        layout.addWidget(helper_label)
        self.video_speed_status_label.setWordWrap(True)
        self.volume_status_label.setWordWrap(True)
        self.black_fade_status_label.setWordWrap(True)
        self.black_flash_status_label.setWordWrap(True)
        self.export_quality_status_label.setWordWrap(True)

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

    def _configure_fade_duration_input(self, widget: QComboBox) -> None:
        if widget.count() == 0:
            for duration in (0.25, 0.50, 1.00, 1.50, 2.00):
                widget.addItem(f"{duration:.2f} ثانية", duration)
        self._set_fade_duration_value(widget, DEFAULT_FADE_IN_SECONDS)
        widget.setToolTip("الافتراضي عند التفعيل: 0.50 ثانية")

    def _configure_black_flash_duration_input(self, widget: QComboBox) -> None:
        if widget.count() == 0:
            for duration in (0.10, 0.20, 0.30, 0.50):
                widget.addItem(f"{duration:.2f} ثانية", duration)
        self._set_black_flash_duration_value(widget, DEFAULT_BLACK_FLASH_SECONDS)
        widget.setToolTip("الافتراضي عند التفعيل: 0.20 ثانية")

    def _configure_export_quality_preset_input(self, widget: QComboBox) -> None:
        if widget.count() == 0:
            for value in ("high", "balanced", "small"):
                widget.addItem(QUALITY_PRESET_LABELS_AR[value], value)
        self._set_export_quality_preset_value(DEFAULT_ENABLED_QUALITY_PRESET)
        widget.setToolTip("الافتراضي عند التفعيل: متوازن")

    def _configure_resolution_limit_input(self, widget: QComboBox) -> None:
        if widget.count() == 0:
            for value in ("original", "1080p", "720p"):
                widget.addItem(RESOLUTION_LIMIT_LABELS_AR[value], value)
        self._set_resolution_limit_value(DEFAULT_RESOLUTION_LIMIT)
        widget.setToolTip("الافتراضي: الأصلية")

    def reset_video_speed(self) -> None:
        self.video_speed_input.setValue(DEFAULT_VIDEO_SPEED)
        self._update_speed_volume_controls()

    def reset_volume(self) -> None:
        self.volume_input.setValue(DEFAULT_VOLUME_PERCENT)
        self._update_speed_volume_controls()

    def _fade_duration_value(self, widget: QComboBox) -> float:
        data = widget.currentData()
        try:
            return normalize_fade_duration(data)
        except Exception:
            return DEFAULT_FADE_IN_SECONDS

    def _set_fade_duration_value(self, widget: QComboBox, value: float) -> None:
        try:
            normalized = normalize_fade_duration(value)
        except Exception:
            normalized = DEFAULT_FADE_IN_SECONDS
        for index in range(widget.count()):
            if abs(float(widget.itemData(index)) - normalized) < 1e-9:
                widget.setCurrentIndex(index)
                return

    def _black_flash_duration_value(self) -> float:
        data = self.black_flash_duration_combo.currentData()
        try:
            return normalize_black_flash_duration(data)
        except Exception:
            return DEFAULT_BLACK_FLASH_SECONDS

    def _set_black_flash_duration_value(self, widget: QComboBox, value: float) -> None:
        try:
            normalized = normalize_black_flash_duration(value)
        except Exception:
            normalized = DEFAULT_BLACK_FLASH_SECONDS
        for index in range(widget.count()):
            if abs(float(widget.itemData(index)) - normalized) < 1e-9:
                widget.setCurrentIndex(index)
                return

    def _export_quality_preset_value(self) -> str:
        try:
            return normalize_quality_preset(self.export_quality_preset_combo.currentData())
        except ExportQualityError:
            return DEFAULT_ENABLED_QUALITY_PRESET

    def _set_export_quality_preset_value(self, value: str) -> None:
        try:
            normalized = normalize_quality_preset(value)
        except ExportQualityError:
            normalized = DEFAULT_ENABLED_QUALITY_PRESET
        for index in range(self.export_quality_preset_combo.count()):
            if self.export_quality_preset_combo.itemData(index) == normalized:
                self.export_quality_preset_combo.setCurrentIndex(index)
                return

    def _resolution_limit_value(self) -> str:
        try:
            return normalize_resolution_limit(self.resolution_limit_combo.currentData())
        except ExportQualityError:
            return DEFAULT_RESOLUTION_LIMIT

    def _set_resolution_limit_value(self, value: str) -> None:
        try:
            normalized = normalize_resolution_limit(value)
        except ExportQualityError:
            normalized = DEFAULT_RESOLUTION_LIMIT
        for index in range(self.resolution_limit_combo.count()):
            if self.resolution_limit_combo.itemData(index) == normalized:
                self.resolution_limit_combo.setCurrentIndex(index)
                return

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

        fade_enabled = self.black_fade_enabled_checkbox.isChecked()
        self.fade_in_duration_combo.setEnabled(fade_enabled)
        self.fade_out_duration_combo.setEnabled(fade_enabled)
        self.black_fade_status_label.setText(
            "بداية ونهاية سوداء تدريجية" if fade_enabled else "الإعدادات الافتراضية آمنة"
        )

        black_flash_enabled = self.black_flash_enabled_checkbox.isChecked()
        self.black_flash_duration_combo.setEnabled(black_flash_enabled)
        self.black_flash_status_label.setText(
            "وميض أسود عند الاستثناء" if black_flash_enabled else "الإعدادات الافتراضية آمنة"
        )

        export_quality_enabled = self.export_quality_enabled_checkbox.isChecked()
        self.export_quality_preset_combo.setEnabled(export_quality_enabled)
        self.resolution_limit_combo.setEnabled(export_quality_enabled)
        if export_quality_enabled:
            self.export_quality_status_label.setText(
                f"جودة التصدير: {quality_preset_label_ar(self._export_quality_preset_value())}"
            )
        else:
            self.export_quality_status_label.setText("الإعدادات الافتراضية آمنة")

    def _build_clips_toolbar_section(self) -> QGroupBox:
        group = QGroupBox("أدوات المقاطع")
        self._style_card(group, "mainActionsCard")
        group.setMaximumHeight(56)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        layout.addWidget(self.clips_import_shortcut_button)
        layout.addWidget(self.clips_new_work_shortcut_button)
        layout.addWidget(self.clips_clear_shortcut_button)
        layout.addWidget(self.clips_delete_shortcut_button)
        layout.addWidget(self.clips_point_shortcut_button)
        layout.addWidget(self.clips_export_shortcut_button)
        layout.addStretch(1)
        return group

    def _build_clips_section(self) -> QGroupBox:
        group = QGroupBox("قائمة المقاطع")
        self._style_card(group, "clipsCard")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self.clips_table.setHorizontalHeaderLabels(["الرقم", "العنوان", "البداية", "النهاية", "استثناءات"])
        self.clips_table.verticalHeader().setVisible(False)
        self.clips_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clips_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.clips_table.setAlternatingRowColors(True)
        self.clips_table.setMinimumHeight(280)
        self.clips_table.horizontalHeader().setSectionResizeMode(NUMBER_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(TITLE_COLUMN, QHeaderView.Stretch)
        self.clips_table.horizontalHeader().setSectionResizeMode(START_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(END_COLUMN, QHeaderView.ResizeToContents)
        self.clips_table.horizontalHeader().setSectionResizeMode(EXCLUSIONS_COLUMN, QHeaderView.Stretch)

        table_buttons = QHBoxLayout()
        table_buttons.addWidget(self.add_row_button)
        table_buttons.addWidget(self.clear_table_button)
        table_buttons.addStretch(1)

        layout.addWidget(self.clips_table)
        layout.addLayout(table_buttons)

        return group

    def _build_selected_clip_details_section(self) -> QGroupBox:
        group = QGroupBox("معاينة المقطع المحدد")
        self._style_card(group)
        layout = QVBoxLayout(group)
        self.selected_clip_preview_label.setAlignment(Qt.AlignCenter)
        self.selected_clip_preview_label.setMinimumHeight(120)
        layout.addWidget(self.selected_clip_preview_label)
        details_title = QLabel("تفاصيل المقطع المحدد")
        details_title.setObjectName("sectionHelpText")
        layout.addWidget(details_title)
        layout.addWidget(self.selected_clip_details_label)
        return group

    def _build_clip_quick_actions_section(self) -> QGroupBox:
        group = QGroupBox("إجراءات سريعة")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.addWidget(self.preview_selected_clip_button)
        layout.addWidget(self.preview_clip_start_button)
        layout.addWidget(self.preview_clip_end_button)
        layout.addWidget(self.delete_row_button)
        duplicate_button = QPushButton("تكرار المقطع — قريبًا")
        duplicate_button.setEnabled(False)
        move_button = QPushButton("نقل إلى قائمة الانتظار — قريبًا")
        move_button.setEnabled(False)
        layout.addWidget(duplicate_button)
        layout.addWidget(move_button)
        layout.addStretch(1)
        return group

    def _build_queue_controls_card(self) -> QGroupBox:
        group = QGroupBox("التحكم في القائمة")
        self._style_card(group, "queueControlCard")
        layout = QGridLayout(group)
        buttons = [
            self.start_queue_processing_button,
            self.stop_queue_after_current_button,
            self.queue_stop_all_button,
            self.queue_move_up_button,
            self.queue_move_down_button,
            self.queue_reorder_button,
            self.load_queue_clips_button,
            self.delete_queue_job_button,
        ]
        for index, button in enumerate(buttons):
            layout.addWidget(button, index // 2, index % 2)
        return group

    def _build_current_job_card(self) -> QGroupBox:
        group = QGroupBox("الوظيفة قيد المعالجة الآن")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.addWidget(self.queue_current_job_label)
        return group

    def _build_queue_table_card(self) -> QGroupBox:
        group = QGroupBox("قائمة الانتظار")
        self._style_card(group, "queueCard")
        layout = QVBoxLayout(group)
        self.queue_table.setHorizontalHeaderLabels(
            ["المصدر", "العنوان", "عدد المقاطع", "الحالة", "أولوية عالية", "الإخراج / الملاحظات"]
        )
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setMinimumHeight(190)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_SOURCE_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_TITLE_COLUMN, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_CLIP_COUNT_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_STATUS_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_HIGH_PRIORITY_COLUMN, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(QUEUE_ACTION_COLUMN, QHeaderView.Stretch)
        layout.addWidget(self.queue_table)

        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(self.load_queue_job_workspace_button)
        edit_buttons.addWidget(self.save_queue_job_edits_button)
        edit_buttons.addWidget(self.cancel_queue_job_edit_button)
        edit_buttons.addStretch(1)
        edit_buttons.addWidget(self.queue_advanced_toggle_button)
        layout.addLayout(edit_buttons)

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
            self.save_queue_state_button,
            self.load_queue_state_button,
            self.clear_queue_button,
            self.readiness_button,
            self.direct_cut_button,
        ]
        for index, button in enumerate(advanced_buttons):
            advanced_controls_layout.addWidget(button, index // 4, index % 4)
        advanced_group_layout.addWidget(self.queue_advanced_controls_widget)
        self.queue_advanced_controls_widget.setVisible(False)
        self.queue_advanced_toggle_button.toggled.connect(self.queue_advanced_controls_widget.setVisible)
        layout.addWidget(self.queue_advanced_group)
        return group

    def _build_queue_task_details_card(self) -> QGroupBox:
        group = QGroupBox("تفاصيل الوظيفة المحددة")
        self._style_card(group, "jobDetailsCard")
        layout = QVBoxLayout(group)
        layout.addWidget(self.queue_selected_job_details_label)
        layout.addWidget(self.queue_edit_status_label)
        layout.addWidget(self.queue_job_details_label)
        layout.addWidget(QLabel("مقاطع المهمة"))
        self.queue_job_clips_table.setHorizontalHeaderLabels(["الرقم", "العنوان", "البداية", "النهاية", "الاستثناءات"])
        self.queue_job_clips_table.verticalHeader().setVisible(False)
        self.queue_job_clips_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_job_clips_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.queue_job_clips_table.setAlternatingRowColors(True)
        self.queue_job_clips_table.setMinimumHeight(120)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(NUMBER_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(TITLE_COLUMN, QHeaderView.Stretch)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(START_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(END_COLUMN, QHeaderView.ResizeToContents)
        self.queue_job_clips_table.horizontalHeader().setSectionResizeMode(EXCLUSIONS_COLUMN, QHeaderView.Stretch)
        layout.addWidget(self.queue_job_clips_table)
        details_button_row = QHBoxLayout()
        details_button_row.addWidget(self.copy_queue_job_details_button)
        details_button_row.addStretch(1)
        layout.addLayout(details_button_row)
        return group

    def _build_queue_info_preview_card(self) -> QGroupBox:
        group = QGroupBox("معاينة المعلومات")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.addWidget(self.queue_info_preview_label)
        return group

    def _build_queue_job_log_card(self) -> QGroupBox:
        group = QGroupBox("سجل الوظيفة المحددة")
        self._style_card(group)
        layout = QVBoxLayout(group)
        filter_row = QHBoxLayout()
        for label in ("الكل", "تحذيرات", "معلومات", "أخطاء"):
            button = QPushButton(label)
            button.setEnabled(label == "الكل")
            filter_row.addWidget(button)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)
        self.queue_job_log_area.setMinimumHeight(140)
        layout.addWidget(self.queue_job_log_area)
        button_row = QHBoxLayout()
        copy_button = QPushButton("نسخ السجل — قريبًا")
        copy_button.setEnabled(False)
        button_row.addWidget(copy_button)
        save_button = QPushButton("حفظ السجل — قريبًا")
        save_button.setEnabled(False)
        button_row.addWidget(save_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return group

    def _build_dashboard_summary_section(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        cards = [
            self._build_metric_card("مصدر الفيديو", self.dashboard_source_label, "مصدر العمل الحالي"),
            self._build_metric_card("المقاطع", self.dashboard_clips_label, "إجمالي المقاطع في الجدول"),
            self._build_metric_card("قائمة الانتظار", self.dashboard_queue_label, "المهام الحالية"),
            self._build_metric_card("الحالة الحالية", self.dashboard_status_label, "حالة التشغيل"),
            self._build_metric_card("مسار الإخراج", self.dashboard_output_label, "المجلد المستخدم فعليًا"),
        ]
        for index, card in enumerate(cards):
            layout.addWidget(card, 0, index)
        return widget

    def _build_operations_log_section(self) -> QGroupBox:
        group = QGroupBox("سجل العمليات")
        self._style_card(group, "clipsCard")
        layout = QVBoxLayout(group)
        filters = QHBoxLayout()
        filters.addWidget(QPushButton("آخر 7 أيام"))
        filters.addWidget(QPushButton("كل الحالات"))
        search = QLineEdit()
        search.setPlaceholderText("بحث في السجل...")
        filters.addWidget(search, stretch=1)
        layout.addLayout(filters)
        self.operations_log_table.setHorizontalHeaderLabels(["العمل", "التفاصيل", "الحدث", "الوقت", "الحالة"])
        self.operations_log_table.verticalHeader().setVisible(False)
        self.operations_log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.operations_log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.operations_log_table.setMinimumHeight(140)
        self.operations_log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.operations_log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.operations_log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.operations_log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.operations_log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.operations_log_table)
        layout.addWidget(self._build_log_section())
        return group

    def _build_queue_snapshot_section(self) -> QGroupBox:
        group = QGroupBox("لقطة سريعة لقائمة الانتظار")
        self._style_card(group)
        layout = QVBoxLayout(group)
        self.queue_snapshot_table.setHorizontalHeaderLabels(["#", "العنوان", "الحالة", "التقدم"])
        self.queue_snapshot_table.verticalHeader().setVisible(False)
        self.queue_snapshot_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue_snapshot_table.setMinimumHeight(120)
        self.queue_snapshot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.queue_snapshot_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_snapshot_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.queue_snapshot_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.queue_snapshot_table)
        return group

    def _build_current_work_section(self) -> QGroupBox:
        group = QGroupBox("العمل المحدد حاليًا")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.addWidget(self.current_work_label)
        open_button = QPushButton("فتح المجلد")
        open_button.clicked.connect(self.open_output_folder)
        layout.addWidget(open_button)
        return group

    def _build_system_status_section(self) -> QGroupBox:
        group = QGroupBox("حالة النظام")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.addWidget(self.system_status_label)
        return group

    def _build_action_section(self) -> QGroupBox:
        group = QGroupBox("أزرار التشغيل")
        self._style_card(group, "mainActionsCard")
        group.setProperty("topActions", True)
        group.setMinimumHeight(96)
        group.setMaximumHeight(96)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        layout.addWidget(self.new_work_button)
        layout.addWidget(self.global_smart_import_button)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.start_button)
        layout.addWidget(self.open_output_button)
        layout.addStretch(1)
        layout.addWidget(self.processing_status_label)
        self.add_and_run_queue_job_button.setVisible(False)

        return group

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("سجل الحالة")
        self._style_card(group)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("ستظهر رسائل الفحص والتقدم هنا.")
        header_row = QHBoxLayout()
        header_row.addWidget(self.log_header_label)
        header_row.addStretch(1)
        header_row.addWidget(self.show_global_log_button)
        layout.addLayout(header_row)
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
        self.black_fade_enabled_checkbox.toggled.connect(self._update_speed_volume_controls)
        self.fade_in_duration_combo.currentIndexChanged.connect(self._update_speed_volume_controls)
        self.fade_out_duration_combo.currentIndexChanged.connect(self._update_speed_volume_controls)
        self.black_flash_enabled_checkbox.toggled.connect(self._update_speed_volume_controls)
        self.black_flash_duration_combo.currentIndexChanged.connect(self._update_speed_volume_controls)
        self.export_quality_enabled_checkbox.toggled.connect(self._update_speed_volume_controls)
        self.export_quality_preset_combo.currentIndexChanged.connect(self._update_speed_volume_controls)
        self.resolution_limit_combo.currentIndexChanged.connect(self._update_speed_volume_controls)
        self.nav_import_button.clicked.connect(lambda: self.switch_dashboard_page("import"))
        self.nav_clips_button.clicked.connect(lambda: self.switch_dashboard_page("clips"))
        self.nav_queue_button.clicked.connect(lambda: self.switch_dashboard_page("queue"))
        self.nav_logs_button.clicked.connect(lambda: self.switch_dashboard_page("logs"))
        self.global_smart_import_button.clicked.connect(lambda: self.switch_dashboard_page("import"))
        self.clear_paste_text_button.clicked.connect(self.paste_message_input.clear)
        self.replace_import_button.clicked.connect(self.import_smart_paste_message)
        self.append_import_button.clicked.connect(self.import_smart_paste_message)
        self.queue_import_button.clicked.connect(self.import_smart_paste_message)
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
        self.queue_table.itemSelectionChanged.connect(self._handle_queue_selection_changed)
        self.queue_table.currentCellChanged.connect(self._handle_queue_selection_changed)
        self.clips_table.itemChanged.connect(self._refresh_dashboard_overview)
        self.clips_table.itemSelectionChanged.connect(self._refresh_dashboard_overview)
        self.smart_paste_button.clicked.connect(self.import_smart_paste_message)
        self.clips_import_shortcut_button.clicked.connect(lambda: self.switch_dashboard_page("import"))
        self.clips_new_work_shortcut_button.clicked.connect(self.start_new_work)
        self.clips_clear_shortcut_button.clicked.connect(self.clear_table)
        self.clips_delete_shortcut_button.clicked.connect(self.delete_selected_row)
        self.clips_point_shortcut_button.clicked.connect(self.preview_selected_clip)
        self.clips_export_shortcut_button.clicked.connect(self.add_current_work_and_start_queue)
        self.parse_message_button.clicked.connect(self.convert_pasted_text_to_table)
        self.show_global_log_button.clicked.connect(self.show_global_log)
        self.copy_queue_job_details_button.clicked.connect(self.copy_selected_queue_job_details)
        self.new_work_button.clicked.connect(self.start_new_work)
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
        self._refresh_dashboard_overview()

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
        job.add_log(AR_QUEUE_JOB_ADDED)
        if job.source_type == QueueVideoSourceType.YOUTUBE:
            job.add_log("تم إضافة رابط يوتيوب إلى قائمة الانتظار")
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
            self._apply_queue_row_visual_state(row, job)
        finally:
            self.queue_table.blockSignals(False)
        self._update_queue_edit_controls()
        self._refresh_dashboard_overview()

    def _readonly_table_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _apply_queue_row_visual_state(self, row: int, job: VideoJob) -> None:
        status_item = self.queue_table.item(row, QUEUE_STATUS_COLUMN)
        if status_item is not None:
            background, foreground = QUEUE_STATUS_COLORS.get(job.status, QUEUE_STATUS_COLORS[JobStatus.DRAFT])
            status_item.setBackground(QBrush(QColor(background)))
            status_item.setForeground(QBrush(QColor(foreground)))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setToolTip(self._queue_status_label(job.status))

        action_item = self.queue_table.item(row, QUEUE_ACTION_COLUMN)
        if action_item is not None:
            if job.status == JobStatus.FAILED:
                action_item.setBackground(QBrush(QColor("#3a2428")))
                action_item.setForeground(QBrush(QColor("#ffd1d1")))
            else:
                action_item.setBackground(QBrush())
                action_item.setForeground(QBrush())

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
        if job.status == JobStatus.FAILED and job.failure_message:
            return f"سبب الفشل: {self._short_queue_text(job.failure_message)}"

        speed_state = "مفعّلة" if job.settings.speed_adjustment_enabled else "غير مفعّلة"
        speed_value = job.settings.speed if job.settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED
        volume_state = "مفعّل" if job.settings.volume_adjustment_enabled else "غير مفعّل"
        volume_value = job.settings.volume_percent if job.settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT
        fade_state = "مفعّلة" if job.settings.fade_enabled else "غير مفعّلة"
        black_flash_state = "مفعّل" if job.settings.black_flash_enabled else "غير مفعّل"
        quality_state = "مفعّلة" if job.settings.export_quality_enabled else "غير مفعّلة"
        return (
            f"السرعة: {speed_state} ({speed_value:.2f}x) | "
            f"الصوت: {volume_state} ({volume_value}%) | "
            f"التدرج: {fade_state} | "
            f"الوميض: {black_flash_state} | "
            f"الجودة: {quality_state}"
        )

    def _short_queue_text(self, text: str, limit: int = 90) -> str:
        clean_text = " ".join(str(text).split())
        if len(clean_text) <= limit:
            return clean_text
        return f"{clean_text[: limit - 1]}…"

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

    def _handle_queue_selection_changed(self, *_args) -> None:
        self._update_queue_edit_controls()
        self._update_selected_queue_job_details()
        self._show_selected_queue_job_log()

    def _selected_queue_job(self) -> VideoJob | None:
        row = self._selected_queue_row()
        if row is None or not 0 <= row < len(self.job_queue):
            return None
        return self.job_queue[row]

    def _refresh_dashboard_overview(self, *_args) -> None:
        if not hasattr(self, "dashboard_source_label"):
            return

        output_path = self._dashboard_output_path()
        short_output_path = self._short_path_text(output_path, limit=62)
        status_text = self.processing_status_label.text().replace("الحالة:", "").strip() or "جاهز"
        source_summary = self._current_source_summary(short=True)
        clip_count = self.clips_table.rowCount()
        queue_count = len(self.job_queue)

        self.dashboard_source_label.setText(source_summary)
        self.dashboard_clips_label.setText(str(clip_count))
        self.dashboard_queue_label.setText(str(queue_count))
        self.dashboard_status_label.setText(status_text)
        self.dashboard_output_label.setText(short_output_path)
        self.dashboard_output_label.setToolTip(str(output_path))
        self.bottom_status_label.setText(status_text)
        self.bottom_output_label.setText(f"مجلد النتائج: {self._short_path_text(output_path, limit=82)}")
        self.bottom_output_label.setToolTip(str(output_path))
        last_job_summary = "لا توجد"
        if self.job_queue:
            last_job = self.job_queue[-1]
            last_job_summary = self._queue_status_label(last_job.status)
        self.sidebar_engine_status_label.setText(status_text or "جاهز")
        self.sidebar_smart_status_label.setText("جاهز")
        self.sidebar_last_job_label.setText(last_job_summary)
        self.sidebar_queue_count_label.setText(str(queue_count))
        self.sidebar_bottom_status_label.setText(status_text)

        project_title = self.project_name_input.text().strip() or "عمل بلا عنوان"
        self.current_work_label.setText(
            "\n".join(
                [
                    f"العنوان: {project_title}",
                    f"المصدر: {self._current_source_summary(short=False)}",
                    f"عدد المقاطع: {clip_count}",
                    f"مجلد النتائج: {output_path}",
                ]
            )
        )

        running_job = self._current_running_queue_job()
        if running_job is None:
            self.queue_current_job_label.setText("لا توجد وظيفة قيد المعالجة الآن")
        else:
            self.queue_current_job_label.setText(
                "\n".join(
                    [
                        f"العنوان: {running_job.title}",
                        f"الحالة: {self._queue_status_label(running_job.status)}",
                        f"المصدر: {self._queue_source_label(running_job)}",
                        f"عدد المقاطع: {running_job.clip_count}",
                        f"أولوية عالية: {'نعم' if running_job.settings.high_priority else 'لا'}",
                    ]
                )
            )

        selected_job = self._selected_queue_job()
        if selected_job is None:
            self.queue_info_preview_label.setText("لا توجد معلومات إضافية متاحة")
        else:
            info_lines = [
                f"المصدر: {self._queue_source_label(selected_job)}",
                f"الحالة: {self._queue_status_label(selected_job.status)}",
                f"عدد المقاطع: {selected_job.clip_count}",
            ]
            if selected_job.output_folder:
                info_lines.append(f"الإخراج: {selected_job.output_folder}")
            if selected_job.failure_stage:
                info_lines.append(f"مرحلة الفشل: {selected_job.failure_stage}")
            if selected_job.failure_message:
                info_lines.append(f"سبب الفشل: {self._short_queue_text(selected_job.failure_message, 120)}")
            self.queue_info_preview_label.setText("\n".join(info_lines))

        processing_state = "قيد المعالجة" if self._queue_processing_thread or self._processing_thread else "جاهز"
        last_result = str(self._last_output_folder) if self._last_output_folder else "لا توجد نتيجة محفوظة بعد"
        self.system_status_label.setText(
            "\n".join(
                [
                    f"حالة التطبيق: {status_text}",
                    f"حالة المعالجة: {processing_state}",
                    f"عدد مهام قائمة الانتظار: {queue_count}",
                    f"مسار الإخراج: {output_path}",
                    f"آخر نتيجة: {last_result}",
                ]
            )
        )

        self._refresh_selected_clip_details()
        self._refresh_import_summary()
        self._refresh_import_extracted_clips_table()
        self._refresh_queue_snapshot_table()
        self._refresh_operations_log_table()

    def _dashboard_output_path(self) -> Path:
        return self._last_output_folder or self.output_root

    def _short_path_text(self, path: Path | str, limit: int = 70) -> str:
        text = str(path)
        if len(text) <= limit:
            return text
        normalized = text.replace("/", "\\")
        parts = [part for part in normalized.split("\\") if part]
        if len(parts) >= 4:
            prefix = parts[0]
            tail = "\\".join(parts[-3:])
            compact = f"{prefix}\\…\\{tail}"
            if len(compact) <= limit:
                return compact
        return f"…{text[-max(10, limit - 1):]}"

    def _current_source_summary(self, *, short: bool) -> str:
        if self.local_file_radio.isChecked():
            path = self.local_file_input.text().strip()
            if short:
                return "فيديو محلي" if path else "فيديو محلي غير محدد"
            return path or "لم يتم اختيار ملف فيديو"

        url = self.youtube_input.text().strip()
        if short:
            return "رابط يوتيوب" if url else "رابط يوتيوب غير محدد"
        return self._safe_queue_source_text(url) if url else "لم يتم إدخال رابط"

    def _current_running_queue_job(self) -> VideoJob | None:
        for job in self.job_queue:
            if self._queue_job_is_running(job):
                return job
        return None

    def _refresh_selected_clip_details(self) -> None:
        if not hasattr(self, "selected_clip_details_label"):
            return

        row = self._selected_clip_row()
        if row is None:
            self.selected_clip_details_label.setText("لم يتم تحديد مقطع")
            self.selected_clip_preview_label.setText("المعاينة المتقدمة قريبًا")
            return

        title = self._cell_text(row, TITLE_COLUMN) or f"مقطع {row + 1}"
        start = self._cell_text(row, START_COLUMN) or "-"
        end = self._cell_text(row, END_COLUMN) or "-"
        exclusions = self._cell_text(row, EXCLUSIONS_COLUMN) or "-"
        duration = self._clip_duration_text(start, end)
        self.selected_clip_preview_label.setText(
            "\n".join(
                [
                    "المعاينة المتقدمة قريبًا" if not self._has_previewable_local_source() else "يمكن استخدام أزرار المعاينة الحالية.",
                    f"{start} - {end}",
                ]
            )
        )
        self.selected_clip_details_label.setText(
            "\n".join(
                [
                    f"العنوان: {title}",
                    f"المصدر: {self._current_source_summary(short=False)}",
                    f"البداية: {start}",
                    f"النهاية: {end}",
                    f"المدة: {duration}",
                    f"الاستثناءات: {exclusions}",
                    "الحالة: جاهز للمراجعة",
                ]
            )
        )

    def _has_previewable_local_source(self) -> bool:
        return self.local_file_radio.isChecked() and bool(self.local_file_input.text().strip())

    def _clip_duration_text(self, start: str, end: str) -> str:
        try:
            start_seconds = parse_timestamp(start)
            end_seconds = parse_timestamp(end)
        except ValueError:
            return "-"
        if end_seconds <= start_seconds:
            return "-"
        total_seconds = end_seconds - start_seconds
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    def _refresh_import_summary(self) -> None:
        if not hasattr(self, "import_summary_label"):
            return
        has_import_context = bool(
            self.youtube_input.text().strip()
            or self.project_name_input.text().strip()
            or self.clips_table.rowCount()
            or self.paste_message_input.toPlainText().strip()
        )
        if not has_import_context:
            self.import_summary_label.setText("سيظهر ملخص الاستيراد بعد تحليل النص أو تحميل مصدر.")
            return

        self.import_summary_label.setText(
            "\n".join(
                [
                    f"الرابط المكتشف: {self._safe_queue_source_text(self.youtube_input.text().strip()) or '-'}",
                    f"عنوان المشروع: {self.project_name_input.text().strip() or '-'}",
                    f"عدد المقاطع: {self.clips_table.rowCount()}",
                    "التحذيرات: تظهر داخل معاينة الاستيراد الذكي عند وجودها",
                    "الأخطاء: تظهر داخل معاينة الاستيراد الذكي عند وجودها",
                ]
            )
        )

    def _refresh_import_extracted_clips_table(self) -> None:
        if not hasattr(self, "import_extracted_clips_table"):
            return
        self.import_extracted_clips_table.blockSignals(True)
        try:
            self.import_extracted_clips_table.setRowCount(0)
            for source_row in range(self.clips_table.rowCount()):
                target_row = self.import_extracted_clips_table.rowCount()
                self.import_extracted_clips_table.insertRow(target_row)

                check_item = QTableWidgetItem("")
                check_item.setFlags((check_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                check_item.setCheckState(Qt.Checked)
                check_item.setTextAlignment(Qt.AlignCenter)
                self.import_extracted_clips_table.setItem(target_row, 0, check_item)

                start = self._cell_text(source_row, START_COLUMN)
                end = self._cell_text(source_row, END_COLUMN)
                status = "جاهز" if start and end else "يحتاج مراجعة"
                values = [
                    str(source_row + 1),
                    self._cell_text(source_row, TITLE_COLUMN) or f"مقطع {source_row + 1}",
                    start,
                    end,
                    self._cell_text(source_row, EXCLUSIONS_COLUMN),
                    status,
                ]
                for offset, value in enumerate(values, start=1):
                    self.import_extracted_clips_table.setItem(
                        target_row,
                        offset,
                        self._readonly_table_item(value),
                    )
        finally:
            self.import_extracted_clips_table.blockSignals(False)

        if hasattr(self, "import_empty_label"):
            has_rows = self.import_extracted_clips_table.rowCount() > 0
            self.import_empty_label.setVisible(not has_rows)
            self.import_extracted_clips_table.setVisible(has_rows)

    def _refresh_queue_snapshot_table(self) -> None:
        if not hasattr(self, "queue_snapshot_table"):
            return
        self.queue_snapshot_table.blockSignals(True)
        try:
            self.queue_snapshot_table.setRowCount(0)
            for index, job in enumerate(self.job_queue, start=1):
                row = self.queue_snapshot_table.rowCount()
                self.queue_snapshot_table.insertRow(row)
                progress = "اكتمل" if job.status == JobStatus.DONE else ("قيد العمل" if self._queue_job_is_running(job) else "-")
                for column, value in enumerate(
                    [
                        str(index),
                        job.title,
                        self._queue_status_label(job.status),
                        progress,
                    ]
                ):
                    self.queue_snapshot_table.setItem(row, column, self._readonly_table_item(value))
        finally:
            self.queue_snapshot_table.blockSignals(False)

    def _refresh_operations_log_table(self) -> None:
        if not hasattr(self, "operations_log_table"):
            return
        self.operations_log_table.blockSignals(True)
        try:
            self.operations_log_table.setRowCount(0)
            log_lines: list[str] = []
            for message in self._global_log_messages[-80:]:
                log_lines.extend(line for line in message.splitlines() if line.strip())
            for line in log_lines[-80:]:
                timestamp = "-"
                details = line
                if line.startswith("[") and "]" in line:
                    timestamp = line[1 : line.index("]")]
                    details = line[line.index("]") + 1 :].strip()
                if "فشل" in details or "خطأ" in details:
                    status = "خطأ"
                elif "تحذير" in details or "راجع" in details:
                    status = "تحذير"
                else:
                    status = "معلومات"
                row = self.operations_log_table.rowCount()
                self.operations_log_table.insertRow(row)
                for column, value in enumerate(["سجل عام", details, "رسالة", timestamp, status]):
                    self.operations_log_table.setItem(row, column, self._readonly_table_item(value))
        finally:
            self.operations_log_table.blockSignals(False)

    def _update_selected_queue_job_details(self) -> None:
        job = self._selected_queue_job()
        if job is None:
            self.queue_job_details_label.setText("لم يتم تحديد مهمة")
            self.queue_job_clips_table.setRowCount(0)
            self.copy_queue_job_details_button.setEnabled(False)
            self._refresh_dashboard_overview()
            return

        self.copy_queue_job_details_button.setEnabled(True)
        self.queue_job_details_label.setText(self._format_queue_job_details(job))
        self._populate_queue_job_clips_preview(job)
        self._refresh_dashboard_overview()

    def _format_queue_job_details(self, job: VideoJob) -> str:
        settings = job.settings
        speed_enabled = "نعم" if settings.speed_adjustment_enabled else "لا"
        volume_enabled = "نعم" if settings.volume_adjustment_enabled else "لا"
        fade_enabled = "نعم" if settings.fade_enabled else "لا"
        black_flash_enabled = "نعم" if settings.black_flash_enabled else "لا"
        export_quality_enabled = "نعم" if settings.export_quality_enabled else "لا"
        cookies_state = "مفعّلة" if settings.use_browser_login else "غير مفعّلة"
        browser_name = settings.browser_name or "chrome"

        if self._queue_job_is_running(job):
            edit_note = "هذه المهمة قيد المعالجة ولا يمكن تعديلها الآن"
        elif job.status == JobStatus.DONE:
            edit_note = "هذه المهمة مكتملة"
        elif job.status in QUEUE_EDITABLE_STATUSES:
            edit_note = "هذه المهمة في الانتظار ويمكن تعديلها"
        else:
            edit_note = "لم يتم تحديد مهمة قابلة للتعديل"

        lines = [
            edit_note,
            "إعدادات المهمة",
            f"الحالة: {self._queue_status_label(job.status)}",
            f"المصدر: {self._queue_source_label(job)}",
            f"رابط YouTube أو مسار الفيديو المحلي: {self._safe_queue_source_text(job.source)}",
            f"اسم المشروع: {job.title}",
            f"عدد المقاطع: {job.clip_count}",
            f"أولوية عالية: {'نعم' if settings.high_priority else 'لا'}",
            f"وقت قبل بداية المقطع: {settings.pre_roll_seconds:g}",
            f"وقت بعد نهاية المقطع: {settings.post_roll_seconds:g}",
            f"هل تعديل سرعة الفيديو مفعّل؟ {speed_enabled}",
            f"سرعة الفيديو: {settings.speed if settings.speed_adjustment_enabled else DEFAULT_VIDEO_SPEED:.2f}x",
            f"هل تعديل مستوى الصوت مفعّل؟ {volume_enabled}",
            f"مستوى الصوت: {settings.volume_percent if settings.volume_adjustment_enabled else DEFAULT_VOLUME_PERCENT}%",
            f"هل البداية والنهاية السوداء مفعّلة؟ {fade_enabled}",
            f"مدة التدرج في البداية: {settings.fade_in_seconds if settings.fade_enabled else DEFAULT_FADE_IN_SECONDS:.2f} ثانية",
            f"مدة التدرج في النهاية: {settings.fade_out_seconds if settings.fade_enabled else DEFAULT_FADE_OUT_SECONDS:.2f} ثانية",
            f"هل الوميض الأسود عند الاستثناء مفعّل؟ {black_flash_enabled}",
            f"مدة الوميض الأسود: {settings.black_flash_duration_seconds if settings.black_flash_enabled else DEFAULT_BLACK_FLASH_SECONDS:.2f} ثانية",
            f"هل تخصيص جودة التصدير مفعّل؟ {export_quality_enabled}",
            f"جودة التصدير: {quality_preset_label_ar(settings.quality_preset) if settings.export_quality_enabled else quality_preset_label_ar(DEFAULT_EXPORT_QUALITY_PRESET)}",
            f"حد الدقة: {resolution_limit_label_ar(settings.resolution_limit) if settings.export_quality_enabled else resolution_limit_label_ar(DEFAULT_RESOLUTION_LIMIT)}",
            f"إعدادات المتصفح/الكوكيز: {cookies_state}، المتصفح: {browser_name}",
        ]
        if job.failure_stage:
            lines.append(f"مرحلة الفشل: {job.failure_stage}")
        if job.failure_message:
            lines.append(f"سبب الفشل: {self._short_queue_text(job.failure_message, 180)}")
        if job.output_folder:
            lines.append(f"مجلد النتائج الفعلي: {job.output_folder}")
        return "\n".join(lines)

    def _safe_queue_source_text(self, source: str) -> str:
        text = str(source).strip()
        parts = urlsplit(text)
        if not parts.scheme or not parts.netloc:
            return text
        query_suffix = "?…" if parts.query else ""
        return f"{parts.scheme}://{parts.netloc}{parts.path}{query_suffix}"

    def _populate_queue_job_clips_preview(self, job: VideoJob) -> None:
        self.queue_job_clips_table.setRowCount(0)
        for index, clip in enumerate(job.clips, start=1):
            row = self.queue_job_clips_table.rowCount()
            self.queue_job_clips_table.insertRow(row)
            self.queue_job_clips_table.setItem(row, NUMBER_COLUMN, self._readonly_table_item(str(index)))
            self.queue_job_clips_table.setItem(row, TITLE_COLUMN, self._readonly_table_item(clip.title))
            self.queue_job_clips_table.setItem(row, START_COLUMN, self._readonly_table_item(clip.start))
            self.queue_job_clips_table.setItem(row, END_COLUMN, self._readonly_table_item(clip.end))
            self.queue_job_clips_table.setItem(row, EXCLUSIONS_COLUMN, self._readonly_table_item(clip.exclusions))

    def copy_selected_queue_job_details(self) -> None:
        job = self._selected_queue_job()
        if job is None:
            self._write_log("لم يتم تحديد مهمة")
            return

        lines = [self._format_queue_job_details(job), "", "مقاطع المهمة"]
        for index, clip in enumerate(job.clips, start=1):
            exclusion_text = f" | الاستثناءات: {clip.exclusions}" if clip.exclusions else ""
            lines.append(f"{index}. {clip.title} | {clip.start} - {clip.end}{exclusion_text}")
        QApplication.clipboard().setText("\n".join(lines))
        self._append_log("تم نسخ تفاصيل المهمة")

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
            self._update_selected_queue_job_details()

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
        self._record_queue_validation_log(job, result, "تم فحص المهمة المحددة")
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
            self._record_queue_validation_log(job, result, "تم فحص كل قائمة الانتظار")
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

    def _record_queue_validation_log(self, job: VideoJob, result, heading: str) -> None:
        job.add_log(heading)
        formatted = format_queue_validation_result_ar(result)
        if formatted:
            job.add_log(formatted)
        if result.status == JobStatus.VALIDATION_ERROR and result.errors:
            job.failure_stage = "validation"
            job.failure_message = result.errors[0]
        elif job.failure_stage == "validation":
            job.failure_stage = ""
            job.failure_message = ""

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
            fade_enabled=self.black_fade_enabled_checkbox.isChecked(),
            fade_in_seconds=self._fade_duration_value(self.fade_in_duration_combo),
            fade_out_seconds=self._fade_duration_value(self.fade_out_duration_combo),
            black_flash_enabled=self.black_flash_enabled_checkbox.isChecked(),
            black_flash_duration_seconds=self._black_flash_duration_value(),
            export_quality_enabled=self.export_quality_enabled_checkbox.isChecked(),
            quality_preset=(
                self._export_quality_preset_value()
                if self.export_quality_enabled_checkbox.isChecked()
                else DEFAULT_EXPORT_QUALITY_PRESET
            ),
            resolution_limit=(
                self._resolution_limit_value()
                if self.export_quality_enabled_checkbox.isChecked()
                else DEFAULT_RESOLUTION_LIMIT
            ),
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

    def start_new_work(self) -> None:
        if self._editing_queue_job is not None:
            if not self._ask_cancel_waiting_job_edit_for_new_work_confirmation():
                return
            self._editing_queue_job = None
        elif self._workspace_has_resettable_data() and not self._ask_new_work_confirmation():
            return

        self._reset_workspace_to_defaults()
        if self._queue_processing_thread is not None:
            self._write_log("تم تجهيز مساحة عمل جديدة، والمهمة الجارية مستمرة في الخلفية")
        else:
            self._write_log("تم تجهيز مساحة عمل جديدة")
        self._update_queue_edit_controls()

    def _workspace_has_resettable_data(self) -> bool:
        return any(
            [
                self.youtube_input.text().strip(),
                self.local_file_input.text().strip(),
                self.project_name_input.text().strip(),
                self.paste_message_input.toPlainText().strip(),
                self._table_has_clip_data(),
                self.pre_padding_input.value() != 0,
                self.post_padding_input.value() != 0,
                self.video_speed_enabled_checkbox.isChecked(),
                self.video_speed_input.value() != DEFAULT_VIDEO_SPEED,
                self.volume_enabled_checkbox.isChecked(),
                self.volume_input.value() != DEFAULT_VOLUME_PERCENT,
                self.black_fade_enabled_checkbox.isChecked(),
                self.black_flash_enabled_checkbox.isChecked(),
                self.export_quality_enabled_checkbox.isChecked(),
                self._export_quality_preset_value() != DEFAULT_ENABLED_QUALITY_PRESET,
                self._resolution_limit_value() != DEFAULT_RESOLUTION_LIMIT,
            ]
        )

    def _reset_workspace_to_defaults(self) -> None:
        self.youtube_radio.setChecked(True)
        self.youtube_input.clear()
        self.local_file_input.clear()
        self.project_name_input.clear()
        self.paste_message_input.clear()
        self.clips_table.setRowCount(0)
        self.pre_padding_input.setValue(0)
        self.post_padding_input.setValue(0)
        self.video_speed_enabled_checkbox.setChecked(False)
        self.video_speed_input.setValue(DEFAULT_VIDEO_SPEED)
        self.volume_enabled_checkbox.setChecked(False)
        self.volume_input.setValue(DEFAULT_VOLUME_PERCENT)
        self.black_fade_enabled_checkbox.setChecked(False)
        self._set_fade_duration_value(self.fade_in_duration_combo, DEFAULT_FADE_IN_SECONDS)
        self._set_fade_duration_value(self.fade_out_duration_combo, DEFAULT_FADE_OUT_SECONDS)
        self.black_flash_enabled_checkbox.setChecked(False)
        self._set_black_flash_duration_value(self.black_flash_duration_combo, DEFAULT_BLACK_FLASH_SECONDS)
        self.export_quality_enabled_checkbox.setChecked(False)
        self._set_export_quality_preset_value(DEFAULT_ENABLED_QUALITY_PRESET)
        self._set_resolution_limit_value(DEFAULT_RESOLUTION_LIMIT)
        self.use_browser_cookies_checkbox.setChecked(False)
        self._set_browser_combo_from_identifier("chrome")
        self._update_speed_volume_controls()
        self._update_source_inputs()

    def _ask_cancel_waiting_job_edit_for_new_work_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("عمل جديد")
        dialog.setText("لديك تعديلات غير محفوظة على مهمة منتظرة. هل تريد إلغاءها وبدء عمل جديد؟")
        confirm_button = dialog.addButton("عمل جديد", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(confirm_button)
        dialog.exec()
        return dialog.clickedButton() == confirm_button

    def _ask_new_work_confirmation(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("عمل جديد")
        dialog.setText("سيتم مسح بيانات العمل الحالي من الواجهة فقط. هل تريد المتابعة؟")
        confirm_button = dialog.addButton("متابعة", QMessageBox.AcceptRole)
        dialog.addButton("إلغاء", QMessageBox.RejectRole)
        dialog.setDefaultButton(confirm_button)
        dialog.exec()
        return dialog.clickedButton() == confirm_button

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
        self.black_fade_enabled_checkbox.setChecked(settings.fade_enabled)
        self._set_fade_duration_value(
            self.fade_in_duration_combo,
            settings.fade_in_seconds if settings.fade_enabled else DEFAULT_FADE_IN_SECONDS,
        )
        self._set_fade_duration_value(
            self.fade_out_duration_combo,
            settings.fade_out_seconds if settings.fade_enabled else DEFAULT_FADE_OUT_SECONDS,
        )
        self.black_flash_enabled_checkbox.setChecked(settings.black_flash_enabled)
        self._set_black_flash_duration_value(
            self.black_flash_duration_combo,
            settings.black_flash_duration_seconds if settings.black_flash_enabled else DEFAULT_BLACK_FLASH_SECONDS,
        )
        self.export_quality_enabled_checkbox.setChecked(settings.export_quality_enabled)
        self._set_export_quality_preset_value(
            settings.quality_preset if settings.export_quality_enabled else DEFAULT_ENABLED_QUALITY_PRESET
        )
        self._set_resolution_limit_value(
            settings.resolution_limit if settings.export_quality_enabled else DEFAULT_RESOLUTION_LIMIT
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
        self._update_selected_queue_job_details()

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
                no_clips_message = "لا توجد مقاطع محفوظة لهذه المهمة"
                if no_clips_message not in job.errors:
                    job.errors.append(no_clips_message)
                job.failure_stage = "validation"
                job.failure_message = no_clips_message
                job.add_log(no_clips_message)

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
                job.add_log(AR_URL_QUEUE_PROCESSING_LATER)

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
        self._update_selected_queue_job_details()

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
        self._update_selected_queue_job_details()

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
            self._apply_queue_row_visual_state(row, job)
        finally:
            self.queue_table.blockSignals(False)
        if job.status == JobStatus.DONE and job.output_folder:
            self._last_output_folder = Path(job.output_folder)
            self.open_output_button.setEnabled(True)
        self._update_queue_edit_controls()
        if self._selected_queue_job() is job:
            self._update_selected_queue_job_details()
            if self._active_log_job is job:
                self._show_selected_queue_job_log()
        self._refresh_dashboard_overview()

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
        clip_fade = self._collect_clip_fade()
        clip_black_flash = self._collect_clip_black_flash()
        export_quality = self._collect_export_quality_settings()

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
            clip_fade=clip_fade,
            clip_black_flash=clip_black_flash,
            export_quality=export_quality,
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
        self.youtube_input.setStyleSheet("")
        self.local_file_input.setStyleSheet("")

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

    def _collect_clip_fade(self) -> ClipFade:
        if not self.black_fade_enabled_checkbox.isChecked():
            return ClipFade()
        return ClipFade(
            enabled=True,
            fade_in_seconds=self._fade_duration_value(self.fade_in_duration_combo),
            fade_out_seconds=self._fade_duration_value(self.fade_out_duration_combo),
        )

    def _collect_clip_black_flash(self) -> ClipBlackFlash:
        if not self.black_flash_enabled_checkbox.isChecked():
            return ClipBlackFlash()
        return ClipBlackFlash(
            enabled=True,
            duration_seconds=self._black_flash_duration_value(),
        )

    def _collect_export_quality_settings(self) -> ExportQualitySettings:
        return normalize_export_quality_settings(
            self.export_quality_enabled_checkbox.isChecked(),
            self._export_quality_preset_value(),
            self._resolution_limit_value(),
        )

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

        self._collect_clip_fade()
        self._collect_clip_black_flash()

        try:
            self._collect_export_quality_settings()
        except ExportQualityError as error:
            errors.append(str(error))

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
        self._global_log_messages = [self._format_log_message(message)]
        self._active_log_job = None
        self._render_log("سجل عام", self._global_log_messages)

    def _append_log(self, message: str) -> None:
        self._global_log_messages.append(self._format_log_message(message))
        if self._active_log_job is None:
            self._render_log("سجل عام", self._global_log_messages)
        else:
            self._flush_log_update()

    def _render_log(self, header: str, messages: list[str]) -> None:
        self.log_header_label.setText(header)
        self.log_area.setPlainText("\n".join(messages))
        if hasattr(self, "queue_job_log_area"):
            self.queue_job_log_area.setPlainText("\n".join(messages))
        self._flush_log_update()

    def show_global_log(self) -> None:
        self._active_log_job = None
        self._render_log("سجل عام", self._global_log_messages)

    def _show_selected_queue_job_log(self) -> None:
        job = self._selected_queue_job()
        if job is None:
            self.show_global_log()
            return

        self._active_log_job = job
        messages = job.log_messages or ["لا توجد رسائل لهذه المهمة بعد."]
        self._render_log("سجل المهمة المحددة", messages)

    def _flush_log_update(self) -> None:
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if hasattr(self, "queue_job_log_area"):
            queue_scrollbar = self.queue_job_log_area.verticalScrollBar()
            queue_scrollbar.setValue(queue_scrollbar.maximum())
        self.log_area.repaint()
        if hasattr(self, "queue_job_log_area"):
            self.queue_job_log_area.repaint()
        self.processing_status_label.repaint()
        self._refresh_dashboard_overview()
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
        clip_fade: ClipFade | None = None,
        clip_black_flash: ClipBlackFlash | None = None,
        export_quality: ExportQualitySettings | None = None,
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
            clip_fade=clip_fade,
            clip_black_flash=clip_black_flash,
            export_quality=export_quality,
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
            self.copy_queue_job_details_button,
            self.queue_job_details_label,
            self.queue_job_clips_table,
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
            self.black_fade_enabled_checkbox,
            self.fade_in_duration_combo,
            self.fade_out_duration_combo,
            self.black_fade_status_label,
            self.black_flash_enabled_checkbox,
            self.black_flash_duration_combo,
            self.black_flash_status_label,
            self.export_quality_enabled_checkbox,
            self.export_quality_preset_combo,
            self.resolution_limit_combo,
            self.export_quality_status_label,
            self.readiness_button,
            self.smart_validation_button,
            self.validate_button,
            self.start_button,
            self.new_work_button,
            self.direct_cut_button,
            self.open_output_button,
            self.show_global_log_button,
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
