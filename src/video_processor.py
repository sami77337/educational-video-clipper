"""Video source preparation and future clipping boundary."""

from __future__ import annotations

import shutil
import subprocess
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from src.classification import (
    ClassificationRule,
    ClassificationRuleError,
    classification_folder_names,
    classify_duration,
    format_classification_errors_ar,
    get_default_classification_rules,
    validate_classification_rules,
)
from src.clip_padding import ClipPadding, calculate_effective_clip_range
from src.export_utils import (
    AR_PROCESSING_SUCCESS,
    AR_REPORT_CREATED,
    BENEFITS_FOLDER_NAME,
    ExportArtifacts,
    ProcessingReportData,
    ProcessingReportClipData,
    REELS_FOLDER_NAME,
    create_result_zips,
    ensure_result_folders,
    write_processing_report,
)
from src.exclusions import (
    ExclusionError,
    calculate_kept_segments,
    format_exclusions,
    validate_exclusions,
)
from src.file_utils import ensure_directory, sanitize_filename
from src.models import ClipRequest
from src.time_utils import format_seconds, parse_timestamp
from src.validation import ClipRowInput
from src.video.ffmpeg_commands import build_ffmpeg_command, build_ffmpeg_concat_command
from src.video import ffmpeg_runner as _ffmpeg_runner
from src.video import youtube_downloader as _youtube_downloader
from src.video.ffmpeg_runner import (
    AR_FFMPEG_NOT_FOUND,
    FfmpegRunnerError,
    MIN_OUTPUT_BYTES,
    OUTPUT_DURATION_TOLERANCE_SECONDS,
    bundled_ffmpeg_location,
    resolve_external_tool,
    _candidate_tool_roots,
    _combined_process_output,
    _concise_ffmpeg_error,
    _hidden_subprocess_kwargs,
    _output_file_is_usable,
    _resolve_command_for_real_execution,
    _should_validate_media_duration,
)
from src.video.youtube_downloader import (
    AR_BROWSER_COOKIES_FAILED,
    AR_EMPTY_YOUTUBE_URL,
    AR_USING_BROWSER_COOKIES,
    AR_YOUTUBE_DOWNLOAD_FINISHING,
    AR_YOUTUBE_DOWNLOAD_PROGRESS,
    AR_YOUTUBE_READING_INFO,
    YouTubeDownloadError,
    YoutubeDL,
    YoutubeDlFactory,
    _build_youtube_progress_hook,
    normalize_browser_name,
)


INPUT_VIDEO_NAME = "input.mp4"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
LONG_CLIP_THRESHOLD_SECONDS = 180
DEFAULT_PROJECT_FOLDER_NAME = "مشروع-بدون-اسم"
MAX_PROJECT_FOLDER_NAME_LENGTH = 80

AR_PREPARING_VIDEO = "جاري تجهيز الفيديو"
AR_DOWNLOADING_YOUTUBE = "جاري تنزيل الفيديو من يوتيوب"
AR_YOUTUBE_DOWNLOADED = "تم تنزيل الفيديو"
AR_LOCAL_VIDEO_COPIED = "تم نسخ الفيديو المحلي"
AR_EMPTY_LOCAL_VIDEO = "خطأ: لم يتم اختيار فيديو محلي"
AR_UNSUPPORTED_LOCAL_VIDEO = "خطأ: صيغة الفيديو المحلي غير مدعومة"
AR_LOCAL_VIDEO_NOT_FOUND = "خطأ: ملف الفيديو المحلي غير موجود"
AR_CUTTING_COMPLETE = "تم الانتهاء من القص والفرز"
AR_INPUT_VIDEO_MISSING = "خطأ: لم يتم العثور على input.mp4"
AR_CLASSIFICATION_RULES_INVALID = "خطأ في قواعد التصنيف"
AR_NO_CLASSIFICATION_RULE_FOR_CLIP = "لا توجد قاعدة تصنيف مناسبة للمقطع رقم"
AR_EXCLUSIONS_INVALID = "خطأ في الاستثناءات"
AR_CHECKING_EXCLUSIONS = "جاري فحص الاستثناءات"
AR_CUTTING_EXCLUDED_PARTS = "جاري حذف الأجزاء المستثناة من المقطع"
AR_MERGED_CLIP_PARTS = "تم دمج أجزاء المقطع"
AR_NO_EXCLUSIONS_FOR_CLIP = "لا توجد استثناءات للمقطع"
AR_CUT_WITHOUT_EXCLUSIONS = "تم قص المقطع بدون استثناءات"
AR_CONCAT_FAILED = "فشل دمج أجزاء المقطع رقم"
AR_PROJECT_NAME_CLEANED = "تم تنظيف اسم المشروع ليكون مناسبًا للمجلدات"
AR_CLIP_PADDING_APPLIED = "تم تطبيق وقت إضافي قبل/بعد القص"
AR_MULTIPLE_EXCLUSIONS_APPLIED = "تم تطبيق أكثر من استثناء داخل المقطع"
TEMP_SEGMENTS_FOLDER_NAME = "_temp_segments"
ProgressCallback = Callable[[str], None]
SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


