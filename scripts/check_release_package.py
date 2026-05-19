"""Audit the portable Windows release folder before sharing it."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_PACKAGE_DIR = Path("dist") / "AlmiqsAlBaseet"
REQUIRED_FILES = ("AlmiqsAlBaseet.exe",)
REQUIRED_FOLDERS = ("_internal",)
FORBIDDEN_ROOT_ENTRIES = {
    "app.py",
    "src",
    "tests",
    "requirements.txt",
    "run_app.bat",
    "build_app.bat",
    "build_app_ci.bat",
}
FORBIDDEN_ANYWHERE_ENTRIES = {".pytest_cache", "__pycache__"}
FFMPEG_CANDIDATES = (
    "ffmpeg.exe",
    "bin/ffmpeg.exe",
    "tools/ffmpeg.exe",
    "_internal/ffmpeg.exe",
    "_internal/tools/ffmpeg.exe",
)
FFPROBE_CANDIDATES = (
    "ffprobe.exe",
    "bin/ffprobe.exe",
    "tools/ffprobe.exe",
    "_internal/ffprobe.exe",
    "_internal/tools/ffprobe.exe",
)


@dataclass(frozen=True)
class ReleaseAuditResult:
    """Result returned by the release package audit."""

    package_dir: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def audit_release_package(
    package_dir: str | Path = DEFAULT_PACKAGE_DIR,
    *,
    expect_readme_ar: bool = False,
) -> ReleaseAuditResult:
    """Check a built release package without changing it."""

    package_path = Path(package_dir)
    errors: list[str] = []
    warnings: list[str] = []
    messages = ["فحص حزمة الإصدار"]

    if not package_path.exists() or not package_path.is_dir():
        errors.append(f"الملف غير موجود: {package_path}")
        messages.append(f"الملف غير موجود: {package_path}")
        return ReleaseAuditResult(package_path, errors, warnings, _finalize(messages, errors))

    for relative_file in REQUIRED_FILES:
        _check_required_file(package_path, relative_file, errors, messages)

    for relative_folder in REQUIRED_FOLDERS:
        _check_required_folder(package_path, relative_folder, errors, messages)

    ffmpeg_path = _first_existing(package_path, FFMPEG_CANDIDATES)
    if ffmpeg_path is None:
        errors.append("الملف غير موجود: ffmpeg.exe")
        messages.append("الملف غير موجود: ffmpeg.exe")
    else:
        messages.append(f"الملف موجود: {ffmpeg_path.relative_to(package_path)}")

    ffprobe_path = _first_existing(package_path, FFPROBE_CANDIDATES)
    if ffprobe_path is None:
        if ffmpeg_path is None:
            errors.append("الملف غير موجود: ffprobe.exe ولا يوجد بديل ffmpeg")
            messages.append("الملف غير موجود: ffprobe.exe ولا يوجد بديل ffmpeg")
        else:
            warnings.append("ffprobe غير موجود وسيتم استخدام ffmpeg كبديل معتمد")
            messages.append("ffprobe غير موجود وسيتم استخدام ffmpeg كبديل معتمد")
    else:
        messages.append(f"الملف موجود: {ffprobe_path.relative_to(package_path)}")

    readme_ar_path = package_path / "README_AR.txt"
    if readme_ar_path.exists() and readme_ar_path.is_file():
        messages.append("الملف موجود: README_AR.txt")
    elif expect_readme_ar:
        errors.append("الملف غير موجود: README_AR.txt")
        messages.append("الملف غير موجود: README_AR.txt")

    _check_forbidden_entries(package_path, errors, messages)

    return ReleaseAuditResult(package_path, errors, warnings, _finalize(messages, errors))


def format_release_audit_report_ar(result: ReleaseAuditResult) -> str:
    """Format the audit result for command-line output."""

    return "\n".join(result.messages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit AlmiqsAlBaseet release package.")
    parser.add_argument(
        "package_dir",
        nargs="?",
        default=str(DEFAULT_PACKAGE_DIR),
        help="Path to the built release folder.",
    )
    parser.add_argument(
        "--expect-readme-ar",
        action="store_true",
        help="Require README_AR.txt in the release folder.",
    )
    args = parser.parse_args(argv)

    result = audit_release_package(args.package_dir, expect_readme_ar=args.expect_readme_ar)
    print(format_release_audit_report_ar(result))
    return 0 if result.passed else 1


def _check_required_file(
    package_path: Path,
    relative_file: str,
    errors: list[str],
    messages: list[str],
) -> None:
    path = package_path / relative_file
    if path.is_file():
        messages.append(f"الملف موجود: {relative_file}")
    else:
        errors.append(f"الملف غير موجود: {relative_file}")
        messages.append(f"الملف غير موجود: {relative_file}")


def _check_required_folder(
    package_path: Path,
    relative_folder: str,
    errors: list[str],
    messages: list[str],
) -> None:
    path = package_path / relative_folder
    if path.is_dir():
        messages.append(f"الملف موجود: {relative_folder}")
    else:
        errors.append(f"الملف غير موجود: {relative_folder}")
        messages.append(f"الملف غير موجود: {relative_folder}")


def _check_forbidden_entries(package_path: Path, errors: list[str], messages: list[str]) -> None:
    for forbidden_name in sorted(FORBIDDEN_ROOT_ENTRIES):
        path = package_path / forbidden_name
        if path.exists():
            errors.append(f"ملف ممنوع موجود: {forbidden_name}")
            messages.append(f"ملف ممنوع موجود: {forbidden_name}")

    for path in package_path.rglob("*"):
        if path.name in FORBIDDEN_ANYWHERE_ENTRIES:
            relative_path = path.relative_to(package_path)
            errors.append(f"ملف ممنوع موجود: {relative_path}")
            messages.append(f"ملف ممنوع موجود: {relative_path}")


def _first_existing(package_path: Path, candidates: tuple[str, ...]) -> Path | None:
    for candidate in candidates:
        path = package_path / candidate
        if path.is_file():
            return path
    return None


def _finalize(messages: list[str], errors: list[str]) -> list[str]:
    if errors:
        return [*messages, "الحزمة غير جاهزة"]
    return [*messages, "الحزمة جاهزة مبدئيًا"]


if __name__ == "__main__":
    raise SystemExit(main())
