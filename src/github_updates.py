"""Verified GitHub Releases update support for the portable Windows desktop app.

The app never installs an unauthenticated ZIP, never updates from arbitrary
repository commits, and never overwrites project outputs. Only a stable
versioned GitHub Release with a matching SHA256 sidecar can be installed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPO = "sami77337/educational-video-clipper"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_SITE = f"https://github.com/{REPO}/releases"
PORTABLE_APP_NAME = "AlmiqsAlBaseet"
MAX_DOWNLOAD_BYTES = 1_200_000_000
MAX_UNPACKED_BYTES = 2_400_000_000
MAX_ZIP_MEMBERS = 10000
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
SHA_LINE = re.compile(r"^([a-fA-F0-9]{64})  \S+$")


class UpdateError(RuntimeError):
    """A release could not be fetched or was unsafe to apply."""


@dataclass(frozen=True)
class ReleaseUpdate:
    version: str
    tag: str
    page_url: str
    zip_name: str
    zip_url: str
    checksum_url: str


def numeric_version(value: str) -> tuple[int, int, int]:
    result = VERSION_PATTERN.fullmatch(value.strip())
    if not result:
        raise ValueError("الإصدار يجب أن يكون رقمًا مثل 1.1.0")
    return tuple(int(x) for x in result.groups())  # type: ignore[return-value]


def release_from_metadata(data: object, current_version: str) -> ReleaseUpdate | None:
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if not tag.startswith("v"):
        return None
    try:
        available = numeric_version(tag)
        current = numeric_version(current_version)
    except ValueError:
        return None
    if available <= current:
        return None

    version = tag[1:]
    filename = f"{PORTABLE_APP_NAME}-Windows-{tag}.zip"
    checksum = filename + ".sha256"
    prefix = f"{RELEASE_SITE}/download/{tag}/"
    page_url = data.get("html_url")
    if page_url != f"{RELEASE_SITE}/tag/{tag}":
        raise UpdateError("عنوان إصدار GitHub غير متوقع.")
    by_name = {
        item.get("name"): item.get("browser_download_url")
        for item in data.get("assets", [])
        if isinstance(item, dict)
    }
    zip_url = by_name.get(filename)
    checksum_url = by_name.get(checksum)
    if zip_url != prefix + filename or checksum_url != prefix + checksum:
        raise UpdateError(
            "الإصدار الجديد لا يحتوي حزمة Windows موقعة ببصمة SHA256 صحيحة."
        )
    return ReleaseUpdate(
        version=version, tag=tag, page_url=page_url,
        zip_name=filename, zip_url=zip_url, checksum_url=checksum_url,
    )


def check_latest_release(
    current_version: str,
    *,
    opener: Callable = urlopen,
) -> ReleaseUpdate | None:
    """Look for a newer *stable* release. Safe when there are no releases yet."""
    request = _request(API_URL)
    try:
        with opener(request, timeout=10) as response:
            content = response.read(524289)
            if len(content) > 524288:
                raise UpdateError("بيانات إصدار GitHub أكبر من الحد المسموح.")
    except HTTPError as error:
        if error.code == 404:
            return None
        raise UpdateError(f"تعذر الاتصال بـGitHub (HTTP {error.code}).") from error
    except (URLError, TimeoutError, OSError) as error:
        raise UpdateError("تعذر فحص تحديثات GitHub. تحقق من الاتصال بالإنترنت.") from error
    try:
        metadata = json.loads(content.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise UpdateError("استجابة GitHub لا تحتوي بيانات تحديث مفهومة.") from error
    return release_from_metadata(metadata, current_version)


def _request(url: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AlmiqsAlBaseet-Desktop-Updater/1",
        },
    )


def parse_checksum(text: str, zip_name: str) -> str:
    """Require exactly one sha256sum line for this exact archive filename."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise UpdateError("ملف بصمة التحديث غير صالح.")
    match = SHA_LINE.fullmatch(lines[0])
    if match is None or lines[0][66:] != zip_name:
        raise UpdateError("بصمة SHA256 لا تطابق اسم حزمة التحديث.")
    return match.group(1).lower()


