# Internal Release Candidate Checklist

Date: 2026-05-19
Branch: `feature/internal-rc-verification-v1`

## Automated Verification

- Full test suite: passed, `376 passed`
- App startup smoke test: passed
- Release verification script: passed, `verify_release.bat`
- Build result: passed, output path reported as `dist\AlmiqsAlBaseet`
- Release package audit: passed
- Generated artifacts committed: no

## Verified Feature Areas

- Readiness check: covered by automated tests and app startup verification
- Smart validation: covered by automated tests
- Smart paste: covered by automated parser and UI tests
- Queue simulation: covered by automated queue model, UI, storage, validation, and dry-run tests
- Pre/post padding: covered by unit tests and local cutting regression tests
- Multiple exclusions: covered by parser/validation tests and local cutting regression tests
- Final report notes: covered by report tests for padding values and exclusion counts

## Queue Execution Status

The queue UI and queue simulation are present, but these areas are still not real execution:

- Queue real processing
- Queue real download/cutting

Queue actions must remain simulation-only until a later implementation phase.

## Manual Tests Still Required Before Sending To Team

- Run the built app on a clean Windows machine.
- Confirm the main window opens without a terminal or extra prompts.
- Process a short local MP4 with no exclusions.
- Process a local MP4 with pre/post padding enabled.
- Process a local MP4 with one internal exclusion.
- Process a local MP4 with multiple internal exclusions.
- Process a YouTube URL using the intended browser-cookie setting.
- Import clips from Excel and CSV files with Arabic titles.
- Paste a real WhatsApp/Telegram clip request and review the preview before applying.
- Confirm output folders, ZIP files, and `تقرير-القص.txt` are created as expected.
- Confirm Arabic filenames open normally on the target Windows machine.
- Confirm queue actions do not start real download/cutting.

## Notes

- `verify_release.bat` completed successfully and included full tests, app startup smoke, build, and release package audit.
- The release audit accepted the packaged `ffmpeg.exe` and the approved ffprobe fallback.
- No generated `dist/`, `build/`, cache, or temporary media files should be included in the PR.
