from __future__ import annotations

from collections import namedtuple
from pathlib import Path

from src.readiness import (
    STATUS_ERROR,
    STATUS_READY,
    STATUS_WARNING,
    ReadinessCheckItem,
    ReadinessReport,
    format_readiness_report_ar,
    run_readiness_check,
)


DiskUsage = namedtuple("DiskUsage", "total used free")


def _ready_tool_resolver(tool_name: str) -> str:
    return f"C:/tools/{tool_name}.exe"


def _missing_tool_resolver(tool_name: str) -> str:
    raise FileNotFoundError(tool_name)


def _package_found(package_name: str) -> object:
    return object()


def _package_missing(package_name: str) -> None:
    return None


def _disk_usage_with_free_space(free_bytes: int):
    return lambda path: DiskUsage(total=free_bytes * 2, used=0, free=free_bytes)


def test_readiness_all_ready_reports_clear_arabic_messages(tmp_path: Path) -> None:
    report = run_readiness_check(
        tmp_path / "output",
        tmp_path / "output" / "_temp",
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
    )

    assert not report.has_errors
    assert {item.name: item.status for item in report.items}["ffmpeg"] == STATUS_READY
    formatted = format_readiness_report_ar(report)
    assert "جاهز: ffmpeg جاهز" in formatted
    assert "جاهز: ffprobe جاهز" in formatted
    assert "جاهز: yt-dlp جاهز" in formatted
    assert "جاهز: مجلد الإخراج قابل للكتابة" in formatted
    assert "جاهز: المساحة المتوفرة كافية" in formatted


def test_readiness_warns_when_ffprobe_uses_ffmpeg_fallback(tmp_path: Path) -> None:
    def resolver(tool_name: str) -> str:
        if tool_name == "ffprobe":
            raise FileNotFoundError(tool_name)
        return f"C:/tools/{tool_name}.exe"

    report = run_readiness_check(
        tmp_path / "output",
        tool_resolver=resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
    )

    ffprobe_item = next(item for item in report.items if item.name == "ffprobe")
    assert ffprobe_item.status == STATUS_WARNING
    assert "ffmpeg كبديل" in ffprobe_item.message


def test_readiness_errors_when_ffmpeg_is_missing(tmp_path: Path) -> None:
    report = run_readiness_check(
        tmp_path / "output",
        tool_resolver=_missing_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
    )

    assert report.has_errors
    assert next(item for item in report.items if item.name == "ffmpeg").status == STATUS_ERROR
    assert "لم يتم العثور على ffmpeg" in format_readiness_report_ar(report)


def test_readiness_errors_when_ytdlp_is_missing(tmp_path: Path) -> None:
    report = run_readiness_check(
        tmp_path / "output",
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_missing,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
    )

    yt_dlp_item = next(item for item in report.items if item.name == "yt_dlp")
    assert yt_dlp_item.status == STATUS_ERROR
    assert "yt-dlp غير متاح" in yt_dlp_item.message


def test_readiness_detects_non_writable_output_folder(tmp_path: Path) -> None:
    output_folder = tmp_path / "blocked-output"

    report = run_readiness_check(
        output_folder,
        tmp_path / "temp",
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
        write_probe=lambda path: path != output_folder,
    )

    output_item = next(item for item in report.items if item.name == "output_folder")
    assert output_item.status == STATUS_ERROR
    assert output_item.message == "لا يمكن الكتابة داخل مجلد الإخراج"


def test_readiness_detects_non_writable_temporary_folder(tmp_path: Path) -> None:
    temp_folder = tmp_path / "blocked-temp"

    report = run_readiness_check(
        tmp_path / "output",
        temp_folder,
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
        write_probe=lambda path: path != temp_folder,
    )

    temp_item = next(item for item in report.items if item.name == "temporary_folder")
    assert temp_item.status == STATUS_ERROR
    assert temp_item.message == "لا يمكن الكتابة داخل المجلد المؤقت"


def test_readiness_errors_when_disk_space_is_low(tmp_path: Path) -> None:
    report = run_readiness_check(
        tmp_path / "output",
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(50 * 1024 * 1024),
    )

    disk_item = next(item for item in report.items if item.name == "disk_space")
    assert disk_item.status == STATUS_ERROR
    assert disk_item.message == "المساحة المتوفرة غير كافية"


def test_readiness_warns_about_long_windows_paths_without_printing_them(tmp_path: Path) -> None:
    long_path = tmp_path / ("a" * 250)

    report = run_readiness_check(
        tmp_path / "output",
        selected_paths=[long_path],
        tool_resolver=_ready_tool_resolver,
        package_finder=_package_found,
        disk_usage_provider=_disk_usage_with_free_space(5 * 1024 * 1024 * 1024),
    )

    path_item = next(item for item in report.items if item.name == "path_length")
    formatted = format_readiness_report_ar(report)
    assert path_item.status == STATUS_WARNING
    assert "المسار طويل" in path_item.message
    assert str(long_path) not in formatted


def test_format_readiness_report_uses_status_prefixes() -> None:
    report = ReadinessReport(
        [
            ReadinessCheckItem("ok", STATUS_READY, "ffmpeg جاهز"),
            ReadinessCheckItem("warn", STATUS_WARNING, "المسار طويل وقد يسبب مشكلة في Windows"),
            ReadinessCheckItem("error", STATUS_ERROR, "لا يمكن الكتابة داخل مجلد الإخراج"),
        ]
    )

    assert format_readiness_report_ar(report).splitlines() == [
        "جاهز: ffmpeg جاهز",
        "تحذير: المسار طويل وقد يسبب مشكلة في Windows",
        "خطأ: لا يمكن الكتابة داخل مجلد الإخراج",
    ]
