"""Inline video/audio preview and per-clip time correction dialog.

The dialog reads the original local media file; it does not cut, move, or
overwrite the source. Edits stay in memory until the user chooses Save all.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from src.clip_review import ReviewedClip, boundary_warnings, update_clip_bounds
from src.time_utils import format_seconds, parse_timestamp


class ClipReviewDialog(QDialog):
    """Review individual Q&A boundaries with native media playback and seeking."""

    def __init__(
        self,
        video_path: str | Path,
        clips: Sequence[ReviewedClip],
        *,
        initial_index: int = 0,
        source_duration: float | None = None,
        pre_padding: float = 0.0,
        post_padding: float = 0.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not clips:
            raise ValueError("لا توجد مقاطع للمراجعة.")
        if not 0 <= initial_index < len(clips):
            raise IndexError(initial_index)

        self._clips = list(clips)
        self._index = initial_index
        self._source_duration = source_duration
        self._pre_padding = max(0.0, pre_padding)
        self._post_padding = max(0.0, post_padding)
        self._video_path = Path(video_path)

        self.setWindowTitle("مراجعة وضبط المقاطع قبل القص")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(930, 690)
        self.setMinimumWidth(700)
        layout = QVBoxLayout(self)

        self.heading = QLabel()
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(270)
        layout.addWidget(self.video_widget, stretch=1)

        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.85)
        self.media.setAudioOutput(self.audio)
        self.media.setVideoOutput(self.video_widget)
        self.media.setSource(QUrl.fromLocalFile(str(self._video_path.resolve())))

        self.play_button = QPushButton("تشغيل")
        self.listen_start_button = QPushButton("استمع للبداية")
        self.listen_end_button = QPushButton("استمع للنهاية")
        controls = QHBoxLayout()
        for widget in (self.play_button, self.listen_start_button, self.listen_end_button):
            controls.addWidget(widget)
        self.position_label = QLabel("00:00:00")
        controls.addWidget(self.position_label)
        layout.addLayout(controls)

        self.timeline = QSlider(Qt.Horizontal, self)
        self.timeline.setRange(0, max(0, int((source_duration or 0) * 1000)))
        layout.addWidget(self.timeline)

        self.original_label = QLabel()
        self.original_label.setWordWrap(True)
        layout.addWidget(self.original_label)

        steps = QHBoxLayout()
        steps.addWidget(QLabel("مقدار التعديل:"))
        self.step_selector = QComboBox()
        for seconds in (0.1, 0.25, 0.5, 1.0, 2.0):
            self.step_selector.addItem(f"{seconds:g} ثانية", seconds)
        self.step_selector.setCurrentIndex(2)
        steps.addWidget(self.step_selector)
        steps.addStretch()
        layout.addLayout(steps)

        self.start_edit = QLineEdit()
        self.end_edit = QLineEdit()
        self.start_minus_button = QPushButton("−")
        self.start_plus_button = QPushButton("+")
        self.end_minus_button = QPushButton("−")
        self.end_plus_button = QPushButton("+")

        for label, edit, minus, plus in (
            ("بداية المقطع:", self.start_edit, self.start_minus_button, self.start_plus_button),
            ("نهاية جواب الشيخ:", self.end_edit, self.end_minus_button, self.end_plus_button),
        ):
            line = QHBoxLayout()
            line.addWidget(QLabel(label))
            line.addWidget(edit, stretch=1)
            line.addWidget(minus)
            line.addWidget(plus)
            layout.addLayout(line)

        self.duration_label = QLabel()
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.duration_label)
        layout.addWidget(self.warning_label)

        bottom = QHBoxLayout()
        self.previous_button = QPushButton("السابق")
        self.next_button = QPushButton("حفظ والانتقال للتالي")
        self.reset_button = QPushButton("استعادة أوقات Gemini")
        self.save_button = QPushButton("حفظ كل التعديلات")
        self.cancel_button = QPushButton("إلغاء")
        for widget in (
            self.previous_button, self.next_button, self.reset_button,
            self.save_button, self.cancel_button,
        ):
            bottom.addWidget(widget)
        layout.addLayout(bottom)

        self.play_button.clicked.connect(self.toggle_playback)
        self.listen_start_button.clicked.connect(lambda: self.seek_to_boundary("start"))
        self.listen_end_button.clicked.connect(lambda: self.seek_to_boundary("end"))
        self.start_minus_button.clicked.connect(lambda: self.adjust_boundary("start", -self.step()))
        self.start_plus_button.clicked.connect(lambda: self.adjust_boundary("start", self.step()))
        self.end_minus_button.clicked.connect(lambda: self.adjust_boundary("end", -self.step()))
        self.end_plus_button.clicked.connect(lambda: self.adjust_boundary("end", self.step()))
        self.start_edit.textChanged.connect(self._refresh_range_details)
        self.end_edit.textChanged.connect(self._refresh_range_details)
        self.previous_button.clicked.connect(lambda: self.move_to(-1))
        self.next_button.clicked.connect(lambda: self.move_to(1))
        self.reset_button.clicked.connect(self.reset_to_original)
        self.save_button.clicked.connect(self.save_all)
        self.cancel_button.clicked.connect(self.reject)
        self.timeline.sliderReleased.connect(
            lambda: self.media.setPosition(self.timeline.value())
        )
        self.media.positionChanged.connect(self._position_changed)
        self.media.durationChanged.connect(self._duration_changed)
        self.media.playbackStateChanged.connect(self._playback_changed)
        self.media.errorOccurred.connect(self._on_media_error)

        self._load_clip(initial_index)

    @property
    def reviewed_clips(self) -> tuple[ReviewedClip, ...]:
        return tuple(self._clips)

    def step(self) -> float:
        return float(self.step_selector.currentData())

    def adjust_boundary(self, boundary: str, delta: float) -> None:
        if boundary not in {"start", "end"}:
            raise ValueError("Unknown boundary")
        edit = self.start_edit if boundary == "start" else self.end_edit
        try:
            current = parse_timestamp(edit.text().strip())
            new_seconds = max(0.0, round(current + delta, 3))
            if self._source_duration is not None:
                new_seconds = min(new_seconds, self._source_duration)
            edit.setText(format_seconds(new_seconds))
        except ValueError:
            self.warning_label.setText("صحح صيغة الوقت أولًا. مثال: 00:00:37.500")

    def reset_to_original(self) -> None:
        clip = self._clips[self._index]
        self.start_edit.setText(clip.original_start or clip.start)
        self.end_edit.setText(clip.original_end or clip.end)

    def toggle_playback(self) -> None:
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media.pause()
        else:
            self.media.play()

    def seek_to_boundary(self, boundary: str) -> None:
        """Play the source on both sides of a boundary, not a cropped preview."""
        try:
            timestamp = parse_timestamp(
                self.start_edit.text() if boundary == "start" else self.end_edit.text()
            )
        except ValueError:
            self.warning_label.setText("صيغة التوقيت غير صحيحة.")
            return
        context = 5 if boundary == "start" else 12
        self.media.setPosition(int(max(0, timestamp - context) * 1000))
        self.media.play()

    def move_to(self, delta: int) -> bool:
        if not self._commit_current():
            return False
        next_index = self._index + delta
        if not 0 <= next_index < len(self._clips):
            return False
        self._load_clip(next_index)
        return True

    def save_all(self) -> bool:
        if not self._commit_current():
            return False
        self.accept()
        return True

    def _commit_current(self) -> bool:
        try:
            adjusted = update_clip_bounds(
                self._clips[self._index],
                self.start_edit.text().strip(),
                self.end_edit.text().strip(),
                source_duration=self._source_duration,
            )
        except ValueError as error:
            QMessageBox.warning(self, "توقيت غير صحيح", str(error))
            return False

        warning_messages = boundary_warnings(
            self._clips,
            self._index,
            adjusted.start,
            adjusted.end,
            pre_padding=self._pre_padding,
            post_padding=self._post_padding,
        )
        if warning_messages:
            answer = QMessageBox.question(
                self,
                "تداخل مع مقطع آخر",
                "\n".join(warning_messages) +
                "\n\nقد يكون التداخل مقصودًا، هل تريد اعتماد الأوقات رغم ذلك؟",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False

        self._clips[self._index] = adjusted
        return True

    def _load_clip(self, index: int) -> None:
        self.media.pause()
        self._index = index
        clip = self._clips[index]
        self.heading.setText(f"المقطع {index + 1} من {len(self._clips)} — {clip.title}")
        self.original_label.setText(
            f"التوقيت الأصلي: {clip.original_start or clip.start}"
            f" ← {clip.original_end or clip.end}"
        )
        self.start_edit.setText(clip.start)
        self.end_edit.setText(clip.end)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < len(self._clips))
        self.media.setPosition(max(0, int((parse_timestamp(clip.start) - 3) * 1000)))
        self._refresh_range_details()

    def _refresh_range_details(self, *_args) -> None:
        try:
            start = parse_timestamp(self.start_edit.text().strip())
            end = parse_timestamp(self.end_edit.text().strip())
            self.duration_label.setText(
                f"مدة المقطع بعد التعديل: {end - start:.3f} ثانية"
            )
            errors: list[str] = []
            if end <= start:
                errors.append("نهاية المقطع يجب أن تكون بعد البداية.")
            if self._source_duration is not None and end > self._source_duration + 0.001:
                errors.append("النهاية تتجاوز مدة الفيديو.")
            if end > start:
                errors.extend(boundary_warnings(
                    self._clips, self._index,
                    self.start_edit.text(), self.end_edit.text(),
                    pre_padding=self._pre_padding,
                    post_padding=self._post_padding,
                ))
            self.warning_label.setText("\n".join(errors))
        except ValueError:
            self.duration_label.setText("أدخل وقتًا صحيحًا بصيغة HH:MM:SS.mmm")
            self.warning_label.setText("")

    def _position_changed(self, value: int) -> None:
        self.position_label.setText(format_seconds(value / 1000))
        if not self.timeline.isSliderDown():
            self.timeline.setValue(value)

    def _duration_changed(self, value: int) -> None:
        self.timeline.setMaximum(value)
        if self._source_duration is None and value > 0:
            self._source_duration = value / 1000

    def _playback_changed(self, state) -> None:
        self.play_button.setText(
            "إيقاف مؤقت" if state == QMediaPlayer.PlaybackState.PlayingState else "تشغيل"
        )

    def _on_media_error(self, _error, message: str) -> None:
        if message:
            self.warning_label.setText(
                "تعذر تشغيل المعاينة داخل البرنامج: " + message
            )

    def done(self, result: int) -> None:
        self.media.stop()
        self.media.setSource(QUrl())
        super().done(result)
