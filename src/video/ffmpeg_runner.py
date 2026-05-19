"""FFmpeg runtime, tool resolution, and output validation helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.time_utils import format_seconds


AR_FFMPEG_NOT_FOUND = "لم يتم العثور على ffmpeg"
MIN_OUTPUT_BYTES = 1024
OUTPUT_DURATION_TOLERANCE_SECONDS = 2.0

SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]
DurationProbe = Callable[[str | Path], float]


class FfmpegRunnerError(RuntimeError):
    """Raised when FFmpeg runtime work fails."""


def _candidate_tool_roots() -> list[Path]:
    """Return likely folders that may contain bundled external tools."""

    roots: list[Path] = []
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        roots.append(executable.parent)
    roots.extend([
        Path.cwd(),
        Path(__file__).resolve().parent.parent,
        Path(__file__).resolve().parent.parent.parent,
    ])

    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved not in unique:
            unique.append(resolved)
    return unique


def resolve_external_tool(tool_name: str) -> str:
    """Resolve a bundled or system external executable/cmd by name."""

    if tool_name.lower().endswith((".exe", ".cmd", ".bat")):
        names = [tool_name]
    else:
        names = [f"{tool_name}.exe", f"{tool_name}.cmd", f"{tool_name}.bat", tool_name]

    subfolders = [Path(""), Path("bin"), Path("_internal"), Path("_internal") / "bin"]
    for root in _candidate_tool_roots():
        for subfolder in subfolders:
            folder = root / subfolder
            for name in names:
                candidate = folder / name
                if candidate.is_file():
                    return str(candidate)

    found = shutil.which(tool_name)
    if found:
        return found

    raise FileNotFoundError(tool_name)


def _resolve_command_for_real_execution(command: list[str], runner: SubprocessRunner) -> list[str]:
    """Use bundled executable paths for real subprocesses only."""

    if runner is not subprocess.run or not command:
        return command

    executable_name = Path(command[0]).name.lower()
    if executable_name in {"ffmpeg", "ffmpeg.exe", "ffmpeg.cmd", "ffmpeg.bat"}:
        return [resolve_external_tool("ffmpeg"), *command[1:]]
    if executable_name in {"ffprobe", "ffprobe.exe", "ffprobe.cmd", "ffprobe.bat"}:
        return [resolve_external_tool("ffprobe"), *command[1:]]
    return command


def bundled_ffmpeg_location() -> str | None:
    """Return a directory usable by yt-dlp's ffmpeg_location option."""

    try:
        ffmpeg_path = Path(resolve_external_tool("ffmpeg"))
    except FileNotFoundError:
        return None
    return str(ffmpeg_path.parent)


def run_ffmpeg_command(
    command: list[str],
    output_path: str | Path,
    runner: SubprocessRunner = subprocess.run,
    should_validate_media_duration: Callable[[SubprocessRunner], bool] | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Run ffmpeg safely and require a clean successful exit.

    FFmpeg writes normal progress and metadata to stderr, so stderr content alone
    is not an error. However, a non-zero return code is a real failure even if a
    partial output file exists. Accepting partial files caused short, corrupted,
    or incomplete clips to be treated as successful, so this function is strict.
    """

    command_to_run = _resolve_command_for_real_execution(command, runner)
    completed = runner(
        command_to_run,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_hidden_subprocess_kwargs(),
    )

    # Unit tests often inject a simple fake runner that returns None and records
    # commands only. Preserve that lightweight testing behavior.
    if completed is None:
        return None

    should_validate = should_validate_media_duration or _should_validate_media_duration
    return_code = getattr(completed, "returncode", 0)
    if return_code == 0:
        if should_validate(runner) and not _output_file_is_usable(output_path):
            raise FfmpegRunnerError("فشل إنشاء ملف المقطع الناتج أو أن الملف الناتج فارغ")
        return completed

    combined_output = _combined_process_output(completed)
    detail = _concise_ffmpeg_error(combined_output, return_code)
    raise FfmpegRunnerError(detail)


def _combined_process_output(completed: subprocess.CompletedProcess[str]) -> str:
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return "\n".join(part for part in (stderr, stdout) if part).strip()


def _hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return Windows-only subprocess options that prevent console windows.

    FFmpeg is a console executable. When the app is packaged with a GUI
    bootloader, Windows may show a black console window for each ffmpeg run
    unless CREATE_NO_WINDOW is passed. Non-Windows systems ignore this helper.
    """

    creation_flag = getattr(subprocess, "CREATE_NO_WINDOW", None)
    if creation_flag is None:
        return {}
    return {"creationflags": creation_flag}


def _output_file_is_usable(path: str | Path) -> bool:
    try:
        output_path = Path(path)
        return output_path.is_file() and output_path.stat().st_size >= MIN_OUTPUT_BYTES
    except OSError:
        return False


def _should_validate_media_duration(runner: SubprocessRunner) -> bool:
    """Only run ffprobe validation for real subprocess executions.

    Unit tests use fake runners with dummy byte files, so ffprobe would fail on
    those artificial files. The actual application uses subprocess.run.
    """

    return runner is subprocess.run


def probe_media_duration_seconds(path: str | Path) -> float:
    """Read media duration and return seconds as float.

    Prefer ffprobe when it exists, but fall back to parsing ffmpeg's input
    metadata. This makes the portable package work even when only ffmpeg.exe is
    bundled.
    """

    output_path = Path(path)
    ffprobe_command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(output_path),
    ]

    try:
        completed = subprocess.run(
            _resolve_command_for_real_execution(ffprobe_command, subprocess.run),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_hidden_subprocess_kwargs(),
        )
        if completed.returncode == 0:
            duration = float((completed.stdout or "").strip())
            if duration > 0:
                return duration
    except (FileNotFoundError, ValueError):
        pass

    return _probe_media_duration_with_ffmpeg(output_path)


