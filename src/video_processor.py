"""Video source preparation and future clipping boundary."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from src.file_utils import ensure_directory, sanitize_filename
from src.models import ClipRequest
from src.time_utils import parse_timestamp
from src.validation import ClipRowInput


INPUT_VIDEO_NAME = "input.mp4"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
REELS_FOLDER_NAME = "ريلز"
BENEFITS_FOLDER_NAME = "فوائد"
LONG_CLIP_THRESHOLD_SECONDS = 180

AR_PREPARING_VIDEO = "جاري تجهيز الفيديو"
AR_DOWNLOADING_YOUTUBE = "جاري تنزيل الفيديو من يوتيوب"
AR_YOUTUBE_DOWNLOADED = "تم تنزيل الفيديو"
AR_LOCAL_VIDEO_COPIED = "تم نسخ الفيديو المحلي"
AR_EMPTY_YOUTUBE_URL = "خطأ: رابط يوتيوب فارغ"
AR_EMPTY_LOCAL_VIDEO = "خطأ: لم يتم اختيار فيديو محلي"
AR_UNSUPPORTED_LOCAL_VIDEO = "خطأ: صيغة الفيديو المحلي غير مدعومة"
AR_LOCAL_VIDEO_NOT_FOUND = "خطأ: ملف الفيديو المحلي غير موجود"
AR_FFMPEG_NOT_FOUND = "لم يتم العثور على ffmpeg"
AR_CUTTING_COMPLETE = "تم الانتهاء من القص والفرز"
AR_INPUT_VIDEO_MISSING = "خطأ: لم يتم العثور على input.mp4"

ProgressCallback = Callable[[str], None]
SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]
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


@dataclass(frozen=True)
class ClipDefinition:
    """Validated clip timing and output naming data."""

    number: int
    title: str
    start_seconds: int
    end_seconds: int

    @property
    def duration_seconds(self) -> int:
        return calculate_clip_duration(self.start_seconds, self.end_seconds)


@dataclass(frozen=True)
class CutClipResult:
    """Result of one completed clip cut."""

    clip: ClipDefinition
    output_path: Path
    destination_folder_name: str


class VideoSourceError(ValueError):
    """Raised when a selected video source cannot be prepared."""


class VideoProcessingError(RuntimeError):
    """Raised when processing cannot continue."""


class FfmpegNotFoundError(VideoProcessingError):
    """Raised when ffmpeg is not available."""


class ClipCutError(VideoProcessingError):
    """Raised when an individual clip cannot be cut."""


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

    def build_clip_definitions(self, rows: list[ClipRowInput]) -> list[ClipDefinition]:
        """Convert validated UI rows into clip definitions."""

        return [build_clip_definition(row) for row in rows]

    def cut_clips(
        self,
        prepared_video: PreparedVideoSource,
        clips: list[ClipDefinition],
        progress_callback: ProgressCallback | None = None,
        runner: SubprocessRunner = subprocess.run,
    ) -> list[CutClipResult]:
        """Cut all clips from the prepared input video and sort them automatically."""

        return cut_clips(prepared_video, clips, progress_callback, runner)

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


def build_clip_definition(row: ClipRowInput) -> ClipDefinition:
    """Build clip timing data from a validated table row."""

    return ClipDefinition(
        number=row.row_number,
        title=row.title.strip(),
        start_seconds=parse_timestamp(row.start),
        end_seconds=parse_timestamp(row.end),
    )


def calculate_clip_duration(start_seconds: int, end_seconds: int) -> int:
    """Return clip duration in seconds."""

    duration = end_seconds - start_seconds
    if duration <= 0:
        raise ValueError("Clip end time must be after start time.")

    return duration


def classify_clip_folder(duration_seconds: int) -> str:
    """Return the Arabic output folder name for a clip duration."""

    if duration_seconds > LONG_CLIP_THRESHOLD_SECONDS:
        return BENEFITS_FOLDER_NAME

    return REELS_FOLDER_NAME


def build_clip_filename(clip: ClipDefinition) -> str:
    """Build a safe output filename that keeps the clip number and title."""

    title = sanitize_filename(clip.title, default="clip")
    return f"{clip.number}_{title}.mp4"


def build_clip_output_path(project_output_folder: str | Path, clip: ClipDefinition) -> Path:
    """Build and create the sorted output path for a clip."""

    destination_folder_name = classify_clip_folder(clip.duration_seconds)
    destination_folder = ensure_directory(Path(project_output_folder) / destination_folder_name)
    return destination_folder / build_clip_filename(clip)


def build_ffmpeg_command(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int,
    duration_seconds: int,
) -> list[str]:
    """Build the ffmpeg command used to cut a clip."""

    return [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-t",
        str(duration_seconds),
        "-i",
        str(input_video_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_video_path),
    ]


def cut_clip(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int,
    duration_seconds: int,
    runner: SubprocessRunner = subprocess.run,
) -> Path:
    """Cut one clip using ffmpeg."""

    input_path = Path(input_video_path)
    if not input_path.is_file():
        raise VideoProcessingError(AR_INPUT_VIDEO_MISSING)

    output_path = Path(output_video_path)
    ensure_directory(output_path.parent)
    command = build_ffmpeg_command(input_path, output_path, start_seconds, duration_seconds)

    try:
        runner(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise FfmpegNotFoundError(AR_FFMPEG_NOT_FOUND) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr or error.stdout or str(error)
        raise ClipCutError(detail.strip()) from error

    return output_path


def cut_clips(
    prepared_video: PreparedVideoSource,
    clips: list[ClipDefinition],
    progress_callback: ProgressCallback | None = None,
    runner: SubprocessRunner = subprocess.run,
) -> list[CutClipResult]:
    """Cut and sort all requested clips."""

    if not prepared_video.input_video_path.is_file():
        raise VideoProcessingError(AR_INPUT_VIDEO_MISSING)

    results: list[CutClipResult] = []
    for clip in clips:
        _emit(progress_callback, f"جاري قص المقطع {clip.number}")
        output_path = build_clip_output_path(prepared_video.project_output_folder, clip)
        destination_folder_name = classify_clip_folder(clip.duration_seconds)

        try:
            cut_clip(
                prepared_video.input_video_path,
                output_path,
                clip.start_seconds,
                clip.duration_seconds,
                runner,
            )
        except FfmpegNotFoundError:
            _emit(progress_callback, f"فشل قص المقطع رقم {clip.number}")
            raise
        except VideoProcessingError as error:
            _emit(progress_callback, f"فشل قص المقطع رقم {clip.number}")
            raise ClipCutError(f"فشل قص المقطع رقم {clip.number}: {error}") from error

        _emit(progress_callback, f"تم قص المقطع {clip.number}")
        _emit(progress_callback, f"تم حفظ المقطع في {destination_folder_name}")
        results.append(
            CutClipResult(
                clip=clip,
                output_path=output_path,
                destination_folder_name=destination_folder_name,
            )
        )

    _emit(progress_callback, AR_CUTTING_COMPLETE)
    return results


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)