def download_verified_update(
    release: ReleaseUpdate,
    *,
    update_root: str | Path | None = None,
    opener: Callable = urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Download, hash-check and safely extract; return full staged app directory.

    No existing installation files are modified by this function.
    """
    parent = Path(update_root or _default_updates_root()).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"{release.tag}-", dir=parent))
    zip_path = root / release.zip_name
    unpack_dir = root / "staged"
    try:
        with opener(_request(release.checksum_url), timeout=15) as stream:
            checksum_bytes = stream.read(257)
            if len(checksum_bytes) > 256:
                raise UpdateError("ملف بصمة التحديث أكبر من المتوقع.")
        expected_sha = parse_checksum(checksum_bytes.decode("ascii"), release.zip_name)

        digest = hashlib.sha256()
        received = 0
        with opener(_request(release.zip_url), timeout=45) as stream:
            headers = getattr(stream, "headers", {})
            content_length = headers.get("Content-Length") if headers else None
            try:
                total = int(content_length) if content_length else 0
            except (ValueError, TypeError):
                total = 0
            if total > MAX_DOWNLOAD_BYTES:
                raise UpdateError("حجم حزمة التحديث يتجاوز الحد الآمن.")
            with zip_path.open("wb") as out:
                while chunk := stream.read(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("حجم حزمة التحديث يتجاوز الحد الآمن.")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress:
                        progress(received, total)
        if digest.hexdigest() != expected_sha:
            raise UpdateError("فشل التحقق من SHA256. لن يُثبَّت هذا التحديث.")

        install_stage = unpack_verified_archive(zip_path, unpack_dir)
        return install_stage
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        shutil.rmtree(root, ignore_errors=True)
        raise UpdateError(f"فشل تنزيل تحديث GitHub: {error}") from error
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def unpack_verified_archive(archive_path: str | Path, destination: str | Path) -> Path:
    """Extract only paths inside AlmiqsAlBaseet/, rejecting traversal and bombs."""
    archive_path = Path(archive_path)
    destination = Path(destination)
    if destination.exists():
        raise UpdateError("مجلد التحديث المؤقت موجود بالفعل.")
    destination.mkdir(parents=True)

    total_bytes = 0
    seen_names: set[str] = set()
    try:
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ZIP_MEMBERS:
                raise UpdateError("عدد ملفات التحديث غير صالح.")
            for member in members:
                name = member.filename
                if "\\" in name or name.startswith("/") or ":" in name:
                    raise UpdateError("تحتوي الحزمة على مسار غير آمن.")
                parts = name.rstrip("/").split("/")
                if (
                    not parts or parts[0] != PORTABLE_APP_NAME
                    or any(not part or part in {".", ".."} for part in parts)
                    or any(part.rstrip(" .") != part for part in parts)
                ):
                    raise UpdateError("تحتوي الحزمة على مسار خارج مجلد البرنامج.")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise UpdateError("الحزمة تحتوي على روابط رمزية غير مسموحة.")
                key = name.rstrip("/").casefold()
                if key in seen_names:
                    raise UpdateError("أسماء ملفات التحديث مكررة.")
                seen_names.add(key)
                total_bytes += member.file_size
                if total_bytes > MAX_UNPACKED_BYTES:
                    raise UpdateError("المحتوى المفكوك يتجاوز الحد الآمن.")

            for member in members:
                output = destination.joinpath(*member.filename.rstrip("/").split("/"))
                if member.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as src, output.open("xb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)

        app = destination / PORTABLE_APP_NAME
        required = (
            app / "AlmiqsAlBaseet.exe",
            app / "ffmpeg.exe",
            app / "README_AR.txt",
            app / "_internal",
        )
        if not (all(path.exists() for path in required) and (app / "_internal").is_dir()):
            raise UpdateError("حزمة التحديث تفتقد ملفات التشغيل الأساسية.")
        return app
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _default_updates_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "AlmiqsAlBaseet" / "verified-updates"


POWERSHELL_APPLY = r'''param(
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string]$StageDir,
  [Parameter(Mandatory=$true)][int]$PreviousPid,
  [Parameter(Mandatory=$true)][string]$BackupDir,
  [switch]$NoRestart
)
$ErrorActionPreference = 'Stop'
$names = @('AlmiqsAlBaseet.exe', '_internal', 'ffmpeg.exe', 'bin', 'README_AR.txt', 'PREVIEW_BUILD_INFO.txt')
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Process -Id $PreviousPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) {
  Start-Sleep -Milliseconds 500
}
if (Get-Process -Id $PreviousPid -ErrorAction SilentlyContinue) {
  throw 'The previous application did not exit; update was not installed.'
}
if (-not (Test-Path -LiteralPath (Join-Path $StageDir 'AlmiqsAlBaseet.exe') -PathType Leaf)) {
  throw 'The verified new app is missing.'
}
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$movedOld = [System.Collections.Generic.List[string]]::new()
$movedNew = [System.Collections.Generic.List[string]]::new()
try {
  foreach ($name in $names) {
    $old = Join-Path $InstallDir $name
    if (Test-Path -LiteralPath $old) {
      Move-Item -LiteralPath $old -Destination (Join-Path $BackupDir $name) -ErrorAction Stop
      $movedOld.Add($name)
    }
  }
  foreach ($name in $names) {
    $new = Join-Path $StageDir $name
    if (Test-Path -LiteralPath $new) {
      Move-Item -LiteralPath $new -Destination (Join-Path $InstallDir $name) -ErrorAction Stop
      $movedNew.Add($name)
    }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'AlmiqsAlBaseet.exe'))) {
    throw 'New executable is missing after installation.'
  }
}
catch {
  foreach ($name in $movedNew) {
    $path = Join-Path $InstallDir $name
    if (Test-Path -LiteralPath $path) {
      Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
  foreach ($name in $movedOld) {
    $old = Join-Path $BackupDir $name
    if (Test-Path -LiteralPath $old) {
      Move-Item -LiteralPath $old -Destination (Join-Path $InstallDir $name) -ErrorAction SilentlyContinue
    }
  }
  throw
}
if (-not $NoRestart) {
  Start-Process -FilePath (Join-Path $InstallDir 'AlmiqsAlBaseet.exe') -WorkingDirectory $InstallDir
}
'''


def create_apply_script(staged_app: str | Path) -> Path:
    staged = Path(staged_app).resolve()
    script = staged.parent.parent / "apply_update.ps1"
    script.write_text(POWERSHELL_APPLY, encoding="utf-8")
    return script


def start_installer_after_exit(
    staged_app: str | Path,
    install_dir: str | Path,
    *,
    previous_pid: int | None = None,
    popen: Callable = subprocess.Popen,
) -> object:
    """Start an external PowerShell process; UI must exit afterward.

    Only known application binary paths are replaced. The output folder and
    all other non-application content remain untouched. A backup is retained.
    """
    if sys.platform != "win32":
        raise UpdateError("التثبيت الآلي متاح فقط على نظام Windows.")
    staged = Path(staged_app).resolve()
    install = Path(install_dir).resolve()
    if not (staged / "AlmiqsAlBaseet.exe").is_file():
        raise UpdateError("ملف البرنامج الجديد مفقود.")
    if not (install / "AlmiqsAlBaseet.exe").is_file():
        raise UpdateError("هذه ليست نسخة Windows محمولة معتمدة.")
    if staged == install or install in staged.parents or staged in install.parents:
        raise UpdateError("مجلد التحديث متداخل مع مجلد البرنامج.")
    script = create_apply_script(staged)
    backup = install / f".backup-before-update-{staged.parent.parent.name}"
    if backup.exists():
        raise UpdateError("يوجد مجلد نسخ احتياطي سابق بنفس الاسم.")
    command = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
        "Bypass", "-File", str(script),
        "-InstallDir", str(install),
        "-StageDir", str(staged),
        "-PreviousPid", str(previous_pid or os.getpid()),
        "-BackupDir", str(backup),
    ]
    return popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