class VideoSourceType(Enum):
    """Supported video source choices."""

    YOUTUBE = "youtube"
    LOCAL_FILE = "local_file"


@dataclass(frozen=True)
class VideoSourceRequest:
    """Input chosen by the user."""

    source_type: VideoSourceType
    value: str
    use_browser_cookies: bool = False
    browser: str = "chrome"


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
    exclusions: str = ""

    @property
    def duration_seconds(self) -> int:
        return calculate_clip_duration(self.start_seconds, self.end_seconds)

    @property
    def start_timestamp(self) -> str:
        return format_seconds(self.start_seconds)

    @property
    def end_timestamp(self) -> str:
        return format_seconds(self.end_seconds)

    @property
    def normalized_exclusions(self) -> str:
        return format_exclusions(self.exclusions)


@dataclass(frozen=True)
class CutClipResult:
    """Result of one completed clip cut."""

    clip: ClipDefinition
    output_path: Path
    destination_folder_name: str


@dataclass(frozen=True)
class ProcessingResult:
    """Final result of a successful processing run."""

    project_output_folder: Path
    prepared_video: PreparedVideoSource
    cut_results: list[CutClipResult]
    export_artifacts: ExportArtifacts


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
        classification_rules: Sequence[ClassificationRule] | None = None,
    ) -> None:
        self.output_root = Path(output_root) if output_root is not None else Path.cwd() / "output"
        self._youtube_dl_factory = youtube_dl_factory
        self.classification_rules = None if classification_rules is None else list(classification_rules)

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
            return self.prepare_youtube_video(
                request.value,
                project_name,
                progress_callback,
                use_browser_cookies=request.use_browser_cookies,
                browser=request.browser,
            )

        if request.source_type is VideoSourceType.LOCAL_FILE:
            return self.prepare_local_video(request.value, project_name, progress_callback)

        raise VideoSourceError("خطأ: مصدر الفيديو غير معروف")

    def prepare_youtube_video(
        self,
        url: str,
        project_name: str,
        progress_callback: ProgressCallback | None = None,
        *,
        use_browser_cookies: bool = False,
        browser: str = "chrome",
    ) -> PreparedVideoSource:
        """Download a YouTube video into the project folder as input.mp4."""

        clean_url = validate_youtube_url(url)
        _emit_project_name_cleanup(project_name, progress_callback)
        project_output_folder = self.get_project_output_folder(project_name)
        input_video_path = project_output_folder / INPUT_VIDEO_NAME

        _emit(progress_callback, AR_DOWNLOADING_YOUTUBE)
        download_youtube_video(
            clean_url,
            input_video_path,
            self._youtube_dl_factory,
            progress_callback,
            use_browser_cookies=use_browser_cookies,
            browser=browser,
        )
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
        _emit_project_name_cleanup(project_name, progress_callback)
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
        classification_rules: Sequence[ClassificationRule] | None = None,
        clip_padding: ClipPadding | None = None,
        video_duration_seconds: float | None = None,
    ) -> list[CutClipResult]:
        """Cut all clips from the prepared input video and sort them automatically."""

        active_rules = self._active_classification_rules(classification_rules)
        return cut_clips(
            prepared_video,
            clips,
            progress_callback,
            runner,
            active_rules,
            clip_padding,
            video_duration_seconds,
        )

    def process_project(
        self,
        source_request: VideoSourceRequest,
        project_name: str,
        clip_rows: list[ClipRowInput],
        progress_callback: ProgressCallback | None = None,
        runner: SubprocessRunner = subprocess.run,
        classification_rules: Sequence[ClassificationRule] | None = None,
        clip_padding: ClipPadding | None = None,
    ) -> ProcessingResult:
        """Prepare, cut, sort, ZIP, and report one project."""

        started_at = datetime.now().astimezone()
        active_rules = self._active_classification_rules(classification_rules)
        active_padding = clip_padding or ClipPadding()
        clips = self.build_clip_definitions(clip_rows)
        exclusion_errors = validate_exclusions_for_clips(clips, active_padding)
        if exclusion_errors:
            raise VideoProcessingError(f"{AR_EXCLUSIONS_INVALID}:\n" + "\n".join(exclusion_errors))

        classification_errors = validate_classification_rules_for_clips(clips, active_rules)
        if classification_errors:
            raise VideoProcessingError(f"{AR_CLASSIFICATION_RULES_INVALID}:\n" + "\n".join(classification_errors))

        _emit(progress_callback, AR_PREPARING_VIDEO)
        prepared_video = self.prepare_source(source_request, project_name, progress_callback)
        video_duration_seconds = _probe_video_duration_if_needed(prepared_video.input_video_path, active_padding)
        cut_results = self.cut_clips(
            prepared_video,
            clips,
            progress_callback,
            runner,
            active_rules,
            active_padding,
            video_duration_seconds,
        )
        export_artifacts = self.export_results(
            project_output_folder=prepared_video.project_output_folder,
            project_name=project_name,
            source_type=source_request.source_type,
            cut_results=cut_results,
            started_at=started_at,
            ended_at=None,
            progress_callback=progress_callback,
            classification_rules=active_rules,
        )
        _emit(progress_callback, AR_PROCESSING_SUCCESS)

        return ProcessingResult(
            project_output_folder=prepared_video.project_output_folder,
            prepared_video=prepared_video,
            cut_results=cut_results,
            export_artifacts=export_artifacts,
        )

    def export_results(
        self,
        project_output_folder: str | Path,
        project_name: str,
        source_type: VideoSourceType,
        cut_results: list[CutClipResult],
        started_at: datetime,
        ended_at: datetime | None,
        progress_callback: ProgressCallback | None = None,
        classification_rules: Sequence[ClassificationRule] | None = None,
    ) -> ExportArtifacts:
        """Create ZIP files and a final report after successful clipping."""

        project_folder = Path(project_output_folder)
        active_rules = self._active_classification_rules(classification_rules)
        folder_names = classification_folder_names(active_rules)
        output_folders = list(ensure_result_folders(project_folder, folder_names))
        zip_result = create_result_zips(project_folder, progress_callback, folder_names)
        clip_counts = count_results_by_folder(cut_results, folder_names)
        report_data = ProcessingReportData(
            project_name=project_name,
            source_type=source_type_label(source_type),
            total_clips_count=len(cut_results),
            reels_count=clip_counts.get(REELS_FOLDER_NAME, 0),
            benefits_count=clip_counts.get(BENEFITS_FOLDER_NAME, 0),
            output_folders=output_folders,
            zip_files=zip_result.zip_files,
            started_at=started_at,
            ended_at=ended_at or datetime.now().astimezone(),
            skipped_or_failed_items=[],
            classification_rules=list(active_rules),
            clip_counts_by_folder=clip_counts,
            clip_details=build_report_clip_details(cut_results),
        )
        report_path = write_processing_report(project_folder, report_data)
        _emit(progress_callback, AR_REPORT_CREATED)

        return ExportArtifacts(
            zip_folder=zip_result.zip_folder,
            zip_files=zip_result.zip_files,
            report_path=report_path,
        )

    def create_clip(self, request: ClipRequest) -> None:
        raise NotImplementedError("Video clipping is not implemented yet.")

    def _active_classification_rules(
        self,
        rules: Sequence[ClassificationRule] | None = None,
    ) -> list[ClassificationRule]:
        if rules is not None:
            return list(rules)
        if self.classification_rules is not None:
            return list(self.classification_rules)
        return get_default_classification_rules()


