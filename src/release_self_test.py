"""Offline checks executed inside the actual packaged application."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import traceback
from pathlib import Path


def run_release_self_test(report_path: str) -> int:
    """Exercise bundled Python/Qt, EJS, Deno, and real FFmpeg cutting."""
    from src.version import APP_VERSION

    report: dict = {"app_version": APP_VERSION, "status": "failed", "checks": {}}
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from src.main_window import MainWindow
        from src.video.ffmpeg_runner import (
            _hidden_subprocess_kwargs,
            probe_media_duration_seconds,
            resolve_external_tool,
            run_ffmpeg_command,
        )
        from src.video_processor import cut_clip
        from yt_dlp.version import __version__ as ytdlp_version
        from yt_dlp.dependencies import yt_dlp_ejs
        import yt_dlp_ejs.yt.solver as solver

        if not yt_dlp_ejs:
            raise RuntimeError("yt-dlp did not recognize its bundled EJS package")
        report["yt_dlp_version"] = ytdlp_version
        report["ejs_version"] = yt_dlp_ejs.version
        lib, core = solver.lib(), solver.core()
        if not lib or not core:
            raise RuntimeError("Missing bundled EJS JavaScript data")
        report["checks"]["ejs_data"] = "passed"

        deno = resolve_external_tool("deno")
        ffmpeg = resolve_external_tool("ffmpeg")
        process_options = dict(check=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               **_hidden_subprocess_kwargs())
        version = subprocess.run([deno, "--version"], **process_options).stdout
        report["deno_version"] = version.splitlines()[0]
        version_parts = tuple(int(part) for part in version.split()[1].split(".")[:3])
        if version_parts < (2, 3, 0):
            raise RuntimeError("Deno 2.3.0 or newer is required")
        report["ffmpeg_version"] = subprocess.run(
            [ffmpeg, "-version"], **process_options).stdout.splitlines()[0]

        with tempfile.TemporaryDirectory(prefix="almiqs-self-test-") as temp:
            folder = Path(temp)
            js_file = folder / "ejs-check.js"
            js_file.write_text(lib + "\nObject.assign(globalThis, lib);\n" + core +
                               '\nif (typeof jsc !== "function") throw new Error("EJS unavailable");\n',
                               encoding="utf-8")
            subprocess.run([deno, "run", "--no-config", "--no-remote", "--no-prompt", str(js_file)],
                           **process_options)
            report["checks"]["deno_ejs_execution"] = "passed"
            sample = folder / "sample.mp4"
            run_ffmpeg_command([
                ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
                "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "ultrafast", "-c:a", "aac", str(sample),
            ], sample)
            output = folder / "clip.mp4"
            cut_clip(sample, output, 1, 1)
            duration = probe_media_duration_seconds(output)
            if not 0.7 <= duration <= 1.5:
                raise RuntimeError(f"Unexpected clipped duration: {duration}")
            report["checks"]["real_ffmpeg_cut"] = "passed"

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        if not window.windowTitle():
            raise RuntimeError("Window has no title")
        window.show()
        app.processEvents()
        window.close()
        app.processEvents()
        report["checks"]["qt_window_startup"] = "passed"
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "passed" else 1
