"""ZIP export, processing report, and output-folder helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.classification import (
    ClassificationRule,
    classification_folder_names,
    format_rule_minutes,
    get_default_classification_rules,
    sanitize_classification_folder_name,
)
from src.file_utils import ensure_directory
from src.video_speed import DEFAULT_VIDEO_SPEED, format_video_speed, normalize_video_speed
from src.video_volume import DEFAULT_VOLUME_PERCENT, format_volume_percent, normalize_volume_percent


REELS_FOLDER_NAME = "ريلز"
BENEFITS_FOLDER_NAME = "فوائد"
ZIP_FOLDER_NAME = "ZIP"
REPORT_FILE_NAME = "تقرير-القص.txt"
REELS_ZIP_NAME = "ريلز.zip"
BENEFITS_ZIP_NAME = "فوائد.zip"
COMPLETE_RESULT_ZIP_NAME = "النتيجة-كاملة.zip"

AR_ZIPPING_REELS = "جاري ضغط ملفات الريلز"
AR_ZIPPING_BENEFITS = "جاري ضغط ملفات الفوائد"
AR_CREATING_COMPLETE_ZIP = "جاري إنشاء ملف النتيجة الكاملة"
AR_ZIP_FILES_CREATED = "تم إنشاء ملفات ZIP"
AR_REPORT_CREATED = "تم إنشاء تقرير القص"
AR_PROCESSING_SUCCESS = "تم الانتهاء بنجاح"
AR_ZIP_CREATION_FAILED = "خطأ: فشل إنشاء ملفات ZIP"
AR_REPORT_CREATION_FAILED = "خطأ: فشل إنشاء تقرير القص"
AR_OUTPUT_FOLDER_MISSING = "خطأ: مجلد الإخراج غير موجود"

ProgressCallback = Callable[[str], None]


class ExportError(RuntimeError):
    """Raised when result export or folder validation fails."""


@dataclass(frozen=True)
class ZipExportResult:
    """ZIP files created for a project."""

    zip_folder: Path
    zip_files: list[Path]


@dataclass(frozen=True)
class ProcessingReportData:
    """Data included in the final processing report."""

    project_name: str
    source_type: str
    total_clips_count: int
    reels_count: int
    benefits_count: int
    output_folders: list[Path]
    zip_files: list[Path]
    started_at: datetime
    ended_at: datetime
    skipped_or_failed_items: list[str]
    classification_rules: list[ClassificationRule] = field(default_factory=list)
    clip_counts_by_folder: dict[str, int] = field(default_factory=dict)
    clip_details: list["ProcessingReportClipData"] = field(default_factory=list)
    pre_padding_seconds: float = 0.0
    post_padding_seconds: float = 0.0
    video_speed: float = DEFAULT_VIDEO_SPEED
    volume_percent: int = DEFAULT_VOLUME_PERCENT


@dataclass(frozen=True)
class ProcessingReportClipData:
    """One processed clip line for the final report."""

    number: int
    title: str
    start: str
    end: str
    exclusions: str
    folder_name: str


@dataclass(frozen=True)
class ExportArtifacts:
    """Files created after successful processing."""

    zip_folder: Path
    zip_files: list[Path]
    report_path: Path


def ensure_result_folders(
    project_output_folder: str | Path,
    folder_names: Sequence[str] | None = None,
) -> tuple[Path, ...]:
    """Ensure the project has sorted result folders."""

    project_folder = Path(project_output_folder)
    return tuple(ensure_directory(project_folder / folder_name) for folder_name in _safe_folder_names(folder_names))


def create_result_zips(
    project_output_folder: str | Path,
    progress_callback: ProgressCallback | None = None,
    folder_names: Sequence[str] | None = None,
) -> ZipExportResult:
    """Create result ZIP files inside the project's ZIP folder."""

    project_folder = Path(project_output_folder)
    zip_files: list[Path] = []

    try:
        result_folders = ensure_result_folders(project_folder, folder_names)
        zip_folder = ensure_directory(project_folder / ZIP_FOLDER_NAME)
        for result_folder in result_folders:
            if folder_contains_clips(result_folder):
                _emit(progress_callback, _folder_zip_progress_message(result_folder.name))
                zip_files.append(
                    _create_folder_zip(
                        project_folder,
                        result_folder,
                        zip_folder / f"{result_folder.name}.zip",
                    )
                )

        _emit(progress_callback, AR_CREATING_COMPLETE_ZIP)
        complete_zip = zip_folder / COMPLETE_RESULT_ZIP_NAME
        _create_zip_from_folders(project_folder, result_folders, complete_zip)
        zip_files.append(complete_zip)
    except Exception as error:
        raise ExportError(f"{AR_ZIP_CREATION_FAILED}: {error}") from error

    _emit(progress_callback, AR_ZIP_FILES_CREATED)
    return ZipExportResult(zip_folder=zip_folder, zip_files=zip_files)