def create_project_output_folder(project_name: str, output_root: str | Path) -> Path:
    """Create a project folder using a Windows-safe version of the project name."""

    folder_name = sanitize_project_name(project_name)
    return ensure_directory(Path(output_root) / folder_name)


def sanitize_project_name(project_name: str | None) -> str:
    """Return a Windows-safe project output folder name."""

    return sanitize_filename(
        project_name,
        default=DEFAULT_PROJECT_FOLDER_NAME,
        max_length=MAX_PROJECT_FOLDER_NAME_LENGTH,
    )


def project_name_was_cleaned(project_name: str | None) -> bool:
    """Return True when the project folder name differs from the entered name."""

    original = "" if project_name is None else str(project_name)
    comparable_original = original.strip(" .-")
    return sanitize_project_name(project_name) != comparable_original


def validate_youtube_url(url: str | None) -> str:
    """Validate that a YouTube URL was provided."""

    try:
        return _youtube_downloader.validate_youtube_url(url)
    except YouTubeDownloadError as error:
        raise VideoSourceError(str(error)) from error


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
    progress_callback: ProgressCallback | None = None,
    *,
    use_browser_cookies: bool = False,
    browser: str = "chrome",
) -> Path:
    """Download a YouTube video through the extracted downloader."""

    try:
        return _youtube_downloader.download_youtube_video(
            url,
            destination,
            youtube_dl_factory,
            progress_callback,
            use_browser_cookies=use_browser_cookies,
            browser=browser,
            ffmpeg_location_provider=bundled_ffmpeg_location,
        )
    except YouTubeDownloadError as error:
        raise VideoSourceError(str(error)) from error