def _probe_media_duration_with_ffmpeg(path: Path) -> float:
    command = ["ffmpeg", "-hide_banner", "-i", str(path)]
    try:
        completed = subprocess.run(
            _resolve_command_for_real_execution(command, subprocess.run),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_hidden_subprocess_kwargs(),
        )
    except FileNotFoundError as error:
        raise FfmpegRunnerError(AR_FFMPEG_NOT_FOUND) from error

    combined = _combined_process_output(completed)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", combined)
    if not match:
        raise FfmpegRunnerError("تعذر التحقق من مدة المقطع الناتج")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    duration = hours * 3600 + minutes * 60 + seconds
    if duration <= 0:
        raise FfmpegRunnerError("مدة المقطع الناتج غير صالحة")
    return duration


def verify_output_duration(
    output_path: str | Path,
    expected_duration_seconds: int | float,
    *,
    tolerance_seconds: float = OUTPUT_DURATION_TOLERANCE_SECONDS,
    probe_duration: DurationProbe = probe_media_duration_seconds,
) -> None:
    """Ensure the resulting clip duration is close to the requested duration."""

    actual = probe_duration(output_path)
    expected = float(expected_duration_seconds)
    lower_bound = max(0.1, expected - tolerance_seconds)
    upper_bound = expected + tolerance_seconds
    if actual < lower_bound:
        raise FfmpegRunnerError(
            "مدة المقطع الناتج أقصر من المطلوب: "
            f"المطلوب تقريبًا {format_seconds(int(round(expected)))}، "
            f"والناتج {format_seconds(int(round(actual)))}"
        )
    if actual > upper_bound:
        raise FfmpegRunnerError(
            "مدة المقطع الناتج أطول من المطلوب: "
            f"المطلوب تقريبًا {format_seconds(int(round(expected)))}، "
            f"والناتج {format_seconds(int(round(actual)))}"
        )


def _concise_ffmpeg_error(output: str, return_code: int | None = None) -> str:
    """Return a short user-facing ffmpeg error instead of dumping full build logs."""

    important_keywords = (
        "error",
        "failed",
        "invalid",
        "no such file",
        "permission denied",
        "conversion failed",
        "unable",
        "cannot",
        "not found",
    )
    ignored_prefixes = (
        "ffmpeg version",
        "built with",
        "configuration:",
        "libav",
        "libsw",
        "libpostproc",
        "input #",
        "output #",
        "metadata:",
        "stream #",
        "stream mapping:",
        "press [q]",
        "frame=",
        "video:",
        "audio:",
        "subtitle:",
        "side data:",
        "handler_name",
        "major_brand",
        "minor_version",
        "compatible_brands",
        "encoder",
        "duration:",
        "bitrate",
        "using sar",
        "using cpu capabilities",
        "profile high",
        "264 - core",
        "consecutive b-frames",
        "mb ",
        "8x8 transform",
        "coded y",
        "i16 ",
        "i8 ",
        "i4 ",
        "i8c ",
        "weighted p-frames",
        "qavg",
    )

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    important = [line for line in lines if any(keyword in line.lower() for keyword in important_keywords)]
    candidates = important or [
        line for line in lines
        if not line.lower().startswith(ignored_prefixes)
        and "late sei is not implemented" not in line.lower()
        and "ffmpeg-devel" not in line.lower()
        and "streams.videolan.org" not in line.lower()
    ]
    selected = candidates[-5:]
    if selected:
        return "\n".join(selected)
    if return_code is not None:
        return f"ffmpeg failed with exit code {return_code}"
    return "ffmpeg failed"
