"""Preview preparation for YouTube URLs, with safe source-identity reuse."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.video_processor import VideoProcessor
from src.youtube_preview_source import cached_youtube_video, remember_youtube_source


def test_youtube_video_cache_tracks_exact_video_not_timestamp(tmp_path: Path):
    mp4 = tmp_path / "input.mp4"
    mp4.write_bytes(b"media" * 1024)
    url = "https://www.youtube.com/watch?v=abcDEF12345"
    assert not cached_youtube_video(mp4, url)
    remember_youtube_source(mp4, url + "&t=20s")
    assert cached_youtube_video(mp4, url)
    assert cached_youtube_video(mp4, "https://youtu.be/abcDEF12345?t=15")
    assert not cached_youtube_video(mp4, "https://youtu.be/otherVid123")
    mp4.unlink()
    assert not cached_youtube_video(mp4, url)


def test_youtube_video_cache_does_not_trust_small_or_missing_files(tmp_path: Path):
    mp4 = tmp_path / "input.mp4"
    mp4.write_bytes(b"short")
    remember_youtube_source(mp4, "https://youtu.be/abcDEF12345")
    assert not cached_youtube_video(mp4, "https://youtu.be/abcDEF12345")
    assert not (tmp_path / ".prepared_youtube_source.json").exists()


def test_youtube_preparation_reuses_matching_video_and_redownloads_new_source(
    tmp_path: Path, monkeypatch
) -> None:
    from src import video_processor
    calls = []

    def fake_download(url, destination, *_args, **_kwargs):
        calls.append(url)
        Path(destination).write_bytes(b"MP4" * 1024)

    monkeypatch.setattr(video_processor, "download_youtube_video", fake_download)
    processor = VideoProcessor(output_root=tmp_path / "output")

    first = processor.prepare_youtube_video(
        "https://www.youtube.com/watch?v=abcDEF12345",
        "مشروع",
    )
    second = processor.prepare_youtube_video(
        "https://youtu.be/abcDEF12345?t=22",
        "مشروع",
    )
    assert second.input_video_path == first.input_video_path
    assert len(calls) == 1

    processor.prepare_youtube_video(
        "https://www.youtube.com/watch?v=otherVid123",
        "مشروع",
    )
    assert len(calls) == 2


@pytest.mark.skipif(not os.environ.get("QT_QPA_PLATFORM"), reason="UI requires offscreen Qt in CI")
def test_reviewing_youtube_without_cache_prompts_for_one_time_download(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    from src.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.youtube_radio.setChecked(True)
    window.project_name_input.setText("تجربة")
    window.youtube_input.setText("https://youtu.be/abcDEF12345")
    window._insert_clip_row(1, "فتوى", "00:01", "00:12")
    requested = []
    monkeypatch.setattr(window, "_offer_youtube_download_for_preview", lambda: requested.append(True))
    window.review_clips_before_cutting()
    assert requested == [True]
    window.close()
    app.processEvents()


@pytest.mark.skipif(not os.environ.get("QT_QPA_PLATFORM"), reason="UI requires offscreen Qt in CI")
def test_preview_worker_emits_succeeded_with_prepared_source(monkeypatch, tmp_path):
    from src.youtube_preview_worker import YoutubePreviewWorker
    result_file = str(tmp_path / "input.mp4")
    class DummyProcessor:
        def prepare_youtube_video(self, url, project_name, progress_callback, **_kwargs):
            assert url == "https://youtu.be/abcDEF12345"
            progress_callback("جاهز")
            return SimpleNamespace(input_video_path=result_file)
    worker = YoutubePreviewWorker(
        DummyProcessor(), url="https://youtu.be/abcDEF12345", project_name="تجربة"
    )
    succeeded, failed, progress, finished = [], [], [], []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)
    worker.progress.connect(progress.append)
    worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert succeeded == [result_file]
    assert failed == []
    assert progress == ["جاهز"]
    assert finished == [True]