def build_clip_definition(row: ClipRowInput) -> ClipDefinition:
    """Build clip timing data from a validated table row."""

    return ClipDefinition(
        number=row.row_number,
        title=row.title.strip(),
        start_seconds=parse_timestamp(row.start),
        end_seconds=parse_timestamp(row.end),
        exclusions=row.exclusions.strip() if row.exclusions else "",
    )


def calculate_clip_duration(start_seconds: int, end_seconds: int) -> int:
    """Return clip duration in seconds."""

    duration = end_seconds - start_seconds
    if duration <= 0:
        raise ValueError("Clip end time must be after start time.")

    return duration


def classify_clip_folder(
    duration_seconds: int,
    rules: Sequence[ClassificationRule] | None = None,
) -> str:
    """Return the output folder name for a clip duration."""

    active_rules = get_default_classification_rules() if rules is None else rules
    return classify_duration(duration_seconds, active_rules)


def source_type_label(source_type: VideoSourceType) -> str:
    """Return the report label for the selected source type."""

    if source_type is VideoSourceType.YOUTUBE:
        return "YouTube"

    return "local file"


def count_results_in_folder(results: list[CutClipResult], folder_name: str) -> int:
    """Count cut results saved in a sorted folder."""

    return sum(1 for result in results if result.destination_folder_name == folder_name)


def count_results_by_folder(
    results: list[CutClipResult],
    folder_names: Sequence[str],
) -> dict[str, int]:
    """Count cut results for each configured output folder."""

    counts = {folder_name: 0 for folder_name in folder_names}
    for result in results:
        counts[result.destination_folder_name] = counts.get(result.destination_folder_name, 0) + 1

    return counts


def validate_classification_rules_for_clips(
    clips: Sequence[ClipDefinition],
    rules: Sequence[ClassificationRule],
) -> list[str]:
    """Validate rules and ensure every clip can be classified."""

    errors = format_classification_errors_ar(validate_classification_rules(rules))
    if errors:
        return errors

    for clip in clips:
        try:
            classify_clip_folder(clip.duration_seconds, rules)
        except ClassificationRuleError:
            errors.append(f"{AR_NO_CLASSIFICATION_RULE_FOR_CLIP} {clip.number}")

    return errors


