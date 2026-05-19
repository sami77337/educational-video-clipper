"""Environment readiness checks for non-technical users."""

from __future__ import annotations

import importlib.util
import shutil
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.video.ffmpeg_runner import resolve_external_tool


STATUS_READY = "جاهز"
STATUS_WARNING = "تحذير"
STATUS_ERROR = "خطأ"
DEFAULT_MIN_FREE_SPACE_BYTES = 1 * 1024 * 1024 * 1024
WINDOWS_LONG_PATH_WARNING_LENGTH = 240

ToolResolver = Callable[[str], str]
PackageFinder = Callable[[str], Any]
DiskUsageProvider = Callable[[str | Path], Any]
WriteProbe = Callable[[Path], bool]


@dataclass(frozen=True)
class ReadinessCheckItem:
    """One readiness check result."""

    name: str
    status: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.status == STATUS_ERROR

    @property
    def is_warning(self) -> bool:
        return self.status == STATUS_WARNING


@dataclass(frozen=True)
class ReadinessReport:
    """Complete readiness check result."""

    items: list[ReadinessCheckItem]

    @property
    def has_errors(self) -> bool:
        return any(item.is_error for item in self.items)

    @property
    def has_warnings(self) -> bool:
        return any(item.is_warning for item in self.items)


def run_readiness_check(
    output_folder: str | Path,
    temp_folder: str | Path | None = None,
    *,
    selected_paths: Sequence[str | Path] | None = None,
    minimum_free_space_bytes: int = DEFAULT_MIN_FREE_SPACE_BYTES,
    tool_resolver: ToolResolver = resolve_external_tool,
    package_finder: PackageFinder = importlib.util.find_spec,
    disk_usage_provider: DiskUsageProvider = shutil.disk_usage,
    write_probe: WriteProbe | None = None,
) -> ReadinessReport:
    """Run advisory readiness checks without changing app startup behavior."""

    output_path = Path(output_folder)
    temp_path = Path(temp_folder) if temp_folder is not None else output_path / "_temp"
    paths_to_check = [output_path, temp_path, *(Path(path) for path in selected_paths or [])]
    active_write_probe = write_probe or _can_write_to_directory

    items = [
        _check_ffmpeg(tool_resolver),
        _check_ffprobe_or_fallback(tool_resolver),
        _check_ytdlp(package_finder),
        _check_writable_folder(
            "output_folder",
            output_path,
            ready_message="مجلد الإخراج قابل للكتابة",
            error_message="لا يمكن الكتابة داخل مجلد الإخراج",
            write_probe=active_write_probe,
        ),
        _check_writable_folder(
            "temporary_folder",
            temp_path,
            ready_message="المجلد المؤقت قابل للكتابة",
            error_message="لا يمكن الكتابة داخل المجلد المؤقت",
            write_probe=active_write_probe,
        ),
        _check_free_disk_space(output_path, minimum_free_space_bytes, disk_usage_provider),
        _check_windows_path_lengths(paths_to_check),
    ]
    return ReadinessReport(items=items)


def format_readiness_report_ar(report: ReadinessReport) -> str:
    """Format readiness results as short Arabic lines for the log area."""

    return "\n".join(f"{item.status}: {item.message}" for item in report.items)


def _check_ffmpeg(tool_resolver: ToolResolver) -> ReadinessCheckItem:
    try:
        tool_resolver("ffmpeg")
    except FileNotFoundError:
        return ReadinessCheckItem("ffmpeg", STATUS_ERROR, "لم يتم العثور على ffmpeg")
    except Exception:
        return ReadinessCheckItem("ffmpeg", STATUS_ERROR, "تعذر فحص ffmpeg")

    return ReadinessCheckItem("ffmpeg", STATUS_READY, "ffmpeg جاهز")


def _check_ffprobe_or_fallback(tool_resolver: ToolResolver) -> ReadinessCheckItem:
    try:
        tool_resolver("ffprobe")
    except FileNotFoundError:
        try:
            tool_resolver("ffmpeg")
        except Exception:
            return ReadinessCheckItem("ffprobe", STATUS_ERROR, "لم يتم العثور على ffprobe أو بديل مناسب")
        return ReadinessCheckItem(
            "ffprobe",
            STATUS_WARNING,
            "ffprobe غير موجود وسيتم استخدام ffmpeg كبديل للتحقق من مدة الفيديو",
        )
    except Exception:
        return ReadinessCheckItem("ffprobe", STATUS_ERROR, "تعذر فحص ffprobe")

    return ReadinessCheckItem("ffprobe", STATUS_READY, "ffprobe جاهز")


def _check_ytdlp(package_finder: PackageFinder) -> ReadinessCheckItem:
    try:
        package_found = package_finder("yt_dlp") is not None
    except Exception:
        package_found = False

    if package_found:
        return ReadinessCheckItem("yt_dlp", STATUS_READY, "yt-dlp جاهز")
    return ReadinessCheckItem("yt_dlp", STATUS_ERROR, "yt-dlp غير متاح")


def _check_writable_folder(
    name: str,
    folder: Path,
    *,
    ready_message: str,
    error_message: str,
    write_probe: WriteProbe,
) -> ReadinessCheckItem:
    try:
        is_writable = write_probe(folder)
    except Exception:
        is_writable = False

    if is_writable:
        return ReadinessCheckItem(name, STATUS_READY, ready_message)
    return ReadinessCheckItem(name, STATUS_ERROR, error_message)


def _check_free_disk_space(
    output_folder: Path,
    minimum_free_space_bytes: int,
    disk_usage_provider: DiskUsageProvider,
) -> ReadinessCheckItem:
    try:
        usage_target = _nearest_existing_path(output_folder)
        free_bytes = disk_usage_provider(usage_target).free
    except Exception:
        return ReadinessCheckItem("disk_space", STATUS_WARNING, "تعذر فحص المساحة المتوفرة")

    if free_bytes >= minimum_free_space_bytes:
        return ReadinessCheckItem("disk_space", STATUS_READY, "المساحة المتوفرة كافية")
    return ReadinessCheckItem("disk_space", STATUS_ERROR, "المساحة المتوفرة غير كافية")


def _check_windows_path_lengths(paths: Sequence[Path]) -> ReadinessCheckItem:
    longest_length = max((len(str(path)) for path in paths), default=0)
    if longest_length >= WINDOWS_LONG_PATH_WARNING_LENGTH:
        return ReadinessCheckItem("path_length", STATUS_WARNING, "المسار طويل وقد يسبب مشكلة في Windows")
    return ReadinessCheckItem("path_length", STATUS_READY, "طول المسارات مناسب")


def _can_write_to_directory(folder: Path) -> bool:
    folder.mkdir(parents=True, exist_ok=True)
    probe_path = folder / f".readiness-{uuid.uuid4().hex}.tmp"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
        return True
    except OSError:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _nearest_existing_path(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current
