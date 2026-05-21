"""Application path resolution helpers."""

from __future__ import annotations

import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


AR_OUTPUT_FALLBACK_USED = "تعذر إنشاء مجلد النتائج بجانب البرنامج، تم استخدام مجلد آمن داخل المستندات"
AR_OUTPUT_CREATE_FAILED = "لا يمكن إنشاء مجلد النتائج. اختر مجلدًا آخر لديك صلاحية الكتابة فيه."
AR_OUTPUT_FOLDER_USED = "تم استخدام مجلد النتائج"


class OutputPathError(PermissionError):
    """Raised when no safe writable output folder can be prepared."""


WriteProbe = Callable[[Path], bool]


@dataclass(frozen=True)
class OutputRootResolution:
    """Resolved output root plus any user-facing warning."""

    path: Path
    used_fallback: bool = False
    warning: str = ""


def app_directory(
    *,
    executable: str | Path | None = None,
    frozen: bool | None = None,
    module_file: str | Path | None = None,
) -> Path:
    """Return the real app directory without consulting the current directory."""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        exe_path = Path(executable or sys.executable)
        return exe_path.resolve().parent

    source_file = Path(module_file or __file__)
    return source_file.resolve().parents[1]


def default_output_root(*, app_dir: str | Path | None = None) -> Path:
    """Return the default output folder beside the app."""

    base_dir = Path(app_dir) if app_dir is not None else app_directory()
    return base_dir.resolve() / "output"


def documents_output_root(*, documents_dir: str | Path | None = None) -> Path:
    """Return the safe per-user fallback output folder."""

    documents = Path(documents_dir) if documents_dir is not None else Path.home() / "Documents"
    return documents.resolve() / "AlmiqsAlBaseet" / "output"


def resolve_output_root(
    configured_output_root: str | Path | None = None,
    *,
    app_dir: str | Path | None = None,
    documents_dir: str | Path | None = None,
    write_probe: WriteProbe | None = None,
) -> OutputRootResolution:
    """Resolve and create a writable output root."""

    preferred = (
        Path(configured_output_root).expanduser()
        if configured_output_root is not None
        else default_output_root(app_dir=app_dir)
    )
    try:
        return OutputRootResolution(_ensure_writable_directory(preferred, write_probe=write_probe))
    except OSError:
        fallback = documents_output_root(documents_dir=documents_dir)
        try:
            return OutputRootResolution(
                _ensure_writable_directory(fallback, write_probe=write_probe),
                used_fallback=True,
                warning=AR_OUTPUT_FALLBACK_USED,
            )
        except OSError as fallback_error:
            raise OutputPathError(AR_OUTPUT_CREATE_FAILED) from fallback_error


def _ensure_writable_directory(path: str | Path, *, write_probe: WriteProbe | None = None) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if write_probe is not None:
        if not write_probe(directory):
            raise PermissionError(AR_OUTPUT_CREATE_FAILED)
        return directory

    probe_path = directory / f".write_test_{uuid.uuid4().hex}.tmp"
    try:
        probe_path.write_text("ok", encoding="utf-8")
    finally:
        try:
            probe_path.unlink()
        except FileNotFoundError:
            pass
    return directory
