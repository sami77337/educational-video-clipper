"""Bounded public YouTube test, with no credentials and normal TLS checks."""
import json
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.video.youtube_downloader import download_youtube_video
from src.video.ffmpeg_runner import probe_media_duration_seconds
from yt_dlp.version import __version__

report = {"status": "inconclusive", "yt_dlp_version": __version__,
          "url": "https://www.youtube.com/watch?v=BaW_jenozKc"}
try:
    target = download_youtube_video(report["url"], "smoke-output/input.mp4", progress_callback=print)
    report.update(status="passed", bytes=target.stat().st_size,
                  duration_seconds=probe_media_duration_seconds(target))
except Exception as error:
    report["error_type"] = type(error).__name__
    report["error"] = str(error)
    traceback.print_exc()
finally:
    Path("youtube-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
