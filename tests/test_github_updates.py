"""Security, update discovery, portable deployment, and rollback regressions."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from src.github_updates import (
    PORTABLE_APP_NAME,
    ReleaseUpdate,
    UpdateError,
    check_latest_release,
    create_apply_script,
    download_verified_update,
    numeric_version,
    parse_checksum,
    release_from_metadata,
    unpack_verified_archive,
)


def make_update(version="1.2.0"):
    tag = "v" + version
    fname = f"AlmiqsAlBaseet-Windows-{tag}.zip"
    base = "https://github.com/sami77337/educational-video-clipper"
    return ReleaseUpdate(
        version=version,
        tag=tag,
        page_url=base + "/releases/tag/" + tag,
        zip_name=fname,
        zip_url=base + "/releases/download/" + tag + "/" + fname,
        checksum_url=base + "/releases/download/" + tag + "/" + fname + ".sha256",
    )


def github_metadata(update: ReleaseUpdate):
    return {
        "tag_name": update.tag,
        "draft": False,
        "prerelease": False,
        "html_url": update.page_url,
        "assets": [
            {"name": update.zip_name, "browser_download_url": update.zip_url},
            {"name": update.zip_name + ".sha256", "browser_download_url": update.checksum_url},
        ],
    }


def make_portable_zip(extra=None):
    buff = io.BytesIO()
    with ZipFile(buff, "w", compression=ZIP_DEFLATED) as z:
        base = PORTABLE_APP_NAME + "/"
        z.writestr(base + "AlmiqsAlBaseet.exe", b"EXE")
        z.writestr(base + "ffmpeg.exe", b"FFMPEG")
        z.writestr(base + "README_AR.txt", b"README")
        z.writestr(base + "_internal/core.dll", b"internal")
        for name, value in (extra or {}).items():
            z.writestr(name, value)
    return buff.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, content):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))}


def make_fake_opener(update, zip_bytes, *, correct_hash=True):
    digest = hashlib.sha256(zip_bytes).hexdigest() if correct_hash else "0" * 64
    checksum = (digest + "  " + update.zip_name + "\n").encode("ascii")
    def fake_opener(request, timeout):
        if request.full_url == update.zip_url:
            return FakeResponse(zip_bytes)
        if request.full_url == update.checksum_url:
            return FakeResponse(checksum)
        raise RuntimeError("Unexpected URL " + request.full_url)
    return fake_opener


def test_semantic_version_comparison():
    assert numeric_version("v1.2.0") > numeric_version("1.1.99")
    assert numeric_version("1.1.0") == (1, 1, 0)
    with pytest.raises(ValueError):
        numeric_version("1.2.0-rc1")


def test_only_newer_stable_github_release_is_accepted():
    release = make_update()
    metadata = github_metadata(release)
    assert release_from_metadata(metadata, "1.1.0") == release
    assert release_from_metadata(metadata, "1.2.0") is None
    assert release_from_metadata(metadata, "1.3.0") is None
    assert release_from_metadata({**metadata, "prerelease": True}, "1.1.0") is None
    assert release_from_metadata({**metadata, "draft": True}, "1.1.0") is None
    assert release_from_metadata({**metadata, "tag_name": "unsafe"}, "1.1.0") is None


def test_fake_github_domain_or_wrong_release_asset_is_rejected():
    release = make_update()
    metadata = github_metadata(release)
    with pytest.raises(UpdateError):
        release_from_metadata({**metadata, "html_url": "https://evil.example/other"}, "1.1.0")
    metadata["assets"][0]["browser_download_url"] = "https://evil.example/payload.zip"
    with pytest.raises(UpdateError):
        release_from_metadata(metadata, "1.1.0")


def test_github_check_reads_stable_metadata_and_skips_404():
    release = make_update()
    raw = json.dumps(github_metadata(release)).encode("utf-8")
    assert check_latest_release("1.1.0", opener=lambda *_args, **_kwargs: FakeResponse(raw)) == release
    def raises404(*_args, **_kwargs):
        raise HTTPError("https://api.github.com/", 404, "Not found", {}, None)
    assert check_latest_release("1.1.0", opener=raises404) is None


def test_checksum_must_match_exact_archive_filename():
    release = make_update()
    value = "a" * 64
    assert parse_checksum(value + "  " + release.zip_name, release.zip_name) == value
    for invalid in (value + "  other.zip", value, "badhash  " + release.zip_name):
        with pytest.raises(UpdateError):
            parse_checksum(invalid, release.zip_name)


def test_github_download_verifies_checksum_and_extracts_in_staging(tmp_path: Path):
    release = make_update()
    archive = make_portable_zip()
    updates = []
    stage = download_verified_update(
        release,
        update_root=tmp_path,
        opener=make_fake_opener(release, archive),
        progress=lambda received, total: updates.append((received, total)),
    )
    assert (stage / "AlmiqsAlBaseet.exe").read_bytes() == b"EXE"
    assert (stage / "_internal" / "core.dll").read_bytes() == b"internal"
    assert stage.name == PORTABLE_APP_NAME
    assert updates[-1][0] == len(archive)


def test_corrupted_github_download_never_reaches_staging(tmp_path: Path):
    release = make_update()
    with pytest.raises(UpdateError, match="SHA256"):
        download_verified_update(
            release, update_root=tmp_path,
            opener=make_fake_opener(release, make_portable_zip(), correct_hash=False),
        )
    assert not list(tmp_path.rglob("AlmiqsAlBaseet.exe"))


@pytest.mark.parametrize("malicious_name", [
    "AlmiqsAlBaseet/../../outside.txt",
    "AlmiqsAlBaseet\\..\\outside.txt",
    "/AlmiqsAlBaseet/evil.txt",
    "another_folder/evil.txt",
    "AlmiqsAlBaseet/f:evil.txt",
])
def test_malicious_zip_paths_are_rejected(tmp_path: Path, malicious_name: str):
    source = tmp_path / "malicious.zip"
    source.write_bytes(make_portable_zip({malicious_name: b"MALICIOUS"}))
    with pytest.raises(UpdateError):
        unpack_verified_archive(source, tmp_path / "staged")
    assert not (tmp_path / "outside.txt").exists()


def test_reject_case_insensitive_duplicate_zip_members(tmp_path: Path):
    path = tmp_path / "duplicate.zip"
    path.write_bytes(make_portable_zip({
        "AlmiqsAlBaseet/README_AR.TXT": b"DUPLICATE",
    }))
    with pytest.raises(UpdateError, match="مكررة"):
        unpack_verified_archive(path, tmp_path / "staged")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell installer runs only on Windows")
def test_portable_windows_update_preserves_project_results_and_keeps_backup(tmp_path: Path):
    install = tmp_path / "ملفات العمل" / "AlmiqsAlBaseet"
    stage = tmp_path / "updates" / "v1.2.0-xyz" / "staged" / "AlmiqsAlBaseet"
    for root in (install, stage):
        (root / "_internal").mkdir(parents=True)
        (root / "bin").mkdir()
        (root / "AlmiqsAlBaseet.exe").write_bytes(b"OLD" if root == install else b"NEW")
        (root / "_internal" / "core.dll").write_bytes(b"old-dll" if root == install else b"new-dll")
        (root / "ffmpeg.exe").write_bytes(b"ffmpeg")
        (root / "README_AR.txt").write_text("old" if root == install else "new", encoding="utf-8")
    (install / "output" / "فتاوى").mkdir(parents=True)
    (install / "output" / "فتاوى" / "النتيجة.mp4").write_bytes(b"IMPORTANT VIDEO")
    (install / "settings.json").write_text("keep me", encoding="utf-8")
    backup = install / ".backup-before-update-test"
    script = create_apply_script(stage)

    command = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-InstallDir", str(install),
        "-StageDir", str(stage),
        "-PreviousPid", "999999",
        "-BackupDir", str(backup),
        "-NoRestart",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, (result.stderr + "\n" + result.stdout)[-1800:]
    assert (install / "AlmiqsAlBaseet.exe").read_bytes() == b"NEW"
    assert (install / "_internal" / "core.dll").read_bytes() == b"new-dll"
    assert (backup / "AlmiqsAlBaseet.exe").read_bytes() == b"OLD"
    assert (install / "output" / "فتاوى" / "النتيجة.mp4").read_bytes() == b"IMPORTANT VIDEO"
    assert (install / "settings.json").read_text(encoding="utf-8") == "keep me"
