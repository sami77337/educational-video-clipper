"""Background authorized YouTube preparation for inline Q&A media review."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from src.video_processor import VideoProcessor


class YoutubePreviewWorker(QObject):
    progress = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        processor: VideoProcessor,
        *,
        url: str,
        project_name: str,
        use_browser_cookies: bool = False,
        browser: str = "chrome",
    ) -> None:
        super().__init__()
        self.processor = processor
        self.url = url
        self.project_name = project_name
        self.use_browser_cookies = use_browser_cookies
        self.browser = browser

    @Slot()
    def run(self) -> None:
        try:
            prepared = self.processor.prepare_youtube_video(
                self.url,
                self.project_name,
                self.progress.emit,
                use_browser_cookies=self.use_browser_cookies,
                browser=self.browser,
            )
        except Exception as error:
            self.failed.emit(f"تعذر تجهيز الفيديو للمعاينة: {error}")
        else:
            self.succeeded.emit(str(prepared.input_video_path))
        finally:
            self.finished.emit()