def folder_contains_clips(folder: str | Path) -> bool:
    """Return True when a folder contains generated mp4 clips."""

    path = Path(folder)
    return path.is_dir() and any(child.is_file() and child.suffix.lower() == ".mp4" for child in path.iterdir())


def build_processing_report(data: ProcessingReportData) -> str:
    """Build the final processing report text."""

    classification_rules = data.classification_rules or get_default_classification_rules()
    clip_counts = _report_clip_counts(data)
    lines = [
        "تقرير القص",
        "",
        f"Project name: {data.project_name}",
        f"Source type: {data.source_type}",
        f"Total clips count: {data.total_clips_count}",
        f"Reels count: {data.reels_count}",
        f"Benefits count: {data.benefits_count}",
    ]
    if _has_clip_padding(data):
        lines.extend(
            [
                f"وقت قبل بداية المقطع: {_format_seconds_value(data.pre_padding_seconds)} ثانية",
                f"وقت بعد نهاية المقطع: {_format_seconds_value(data.post_padding_seconds)} ثانية",
            ]
        )
    if _has_video_speed(data):
        lines.append(f"سرعة الفيديو: {format_video_speed(data.video_speed)}")
    if _has_volume(data):
        lines.append(f"مستوى الصوت: {format_volume_percent(data.volume_percent)}")
    lines.append("Classification rules:")
    lines.extend(_format_classification_rule(rule) for rule in classification_rules)
    lines.append("Clip counts by folder:")
    lines.extend(f"- {folder_name}: {count}" for folder_name, count in clip_counts.items())
    if data.clip_details:
        lines.append("Clip details:")
        for clip in data.clip_details:
            lines.extend(_format_clip_detail(clip))
    lines.append("Output folders:")
    lines.extend(f"- {folder}" for folder in data.output_folders)
    lines.append("ZIP files created:")
    if data.zip_files:
        lines.extend(f"- {zip_file}" for zip_file in data.zip_files)
    else:
        lines.append("- None")

    lines.extend(
        [
            f"Start timestamp of processing: {_format_timestamp(data.started_at)}",
            f"End timestamp of processing: {_format_timestamp(data.ended_at)}",
            "Skipped or failed items:",
        ]
    )
    if data.skipped_or_failed_items:
        lines.extend(f"- {item}" for item in data.skipped_or_failed_items)
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def write_processing_report(project_output_folder: str | Path, data: ProcessingReportData) -> Path:
    """Write the final processing report into the project folder."""

    report_path = Path(project_output_folder) / REPORT_FILE_NAME
    try:
        report_path.write_text(build_processing_report(data), encoding="utf-8")
    except OSError as error:
        raise ExportError(f"{AR_REPORT_CREATION_FAILED}: {error}") from error

    return report_path


