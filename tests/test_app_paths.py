from pathlib import Path

import pytest

from src.app_paths import (
    AR_OUTPUT_CREATE_FAILED,
    AR_OUTPUT_FALLBACK_USED,
    OutputPathError,
    app_directory,
    default_output_root,
    documents_output_root,
    resolve_output_root,
)


def test_built_mode_app_directory_uses_executable_parent(tmp_path: Path) -> None:
    exe_path = tmp_path / "dist" / "AlmiqsAlBaseet" / "AlmiqsAlBaseet.exe"

    assert app_directory(executable=exe_path, frozen=True) == exe_path.resolve().parent


def test_default_output_root_is_app_dir_output(tmp_path: Path) -> None:
    app_dir = tmp_path / "AlmiqsAlBaseet"

    assert default_output_root(app_dir=app_dir) == app_dir.resolve() / "output"


def test_default_output_root_does_not_depend_on_current_working_directory(tmp_path: Path, monkeypatch) -> None:
    fake_system32 = tmp_path / "WINDOWS" / "System32"
    fake_system32.mkdir(parents=True)
    app_dir = tmp_path / "dist" / "AlmiqsAlBaseet"
    app_dir.mkdir(parents=True)
    monkeypatch.chdir(fake_system32)

    result = resolve_output_root(app_dir=app_dir)

    assert result.path == app_dir.resolve() / "output"
    assert result.path != fake_system32 / "output"
    assert "System32" not in str(result.path)


def test_output_root_is_created_if_missing(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    output_root = app_dir / "output"

    result = resolve_output_root(app_dir=app_dir)

    assert result.path == output_root.resolve()
    assert output_root.is_dir()


def test_non_writable_app_dir_falls_back_to_documents(tmp_path: Path) -> None:
    app_dir = tmp_path / "Program Files" / "AlmiqsAlBaseet"
    documents_dir = tmp_path / "Documents"
    preferred = app_dir.resolve() / "output"

    result = resolve_output_root(
        app_dir=app_dir,
        documents_dir=documents_dir,
        write_probe=lambda path: path != preferred,
    )

    assert result.path == documents_output_root(documents_dir=documents_dir)
    assert result.used_fallback is True
    assert result.warning == AR_OUTPUT_FALLBACK_USED


def test_non_writable_configured_output_folder_falls_back_safely(tmp_path: Path) -> None:
    configured = tmp_path / "blocked-output"
    documents_dir = tmp_path / "Documents"
    blocked = configured.resolve()

    result = resolve_output_root(
        configured,
        documents_dir=documents_dir,
        write_probe=lambda path: path != blocked,
    )

    assert result.path == documents_output_root(documents_dir=documents_dir)
    assert result.used_fallback is True


def test_total_failure_to_create_output_folder_raises_clear_arabic_error(tmp_path: Path) -> None:
    with pytest.raises(OutputPathError) as error:
        resolve_output_root(
            app_dir=tmp_path / "app",
            documents_dir=tmp_path / "Documents",
            write_probe=lambda _path: False,
        )

    assert str(error.value) == AR_OUTPUT_CREATE_FAILED