def validate_exclusions_for_clips(
    clips: Sequence[ClipDefinition],
    clip_padding: ClipPadding | None = None,
    video_duration_seconds: float | None = None,
) -> list[str]:
    """Validate clip exclusions before any ffmpeg work starts."""

    active_padding = clip_padding or ClipPadding()
    errors: list[str] = []
    for clip in clips:
        if not clip.exclusions.strip():
            continue
        try:
            validation_start = clip.start_timestamp
            validation_end = clip.end_timestamp
            if active_padding.has_padding:
                effective_range = calculate_effective_clip_range(
                    clip.start_seconds,
                    clip.end_seconds,
                    active_padding,
                    video_duration_seconds,
                )
                validation_start = format_seconds(max(0, math.floor(effective_range.start_seconds)))
                validation_end = format_seconds(math.ceil(effective_range.end_seconds))

            exclusion_errors = validate_exclusions(validation_start, validation_end, clip.exclusions)
        except (ExclusionError, ValueError) as error:
            exclusion_errors = [str(error)]
        errors.extend(f"{error} في المقطع رقم {clip.number}" for error in exclusion_errors)

    return errors


def build_report_clip_details(results: Sequence[CutClipResult]) -> list[ProcessingReportClipData]:
    """Build final report rows for processed clips."""

    return [
        ProcessingReportClipData(
            number=result.clip.number,
            title=result.clip.title,
            start=result.clip.start_timestamp,
            end=result.clip.end_timestamp,
            exclusions=result.clip.normalized_exclusions,
            folder_name=result.destination_folder_name,
        )
        for result in results
    ]


def build_clip_filename(clip: ClipDefinition) -> str:
    """Build a safe output filename that keeps the clip number and title."""

    title = sanitize_filename(clip.title, default="clip")
    return f"{clip.number}_{title}.mp4"


def build_clip_output_path(
    project_output_folder: str | Path,
    clip: ClipDefinition,
    classification_rules: Sequence[ClassificationRule] | None = None,
    destination_folder_name: str | None = None,
) -> Path:
    """Build and create the sorted output path for a clip."""

    destination_folder_name = destination_folder_name or classify_clip_folder(
        clip.duration_seconds,
        classification_rules,
    )
    destination_folder = ensure_directory(Path(project_output_folder) / destination_folder_name)
    return destination_folder / build_clip_filename(clip)


def _run_ffmpeg_command(
    command: list[str],
    output_path: str | Path,
    runner: SubprocessRunner = subprocess.run,
) -> subprocess.CompletedProcess[str] | None:
    """Run ffmpeg through the extracted runner and preserve local errors."""

    try:
        return _ffmpeg_runner.run_ffmpeg_command(
            command,
            output_path,
            runner,
            should_validate_media_duration=_should_validate_media_duration,
        )
    except FfmpegRunnerError as error:
        raise ClipCutError(str(error)) from error


def probe_media_duration_seconds(path: str | Path) -> float:
    """Read media duration through the extracted runner and preserve local errors."""

    try:
        return _ffmpeg_runner.probe_media_duration_seconds(path)
    except FfmpegRunnerError as error:
        raise ClipCutError(str(error)) from error


def verify_output_duration(
    output_path: str | Path,
    expected_duration_seconds: int | float,
    *,
    tolerance_seconds: float = OUTPUT_DURATION_TOLERANCE_SECONDS,
) -> None:
    """Ensure the resulting clip duration is close to the requested duration."""

    try:
        _ffmpeg_runner.verify_output_duration(
            output_path,
            expected_duration_seconds,
            tolerance_seconds=tolerance_seconds,
            probe_duration=probe_media_duration_seconds,
        )
    except FfmpegRunnerError as error:
        raise ClipCutError(str(error)) from error


