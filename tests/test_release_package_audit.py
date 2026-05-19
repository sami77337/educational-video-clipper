from scripts.check_release_package import audit_release_package, format_release_audit_report_ar


def _minimal_package(tmp_path):
    package_dir = tmp_path / "AlmiqsAlBaseet"
    package_dir.mkdir()
    (package_dir / "AlmiqsAlBaseet.exe").write_bytes(b"exe")
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


def test_release_audit_can_require_arabic_readme(tmp_path) -> None:
    package_dir = _minimal_package(tmp_path)

    result = audit_release_package(package_dir, expect_readme_ar=True)

    assert not result.passed
    assert "الملف غير موجود: README_AR.txt" in result.errors
