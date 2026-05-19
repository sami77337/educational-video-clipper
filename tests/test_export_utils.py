from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from src.classification import ClassificationRule
from src.export_utils import (
    AR_CREATING_COMPLETE_ZIP,
    AR_ZIP_FILES_CREATED,
    AR_ZIPPING_REELS,
    BENEFITS_FOLDER_NAME,
    BENEFITS_ZIP_NAME,
    COMPLETE_RESULT_ZIP_NAME,
    ExportError,
    ProcessingReportData,
    ProcessingReportClipData,
    REELS_FOLDER_NAME,
    REELS_ZIP_NAME,
    REPORT_FILE_NAME,
    ZIP_FOLDER_NAME,
    build_processing_report,
    create_result_zips,
    validate_output_folder_path,
)
from src.video_processor import ClipDefinition, CutClipResult, VideoProcessor, VideoSourceType


def test_create_result_zips_creates_zip_folder_and_expected_archives(tmp_path) -> None:
    project_folder = tmp_path / "project"
    reels_folder = project_folder / REELS_FOLDER_NAME
    benefits_folder = project_folder / BENEFITS_FOLDER_NAME
    reels_folder.mkdir(parents=True)
    benefits_folder.mkdir(parents=True)
    (reels_folder / "1_intro.mp4").write_bytes(b"reel")
    messages: list[str] = []

    result = create_result_zips(project_folder, messages.append)

    assert result.zip_folder == project_folder / ZIP_FOLDER_NAME
    assert project_folder.joinpath(ZIP_FOLDER_NAME, REELS_ZIP_NAME).is_file()
    assert not project_folder.joinpath(ZIP_FOLDER_NAME, BENEFITS_ZIP_NAME).exists()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, COMPLETE_RESULT_ZIP_NAME).is_file()
    assert AR_ZIPPING_REELS in messages
    assert AR_CREATING_COMPLETE_ZIP in messages
    assert AR_ZIP_FILES_CREATED in messages

    with ZipFile(project_folder / ZIP_FOLDER_NAME / COMPLETE_RESULT_ZIP_NAME) as zip_file:
        assert REELS_FOLDER_NAME + "/" in zip_file.namelist()
        assert f"{REELS_FOLDER_NAME}/1_intro.mp4" in zip_file.namelist()
        assert BENEFITS_FOLDER_NAME + "/" in zip_file.namelist()


def test_create_result_zips_generates_archives_for_dynamic_folders(tmp_path) -> None:
    project_folder = tmp_path / "project"
    shorts_folder = project_folder / "Shorts"
    long_benefits_folder = project_folder / "فوائد طويلة"
    lessons_folder = project_folder / "دروس"
    shorts_folder.mkdir(parents=True)
    long_benefits_folder.mkdir()
    lessons_folder.mkdir()
    (shorts_folder / "1_short.mp4").write_bytes(b"short")
    (long_benefits_folder / "2_long.mp4").write_bytes(b"long")

    result = create_result_zips(project_folder, folder_names=["Shorts", "فوائد طويلة", "دروس"])

    assert project_folder.joinpath(ZIP_FOLDER_NAME, "Shorts.zip").is_file()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, "فوائد طويلة.zip").is_file()
    assert not project_folder.joinpath(ZIP_FOLDER_NAME, "دروس.zip").exists()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, COMPLETE_RESULT_ZIP_NAME).is_file()
    assert result.zip_files[-1] == project_folder / ZIP_FOLDER_NAME / COMPLETE_RESULT_ZIP_NAME

    with ZipFile(project_folder / ZIP_FOLDER_NAME / COMPLETE_RESULT_ZIP_NAME) as zip_file:
        assert "Shorts/" in zip_file.namelist()
        assert "فوائد طويلة/2_long.mp4" in zip_file.namelist()
        assert "دروس/" in zip_file.namelist()


def test_build_processing_report_includes_required_content(tmp_path) -> None:
    started_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 5, 13, 10, 3, tzinfo=timezone.utc)
    data = ProcessingReportData(
        project_name="مشروع تعليمي",
        source_type="YouTube",
        total_clips_count=2,
        reels_count=1,
        benefits_count=1,
        output_folders=[tmp_path / REELS_FOLDER_NAME, tmp_path / BENEFITS_FOLDER_NAME],
        zip_files=[tmp_path / ZIP_FOLDER_NAME / REELS_ZIP_NAME],
        started_at=started_at,
        ended_at=ended_at,
        skipped_or_failed_items=[],
    )

    report = build_processing_report(data)

    assert "Project name: مشروع تعليمي" in report
    assert "Source type: YouTube" in report
    assert "Total clips count: 2" in report
    assert "Reels count: 1" in report
    assert "Benefits count: 1" in report
    assert "ZIP files created:" in report
    assert "Start timestamp of processing: 2026-05-13 10:00:00+00:00" in report
    assert "End timestamp of processing: 2026-05-13 10:03:00+00:00" in report
    assert "Skipped or failed items:\n- None" in report


