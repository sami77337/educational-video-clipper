from pathlib import Path

from scripts.check_release_package import audit_release_package, format_release_audit_report_ar


def _minimal_package(tmp_path):
    package_dir = tmp_path / "AlmiqsAlBaseet"
    package_dir.mkdir()
    (package_dir / "AlmiqsAlBaseet.exe").write_bytes(b"exe")
    (package_dir / "README_AR.txt").write_text("تعليمات الاستخدام", encoding="utf-8")
    (package_dir / "_internal").mkdir()
    (package_dir / "ffmpeg.exe").write_bytes(b"ffmpeg")
    return package_dir


def test_release_audit_accepts_minimal_package_with_ffmpeg_fallback(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)

    result = audit_release_package(package_dir)
    report = format_release_audit_report_ar(result)

    assert result.passed
    assert "فحص حزمة الإصدار" in report
    assert "الملف موجود: AlmiqsAlBaseet.exe" in report
    assert "الملف موجود: README_AR.txt" in report
    assert "الملف موجود: _internal" in report
    assert "ffprobe غير موجود وسيتم استخدام ffmpeg كبديل معتمد" in report
    assert "الحزمة جاهزة مبدئيًا" in report


def test_release_audit_detects_missing_required_file(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)
    (package_dir / "AlmiqsAlBaseet.exe").unlink()

    result = audit_release_package(package_dir)

    assert not result.passed
    assert "الملف غير موجود: AlmiqsAlBaseet.exe" in result.errors
    assert "الحزمة غير جاهزة" in format_release_audit_report_ar(result)


def test_release_audit_detects_missing_package_folder(tmp_path) -> None:
    result = audit_release_package(tmp_path / "missing")

    assert not result.passed
    assert result.errors == [f"الملف غير موجود: {tmp_path / 'missing'}"]


def test_release_audit_detects_forbidden_root_file(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)
    (package_dir / "app.py").write_text("print('dev file')", encoding="utf-8")

    result = audit_release_package(package_dir)

    assert not result.passed
    assert "ملف ممنوع موجود: app.py" in result.errors


def test_release_audit_detects_forbidden_cache_folder(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)
    cache_dir = package_dir / "_internal" / "__pycache__"
    cache_dir.mkdir()

    result = audit_release_package(package_dir)

    assert not result.passed
    assert f"ملف ممنوع موجود: {cache_dir.relative_to(package_dir)}" in result.errors


def test_release_audit_requires_arabic_readme_by_default(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)
    (package_dir / "README_AR.txt").unlink()

    result = audit_release_package(package_dir)

    assert not result.passed
    assert "الملف غير موجود: README_AR.txt" in result.errors


def test_release_audit_detects_forbidden_dev_script(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)
    (package_dir / "build_installer.bat").write_text("@echo off", encoding="utf-8")

    result = audit_release_package(package_dir)

    assert not result.passed
    assert "ملف ممنوع موجود: build_installer.bat" in result.errors


def test_release_preparation_files_exist_and_document_forbidden_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    release_readme = root / "RELEASE_README_AR.md"
    guide = root / "docs" / "RELEASE_PACKAGE_GUIDE.md"
    installer_script = root / "installer" / "AlmiqsAlBaseet.iss"
    build_installer = root / "build_installer.bat"

    assert release_readme.is_file()
    assert guide.is_file()
    assert installer_script.is_file()
    assert build_installer.is_file()

    guide_text = guide.read_text(encoding="utf-8")
    assert "app.py" in guide_text
    assert "src" in guide_text
    assert "tests" in guide_text
    assert "ملفات المصدر لا تُرسل للفريق" in guide_text

    readme_text = release_readme.read_text(encoding="utf-8")
    assert "لا يتم إنشاء ملف ZIP افتراضيًا" in readme_text
    assert "فتح مجلد النتائج" in readme_text


def test_inno_setup_script_installs_built_dist_only() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "installer" / "AlmiqsAlBaseet.iss").read_text(encoding="utf-8")

    assert "Source: \"..\\dist\\AlmiqsAlBaseet\\*\"" in script
    assert "AlmiqsAlBaseet.exe" in script
    assert "app.py" not in script
    assert "src\\*" not in script
    assert "tests\\*" not in script