def cut_clip(
    input_video_path: str | Path,
    output_video_path: str | Path,
    start_seconds: int | float,
    duration_seconds: int | float,
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
        _run_ffmpeg_command(command, output_path, runner)
        if _should_validate_media_duration(runner):
            verify_output_duration(output_path, duration_seconds)
    except FileNotFoundError as error:
        raise FfmpegNotFoundError(AR_FFMPEG_NOT_FOUND) from error

    return output_path


def cut_clip_with_exclusions(
    input_video_path: str | Path,
    output_video_path: str | Path,
    clip: ClipDefinition,
    temp_root: str | Path,
    progress_callback: ProgressCallback | None = None,
    runner: SubprocessRunner = subprocess.run,
    effective_start_seconds: int | float | None = None,
    effective_end_seconds: int | float | None = None,
) -> Path:
    """Cut kept segments for a clip with exclusions and merge them into one mp4."""

    temp_folder = _prepare_temp_clip_folder(temp_root, clip.number)
    output_path = Path(output_video_path)
    try:
        kept_segments = calculate_kept_segment_seconds(
            effective_start_seconds if effective_start_seconds is not None else clip.start_seconds,
            effective_end_seconds if effective_end_seconds is not None else clip.end_seconds,
            clip.exclusions,
        )
        segment_paths: list[Path] = []
        for index, (segment_start_seconds, segment_end_seconds) in enumerate(kept_segments, start=1):
            segment_path = temp_folder / f"segment_{index:03d}.mp4"
            segment_paths.append(
                cut_clip(
                    input_video_path,
                    segment_path,
                    segment_start_seconds,
                    segment_end_seconds - segment_start_seconds,
                    runner,
                )
            )

        for exclusion in format_exclusions(clip.exclusions).split(", "):
            if exclusion:
                exclusion_start, exclusion_end = exclusion.split("-", maxsplit=1)
                _emit(progress_callback, f"تم حذف الجزء {exclusion_start} - {exclusion_end}")

        expected_duration = sum(segment_end - segment_start for segment_start, segment_end in kept_segments)
        file_list_path = write_concat_file_list(segment_paths, temp_folder / "segments.txt")
        try:
            concat_clip_segments(file_list_path, output_path, runner, expected_duration)
        except ClipCutError as error:
            raise ClipCutError(f"{AR_CONCAT_FAILED} {clip.number}: {error}") from error
        _emit(progress_callback, f"{AR_MERGED_CLIP_PARTS} {clip.number:02d}")
        return output_path
    except FfmpegNotFoundError:
        raise
    except VideoProcessingError:
        raise
    except ExclusionError as error:
        raise ClipCutError(str(error)) from error
    except Exception as error:
        raise ClipCutError(f"{AR_CONCAT_FAILED} {clip.number}: {error}") from error
    finally:
        _cleanup_temp_folder(temp_folder)


def concat_clip_segments(
    file_list_path: str | Path,
    output_video_path: str | Path,
    runner: SubprocessRunner = subprocess.run,
    expected_duration_seconds: int | float | None = None,
) -> Path:
    """Concatenate already-cut segment files into one mp4."""

    output_path = Path(output_video_path)
    ensure_directory(output_path.parent)
    command = build_ffmpeg_concat_command(file_list_path, output_path)

    try:
        _run_ffmpeg_command(command, output_path, runner)
        if expected_duration_seconds is not None and _should_validate_media_duration(runner):
            verify_output_duration(output_path, expected_duration_seconds)
    except FileNotFoundError as error:
        raise FfmpegNotFoundError(AR_FFMPEG_NOT_FOUND) from error

    return output_path


def write_concat_file_list(segment_paths: Sequence[Path], file_list_path: str | Path) -> Path:
    """Write an ffmpeg concat demuxer file list."""

    list_path = Path(file_list_path)
    ensure_directory(list_path.parent)
    lines = [f"file '{_escape_concat_path(path)}'" for path in segment_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def calculate_kept_segment_seconds(
    main_start_seconds: int | float,
    main_end_seconds: int | float,
    exclusions: str,
) -> list[tuple[float, float]]:
    """Return kept absolute-second segments for a clip with optional padded bounds."""

    if not exclusions.strip():
        return [(float(main_start_seconds), float(main_end_seconds))]

    # Reuse the existing HH:MM:SS exclusion normalizer for stable ordering and validation.
    calculate_kept_segments(
        format_seconds(max(0, math.floor(main_start_seconds))),
        format_seconds(math.ceil(main_end_seconds)),
        exclusions,
    )
    current_start = float(main_start_seconds)
    kept_segments: list[tuple[float, float]] = []
    for exclusion in format_exclusions(exclusions).split(", "):
        if not exclusion:
            continue
        exclusion_start_text, exclusion_end_text = exclusion.split("-", maxsplit=1)
        exclusion_start = float(parse_timestamp(exclusion_start_text))
        exclusion_end = float(parse_timestamp(exclusion_end_text))
        if exclusion_start > current_start:
            kept_segments.append((current_start, exclusion_start))
        current_start = max(current_start, exclusion_end)

    main_end = float(main_end_seconds)
    if current_start < main_end:
        kept_segments.append((current_start, main_end))

    return kept_segments


def _prepare_temp_clip_folder(temp_root: str | Path, clip_number: int) -> Path:
    temp_folder = Path(temp_root) / f"clip_{clip_number:03d}"
    if temp_folder.exists():
        shutil.rmtree(temp_folder)
    return ensure_directory(temp_folder)


def _cleanup_temp_folder(temp_folder: str | Path) -> None:
    folder = Path(temp_folder)
    parent = folder.parent
    shutil.rmtree(folder, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def _escape_concat_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def cut_clips(
    prepared_video: PreparedVideoSource,
    clips: list[ClipDefinition],
    progress_callback: ProgressCallback | None = None,
    runner: SubprocessRunner = subprocess.run,
    classification_rules: Sequence[ClassificationRule] | None = None,
    clip_padding: ClipPadding | None = None,
    video_duration_seconds: float | None = None,
) -> list[CutClipResult]:
    """Cut and sort all requested clips."""

    if not prepared_video.input_video_path.is_file():
        raise VideoProcessingError(AR_INPUT_VIDEO_MISSING)

    active_padding = clip_padding or ClipPadding()
    exclusion_errors = validate_exclusions_for_clips(clips, active_padding, video_duration_seconds)
    if exclusion_errors:
        raise VideoProcessingError(f"{AR_EXCLUSIONS_INVALID}:\n" + "\n".join(exclusion_errors))

    _emit(progress_callback, AR_CHECKING_EXCLUSIONS)
    if active_padding.has_padding:
        _emit(progress_callback, AR_CLIP_PADDING_APPLIED)

    results: list[CutClipResult] = []
    for clip in clips:
        _emit(progress_callback, f"جاري قص المقطع {clip.number}")
        effective_range = calculate_effective_clip_range(
            clip.start_seconds,
            clip.end_seconds,
            active_padding,
            video_duration_seconds,
        )
        try:
            destination_folder_name = classify_clip_folder(clip.duration_seconds, classification_rules)
        except ClassificationRuleError as error:
            _emit(progress_callback, f"{AR_NO_CLASSIFICATION_RULE_FOR_CLIP} {clip.number}")
            raise ClipCutError(f"{AR_NO_CLASSIFICATION_RULE_FOR_CLIP} {clip.number}: {error}") from error

        _emit(progress_callback, f"تم تصنيف المقطع {clip.number:02d} إلى مجلد {destination_folder_name}")
        output_path = build_clip_output_path(
            prepared_video.project_output_folder,
            clip,
            classification_rules,
            destination_folder_name,
        )

        try:
            if clip.exclusions.strip():
                _emit(progress_callback, f"{AR_CUTTING_EXCLUDED_PARTS} {clip.number:02d}")
                if len(format_exclusions(clip.exclusions).split(", ")) > 1:
                    _emit(progress_callback, f"{AR_MULTIPLE_EXCLUSIONS_APPLIED} {clip.number:02d}")
                cut_clip_with_exclusions(
                    prepared_video.input_video_path,
                    output_path,
                    clip,
                    Path(prepared_video.project_output_folder) / TEMP_SEGMENTS_FOLDER_NAME,
                    progress_callback,
                    runner,
                    effective_range.start_seconds,
                    effective_range.end_seconds,
                )
            else:
                _emit(progress_callback, f"{AR_NO_EXCLUSIONS_FOR_CLIP} {clip.number:02d}")
                cut_clip(
                    prepared_video.input_video_path,
                    output_path,
                    effective_range.start_seconds,
                    effective_range.duration_seconds,
                    runner,
                )
                _emit(progress_callback, AR_CUT_WITHOUT_EXCLUSIONS)
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


def _probe_video_duration_if_needed(input_video_path: Path, clip_padding: ClipPadding) -> float | None:
    if not clip_padding.has_padding:
        return None

    try:
        return probe_media_duration_seconds(input_video_path)
    except Exception:
        return None


def _emit(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _emit_project_name_cleanup(project_name: str | None, progress_callback: ProgressCallback | None) -> None:
    if project_name_was_cleaned(project_name):
        _emit(progress_callback, AR_PROJECT_NAME_CLEANED)
