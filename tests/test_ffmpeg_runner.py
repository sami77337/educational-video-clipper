import subprocess

import pytest

from src.video import ffmpeg_runner
from src.video.ffmpeg_runner import (
    AR_FFMPEG_NOT_FOUND,
    FfmpegRunnerError,
    _hidden_subprocess_kwargs,
    _resolve_command_for_real_execution,
    bundled_ffmpeg_location,
    resolve_external_tool,
    run_ffmpeg_command,
)


def test_resolve_external_tool_prefers_bundled_ffmpeg_from_candidate_roots(tmp_path, monkeypatch) -> None:
    bundled_ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    bundled_ffmpeg.parent.mkdir()
    bundled_ffmpeg.write_bytes(b"exe")
    monkeypatch.setattr(ffmpeg_runner, "_candidate_tool_roots", lambda: [tmp_path])
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda tool_name: None)

    assert resolve_external_tool("ffmpeg") == str(bundled_ffmpeg)
    assert bundled_ffmpeg_location() == str(bundled_ffmpeg.parent)


def test_resolve_external_tool_raises_when_ffmpeg_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg_runner, "_candidate_tool_roots", lambda: [tmp_path])
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda tool_name: None)

    with pytest.raises(FileNotFoundError):
        resolve_external_tool("ffmpeg")


def test_resolve_command_for_real_execution_uses_resolved_ffmpeg_for_subprocess_run(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg_runner, "resolve_external_tool", lambda tool_name: f"C:/tools/{tool_name}.exe")

    command = _resolve_command_for_real_execution(["ffmpeg", "-version"], subprocess.run)

    assert command == ["C:/tools/ffmpeg.exe", "-version"]


def test_resolve_command_for_fake_runner_keeps_original_command(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg_runner, "resolve_external_tool", lambda tool_name: f"C:/tools/{tool_name}.exe")

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    assert _resolve_command_for_real_execution(["ffmpeg", "-version"], fake_runner) == ["ffmpeg", "-version"]


def test_run_ffmpeg_command_passes_list_and_utf8_capture_without_shell(tmp_path) -> None:
    output_path = tmp_path / "output.mp4"
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="normal ffmpeg progress")

    result = run_ffmpeg_command(["ffmpeg", "-version"], output_path, fake_runner)

    assert result is not None
    assert isinstance(calls[0][0], list)
    assert calls[0][1]["check"] is False
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"
    assert calls[0][1].get("shell", False) is False


def test_run_ffmpeg_command_allows_stderr_when_return_code_is_zero(tmp_path) -> None:
    output_path = tmp_path / "output.mp4"

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="ffmpeg writes progress to stderr")

    assert run_ffmpeg_command(["ffmpeg", "-version"], output_path, fake_runner) is not None


def test_run_ffmpeg_command_non_zero_exit_fails_with_concise_error(tmp_path) -> None:
    output_path = tmp_path / "output.mp4"

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="\n".join([
                "ffmpeg version 8.1.1-full_build-www.gyan.dev",
                "configuration: many flags",
                "Conversion failed: Invalid argument",
            ]),
        )

    with pytest.raises(FfmpegRunnerError) as error:
        run_ffmpeg_command(["ffmpeg", "-version"], output_path, fake_runner)

    message = str(error.value)
    assert "Invalid argument" in message
    assert "configuration:" not in message
    assert "ffmpeg version" not in message


def test_run_ffmpeg_command_rejects_partial_output_on_success(tmp_path) -> None:
    output_path = tmp_path / "output.mp4"
    output_path.write_bytes(b"x")

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(FfmpegRunnerError) as error:
        run_ffmpeg_command(
            ["ffmpeg", "-version"],
            output_path,
            fake_runner,
            should_validate_media_duration=lambda runner: True,
        )

    assert "فارغ" in str(error.value)


def test_probe_duration_reports_arabic_error_when_ffmpeg_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg_runner, "_resolve_command_for_real_execution", lambda command, runner: command)

    def fake_subprocess_run(command, **kwargs):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", fake_subprocess_run)

    with pytest.raises(FfmpegRunnerError) as error:
        ffmpeg_runner.probe_media_duration_seconds(tmp_path / "missing.mp4")

    assert str(error.value) == AR_FFMPEG_NOT_FOUND


def test_hidden_subprocess_kwargs_use_create_no_window_when_available(monkeypatch) -> None:
    monkeypatch.setattr(ffmpeg_runner.subprocess, "CREATE_NO_WINDOW", 12345, raising=False)

    assert _hidden_subprocess_kwargs() == {"creationflags": 12345}
