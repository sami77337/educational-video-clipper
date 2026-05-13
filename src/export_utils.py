"""ZIP export, processing report, and output-folder helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.file_utils import ensure_directory


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


@dataclass(frozen=True)
class ExportArtifacts:
    """Files created after successful processing."""

    zip_folder: Path
    zip_files: list[Path]
    report_path: Path


def ensure_result_folders(project_output_folder: str | Path) -> tuple[Path, Path]:
    """Ensure the project has both sorted result folders."""

    project_folder = Path(project_output_folder)
    reels_folder = ensure_directory(project_folder / REELS_FOLDER_NAME)
    benefits_folder = ensure_directory(project_folder / BENEFITS_FOLDER_NAME)
    return reels_folder, benefits_folder


def create_result_zips(
    project_output_folder: str | Path,
    progress_callback: ProgressCallback | None = None,
) -> ZipExportResult:
    """Create result ZIP files inside the project's ZIP folder."""

    project_folder = Path(project_output_folder)
    zip_files: list[Path] = []

    try:
        reels_folder, benefits_folder = ensure_result_folders(project_folder)
        zip_folder = ensure_directory(project_folder / ZIP_FOLDER_NAME)
        if folder_contains_clips(reels_folder):
            _emit(progress_callback, AR_ZIPPING_REELS)
            zip_files.append(_create_folder_zip(project_folder, reels_folder, zip_folder / REELS_ZIP_NAME))

        if folder_contains_clips(benefits_folder):
            _emit(progress_callback, AR_ZIPPING_BENEFITS)
            zip_files.append(_create_folder_zip(project_folder, benefits_folder, zip_folder / BENEFITS_ZIP_NAME))

        _emit(progress_callback, AR_CREATING_COMPLETE_ZIP)
        complete_zip = zip_folder / COMPLETE_RESULT_ZIP_NAME
        _create_zip_from_folders(project_folder, [reels_folder, benefits_folder], complete_zip)
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

    lines = [
        "تقرير القص",
        "",
        f"Project name: {data.project_name}",
        f"Source type: {data.source_type}",
        f"Total clips count: {data.total_clips_count}",
        f"Reels count: {data.reels_count}",
        f"Benefits count: {data.benefits_count}",
        "Output folders:",
    ]
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
