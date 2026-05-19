# Internal RC Build Result

Date/time: 2026-05-19 21:58:46 +03:00

## Verification Summary

- Full test suite: passed, 376 tests.
- App startup smoke: passed through `verify_release.bat`.
- Build: passed through `build_app_ci.bat`.
- Release audit: passed for `dist/AlmiqsAlBaseet`.

## Package Output

Output path:

```text
dist/AlmiqsAlBaseet
```

Confirmed runtime package contents:

- `AlmiqsAlBaseet.exe` exists.
- `_internal` exists.
- `ffmpeg.exe` exists.
- `ffprobe.exe` is not packaged, and the release audit accepted the approved ffmpeg fallback.
- `README_AR.txt` is not currently expected by the audit.

Confirmed forbidden source/developer files are not present in the package:

- `app.py`
- `src`
- `tests`
- `requirements.txt`
- `run_app.bat`
- `build_app.bat`
- `build_app_ci.bat`
- `.pytest_cache`
- `__pycache__`

## Manual Tests Still Required

- Run the packaged EXE on a clean Windows machine.
- Verify local video cutting with a short sample.
- Verify YouTube download with the supported browser-cookie options when needed.
- Verify Smart Paste preview with a real team message.
- Verify Excel/CSV import with Arabic titles.
- Verify pre/post padding and multiple exclusions on real clips.
- Verify ZIP output and final report files after a complete processing run.
- Confirm queue actions remain simulation-only until real queue processing is intentionally implemented.

## Notes

- No generated `dist/`, `build/`, cache folders, or generated `.spec` files should be committed.
- This document records the internal release candidate build verification only; no application behavior was changed.
