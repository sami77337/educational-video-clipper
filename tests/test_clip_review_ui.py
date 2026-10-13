"""Offscreen Qt regression for local media review and non-destructive edits."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from src.clip_review import ReviewedClip, update_clip_bounds
from src.main_window import END_COLUMN, START_COLUMN, MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_clip_review_dialog_adjusts_half_second_and_preserves_original(tmp_path: Path):
    app = _app()
    from src.clip_review_dialog import ClipReviewDialog

    media = tmp_path / "example.mp4"
    media.write_bytes(b"not a real video (UI construction only)")
    clips = [ReviewedClip(
        number=1, title="حكم الجمع",
        start="00:04", end="00:11",
        original_start="00:04", original_end="00:11",
    )]
    dialog = ClipReviewDialog(media, clips, source_duration=25)
    assert dialog.heading.text().startswith("المقطع 1 من 1")
    assert dialog.step() == 0.5
    dialog.adjust_boundary("end", 0.5)
    assert dialog.end_edit.text() == "00:00:11.500"
    assert dialog.save_all()
    assert dialog.result() == QDialog.Accepted
    edited = dialog.reviewed_clips[0]
    assert edited.end == "00:00:11.500"
    assert edited.original_end == "00:11"
    dialog.close()
    app.processEvents()


def test_review_main_window_applies_saved_time_and_provenance(monkeypatch, tmp_path: Path):
    app = _app()
    from src import clip_review_dialog
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"fake (not decoded by fake review dialog)")
    window = MainWindow()
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(source))
    window._insert_clip_row(
        1, "هل يجوز الجمع؟", "00:19", "00:37.500",
        original_start="00:19", original_end="00:37.500",
    )
    monkeypatch.setattr(window, "_preview_video_duration", lambda *_args: 60.0)
    class FakeReview:
        def __init__(self, _path, clips, **_kwargs):
            self.reviewed_clips = [
                update_clip_bounds(clips[0], clips[0].start, "00:38"),
            ]
        def exec(self):
            return QDialog.Accepted
    monkeypatch.setattr(clip_review_dialog, "ClipReviewDialog", FakeReview)
    window.review_clips_before_cutting()
    assert window.clips_table.item(0, START_COLUMN).text() == "00:00:19"
    assert window.clips_table.item(0, END_COLUMN).text() == "00:00:38"
    assert window._original_clip_time(0, END_COLUMN) == "00:37.500"
    job = window._clip_jobs_from_current_table()[0]
    assert job.end == "00:00:38"
    assert job.original_end == "00:37.500"
    row = window._collect_clip_rows()[0]
    assert row.original_end == "00:37.500"
    window.close()
    app.processEvents()


def test_review_main_window_cancel_discards_all_changes(monkeypatch, tmp_path: Path):
    app = _app()
    from src import clip_review_dialog
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"fake")
    window = MainWindow()
    window.local_file_radio.setChecked(True)
    window.local_file_input.setText(str(source))
    window._insert_clip_row(
        1, "سؤال", "00:19", "00:37.500",
        original_start="00:19", original_end="00:37.500",
    )
    monkeypatch.setattr(window, "_preview_video_duration", lambda *_args: 60.0)
    class FakeCancelledReview:
        def __init__(self, _path, clips, **_kwargs):
            self.reviewed_clips = [
                update_clip_bounds(clips[0], clips[0].start, "00:45"),
            ]
        def exec(self):
            return QDialog.Rejected
    monkeypatch.setattr(clip_review_dialog, "ClipReviewDialog", FakeCancelledReview)
    window.review_clips_before_cutting()
    assert window.clips_table.item(0, END_COLUMN).text() == "00:37.500"
    window.close()
    app.processEvents()


def test_queued_clip_review_provenance_round_trip():
    import json
    from src.job_queue import ClipJob, JobSettings, VideoJob, VideoSourceType
    from src.job_queue_storage import queue_jobs_to_json, queue_jobs_from_data

    job = VideoJob(
        source_type=VideoSourceType.LOCAL,
        source="D:/media/lesson.mp4",
        title="فتاوى",
        settings=JobSettings(create_handoff_package=True),
        clips=[
            ClipJob(
                title="ما الحكم؟",
                start="00:19",
                end="00:38",
                original_start="00:19",
                original_end="00:37.500",
            ),
        ],
    )
    restored = queue_jobs_from_data(json.loads(queue_jobs_to_json([job])))[0]
    assert restored.clips[0].original_end == "00:37.500"
    assert restored.clips[0].end == "00:38"