def validate_output_folder_path(folder_path: str | Path | None) -> Path:
    """Validate that an output folder exists before opening it."""

    if folder_path is None:
        raise ExportError(AR_OUTPUT_FOLDER_MISSING)

    path = Path(folder_path)
    if not path.is_dir():
        raise ExportError(AR_OUTPUT_FOLDER_MISSING)

    return path


def _safe_folder_names(folder_names: Sequence[str] | None) -> list[str]:
    names = list(folder_names) if folder_names is not None else classification_folder_names()
    safe_names: list[str] = []
    for name in names:
        safe_name = sanitize_classification_folder_name(name)
        if safe_name not in safe_names:
            safe_names.append(safe_name)

    return safe_names


def _folder_zip_progress_message(folder_name: str) -> str:
    if folder_name == REELS_FOLDER_NAME:
        return AR_ZIPPING_REELS
    if folder_name == BENEFITS_FOLDER_NAME:
        return AR_ZIPPING_BENEFITS
    return f"جاري ضغط ملفات {folder_name}"


def _format_classification_rule(rule: ClassificationRule) -> str:
    max_minutes = format_rule_minutes(rule.max_minutes)
    return (
        f"- {rule.name}: من {format_rule_minutes(rule.min_minutes)} "
        f"إلى {max_minutes} دقيقة -> {sanitize_classification_folder_name(rule.folder_name)}"
    )


def _report_clip_counts(data: ProcessingReportData) -> Mapping[str, int]:
    if data.clip_counts_by_folder:
        return data.clip_counts_by_folder

    return {
        REELS_FOLDER_NAME: data.reels_count,
        BENEFITS_FOLDER_NAME: data.benefits_count,
    }


def _format_clip_detail(clip: ProcessingReportClipData) -> list[str]:
    lines = [
        f"{clip.number:02d} - {clip.title}",
        f"البداية: {clip.start}",
        f"النهاية: {clip.end}",
    ]
    if clip.exclusions:
        lines.append(f"الاستثناءات: {clip.exclusions}")
        exclusion_count = _count_exclusions(clip.exclusions)
        lines.append(f"عدد الاستثناءات داخل المقطع: {exclusion_count}")
        if exclusion_count > 1:
            lines.append("تم تطبيق أكثر من استثناء داخل هذا المقطع")
    lines.append(f"المجلد: {clip.folder_name}")
    return lines


def _has_clip_padding(data: ProcessingReportData) -> bool:
    return data.pre_padding_seconds > 0 or data.post_padding_seconds > 0


def _has_video_speed(data: ProcessingReportData) -> bool:
    return normalize_video_speed(data.video_speed) != DEFAULT_VIDEO_SPEED


def _has_volume(data: ProcessingReportData) -> bool:
    return normalize_volume_percent(data.volume_percent) != DEFAULT_VOLUME_PERCENT


def _format_seconds_value(value: float) -> str:
    return f"{float(value):g}"


def _count_exclusions(exclusions: str) -> int:
    return len([part for part in exclusions.split(",") if part.strip()])


def _create_folder_zip(project_folder: Path, folder: Path, zip_path: Path) -> Path:
    _create_zip_from_folders(project_folder, [folder], zip_path)
    return zip_path


def _create_zip_from_folders(project_folder: Path, folders: Iterable[Path], zip_path: Path) -> Path:
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zip_file:
        for folder in folders:
            _add_folder_to_zip(zip_file, project_folder, folder)

    return zip_path


def _add_folder_to_zip(zip_file: ZipFile, project_folder: Path, folder: Path) -> None:
    folder_arcname = folder.relative_to(project_folder).as_posix().rstrip("/") + "/"
    zip_file.writestr(folder_arcname, "")
    for child in sorted(folder.rglob("*")):
        arcname = child.relative_to(project_folder).as_posix()
        if child.is_dir():
            zip_file.writestr(arcname.rstrip("/") + "/", "")
        else:
            zip_file.write(child, arcname)


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="seconds")


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)