def test_build_processing_report_includes_dynamic_rules_and_counts(tmp_path) -> None:
    started_at = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 5, 13, 10, 3, tzinfo=timezone.utc)
    data = ProcessingReportData(
        project_name="مشروع تعليمي",
        source_type="local file",
        total_clips_count=3,
        reels_count=0,
        benefits_count=0,
        output_folders=[tmp_path / "Shorts", tmp_path / "دروس"],
        zip_files=[tmp_path / ZIP_FOLDER_NAME / "Shorts.zip"],
        started_at=started_at,
        ended_at=ended_at,
        skipped_or_failed_items=[],
        classification_rules=[
            ClassificationRule("Shorts", 0, 1, "Shorts"),
            ClassificationRule("دروس", 1, None, "دروس"),
        ],
        clip_counts_by_folder={"Shorts": 2, "دروس": 1},
    )

    report = build_processing_report(data)

    assert "Classification rules:" in report
    assert "- Shorts: من 0 إلى 1 دقيقة -> Shorts" in report
    assert "- دروس: من 1 إلى مفتوح دقيقة -> دروس" in report
    assert "Clip counts by folder:" in report
    assert "- Shorts: 2" in report
    assert "- دروس: 1" in report
    assert str(tmp_path / ZIP_FOLDER_NAME / "Shorts.zip") in report


def test_build_processing_report_includes_clip_exclusions() -> None:
    timestamp = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
    data = ProcessingReportData(
        project_name="Project",
        source_type="local file",
        total_clips_count=1,
        reels_count=1,
        benefits_count=0,
        output_folders=[],
        zip_files=[],
        started_at=timestamp,
        ended_at=timestamp,
        skipped_or_failed_items=[],
        clip_details=[
            ProcessingReportClipData(
                number=1,
                title="عنوان المقطع",
                start="00:26:56",
                end="00:29:14",
                exclusions="00:27:40-00:28:20",
                folder_name=REELS_FOLDER_NAME,
            )
        ],
    )

    report = build_processing_report(data)

    assert "01 - عنوان المقطع" in report
    assert "البداية: 00:26:56" in report
    assert "النهاية: 00:29:14" in report
    assert "الاستثناءات: 00:27:40-00:28:20" in report
    assert f"المجلد: {REELS_FOLDER_NAME}" in report


def test_export_results_creates_full_result_folder_structure(tmp_path) -> None:
    project_folder = tmp_path / "project"
    reels_folder = project_folder / REELS_FOLDER_NAME
    benefits_folder = project_folder / BENEFITS_FOLDER_NAME
    reels_folder.mkdir(parents=True)
    benefits_folder.mkdir()
    (project_folder / "input.mp4").write_bytes(b"input")
    (reels_folder / "1_reel.mp4").write_bytes(b"reel")
    (benefits_folder / "2_benefit.mp4").write_bytes(b"benefit")
    cut_results = [
        CutClipResult(
            clip=ClipDefinition(number=1, title="reel", start_seconds=0, end_seconds=30),
            output_path=reels_folder / "1_reel.mp4",
            destination_folder_name=REELS_FOLDER_NAME,
        ),
        CutClipResult(
            clip=ClipDefinition(
                number=2,
                title="benefit",
                start_seconds=0,
                end_seconds=181,
                exclusions="00:01:00-00:01:10",
            ),
            output_path=benefits_folder / "2_benefit.mp4",
            destination_folder_name=BENEFITS_FOLDER_NAME,
        ),
    ]
    processor = VideoProcessor(output_root=tmp_path)

    artifacts = processor.export_results(
        project_output_folder=project_folder,
        project_name="Project",
        source_type=VideoSourceType.LOCAL_FILE,
        cut_results=cut_results,
        started_at=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 13, 10, 5, tzinfo=timezone.utc),
    )

    assert project_folder.joinpath("input.mp4").is_file()
    assert project_folder.joinpath(REELS_FOLDER_NAME).is_dir()
    assert project_folder.joinpath(BENEFITS_FOLDER_NAME).is_dir()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, REELS_ZIP_NAME).is_file()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, BENEFITS_ZIP_NAME).is_file()
    assert project_folder.joinpath(ZIP_FOLDER_NAME, COMPLETE_RESULT_ZIP_NAME).is_file()
    assert project_folder.joinpath(REPORT_FILE_NAME).is_file()
    assert artifacts.report_path == project_folder / REPORT_FILE_NAME
    assert "الاستثناءات: 00:01:00-00:01:10" in artifacts.report_path.read_text(encoding="utf-8")


def test_validate_output_folder_path_accepts_existing_folder(tmp_path) -> None:
    assert validate_output_folder_path(tmp_path) == tmp_path


def test_validate_output_folder_path_rejects_missing_folder(tmp_path) -> None:
    with pytest.raises(ExportError):
        validate_output_folder_path(tmp_path / "missing")
