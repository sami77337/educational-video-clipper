"""Video source preparation and future clipping boundary."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from src.file_utils import ensure_directory, sanitize_filename
from src.models import ClipRequest


INPUT_VIDEO_NAME = "input.mp4"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}

AR_PREPARING_VIDEO = "جاري تجهيز الفيديو"
AR_DOWNLOADING_YOUTUBE = "جاري تنزيل الفيديو من يوتيوب"
AR_YOUTUBE_DOWNLOADED = "تم تنزيل الفيديو"
AR_LOCAL_VIDEO_COPIED = "تم نسخ الفيديو المحلي"
AR_EMPTY_YOUTUBE_URL = "خطأ: رابط يوتيوب فارغ"
AR_EMPTY_LOCAL_VIDEO = "خطأ: لم يتم اختيار فيديو محلي"
AR_UNSUPPORTED_LOCAL_VIDEO = "خطأ: صيغة الفيديو المحلي غير مدعومة"
AR_LOCAL_VIDEO_NOT_FOUND = "خطأ: ملف الفيديو المحلي غير موجود"

ProgressCallback = Callable[[str], None]
YoutubeDlFactory = Callable[[dict[str, Any]], Any]


class VideoSourceType(Enum):
    """Supported video source choices."""

    YOUTUBE = "youtube"
    LOCAL_FILE = "local_file"


@dataclass(frozen=True)
class VideoSourceRequest:
    """Input chosen by the user."""

    source_type: VideoSourceType
    value: str


@dataclass(frozen=True)
class PreparedVideoSource:
    """Prepared source video ready for future clipping."""

    source_type: VideoSourceType
    project_output_folder: Path
    input_video_path: Path


class VideoSourceError(ValueError):
    """Raised when a selected video source cannot be prepared."""


class VideoProcessor:
    """Service for preparing videos before future clipping integration."""

    def __init__(
        self,
        output_root: str | Path | None = None,
        youtube_dl_factory: YoutubeDlFactory = YoutubeDL,
    ) -> None:
        self.output_root = Path(output_root) if output_root is not None else Path.cwd() / "output"
        self._youtube_dl_factory = youtube_dl_factory

    def get_project_output_folder(self, project_name: str) -> Path:
        """Create and return the sanitized output folder for a project."""

        return create_project_output_folder(project_name, self.output_root)

    def prepare_source(
        self,
        request: VideoSourceRequest,
        project_name: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedVideoSource:
        """Prepare the selected source video as input.mp4."""

        if request.source_type is VideoSourceType.YOUTUBE:
            return self.prepare_youtube_video(request.value, project_name, progress_callback)

        if request.source_type is VideoSourceType.LOCAL_FILE:
            return self.prepare_local_video(request.value, project_name, progress_callback)

        raise VideoSourceError("خطأ: مصدر الفيديو غير معروف")

    def prepare_youtube_video(
        self,
        url: str,
        project_name: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedVideoSource:
        """Download a YouTube video into the project folder as input.mp4."""

        clean_url = validate_youtube_url(url)
        project_output_folder = self.get_project_output_folder(project_name)
        input_video_path = project_output_folder / INPUT_VIDEO_NAME

        _emit(progress_callback, AR_DOWNLOADING_YOUTUBE)
        download_youtube_video(clean_url, input_video_path, self._youtube_dl_factory)
        _emit(progress_callback, AR_YOUTUBE_DOWNLOADED)

        return PreparedVideoSource(
            source_type=VideoSourceType.YOUTUBE,
            project_output_folder=project_output_folder,
            input_video_path=input_video_path,
        )

    def prepare_local_video(
        self,
        file_path: str,
        project_name: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedVideoSource:
        """Copy a local video into the project folder as input.mp4."""

        source_path = validate_local_video_file(file_path)
        project_output_folder = self.get_project_output_folder(project_name)
        input_video_path = project_output_folder / INPUT_VIDEO_NAME

        if source_path.resolve() != input_video_path.resolve():
            shutil.copy2(source_path, input_video_path)

        _emit(progress_callback, AR_LOCAL_VIDEO_COPIED)

        return PreparedVideoSource(
            source_type=VideoSourceType.LOCAL_FILE,
            project_output_folder=project_output_folder,
            input_video_path=input_video_path,
        )

    def create_clip(self, request: ClipRequest) -> None:
        raise NotImplementedError("Video clipping is not implemented yet.")


def create_project_output_folder(project_name: str, output_root: str | Path) -> Path:
    """Create a project folder using a Windows-safe version of the project name."""

    folder_name = sanitize_filename(project_name, default="project")
    return ensure_directory(Path(output_root) / folder_name)


def validate_youtube_url(url: str | None) -> str:
    """Validate that a YouTube URL was provided."""

    if url is None or not url.strip():
        raise VideoSourceError(AR_EMPTY_YOUTUBE_URL)

    return url.strip()


def validate_local_video_file(file_path: str | Path | None) -> Path:
    """Validate a selected local video path and return it as a Path."""

    if file_path is None or not str(file_path).strip():
        raise VideoSourceError(AR_EMPTY_LOCAL_VIDEO)

    path = Path(str(file_path).strip())
    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise VideoSourceError(f"{AR_UNSUPPORTED_LOCAL_VIDEO}: {allowed}")

    if not path.is_file():
        raise VideoSourceError(AR_LOCAL_VIDEO_NOT_FOUND)

    return path


def download_youtube_video(
    url: str,
    destination: str | Path,
    youtube_dl_factory: YoutubeDlFactory = YoutubeDL,
) -> Path:
    """Download a YouTube video to the given destination using yt-dlp's Python API."""

    destination_path = Path(destination)
    ensure_directory(destination_path.parent)

    options = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "outtmpl": str(destination_path),
        "overwrites": True,
        "quiet": True,
        "no_warnings": True,
    }

    with youtube_dl_factory(options) as ydl:
        ydl.download([url])

    return destination_path


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)
