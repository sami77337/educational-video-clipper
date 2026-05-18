# Architecture Audit

Date: 2026-05-19

Scope: analysis only. This audit reviews the current project shape before adding more features. It does not change user-facing behavior, cutting behavior, YouTube download behavior, parsing behavior, export/report behavior, or packaging behavior.

## Current Structure Summary

The project is a Python/PySide6 Windows desktop app with a small root entry point and most app logic in `src/`.

- `app.py`: starts `QApplication` and opens `MainWindow`.
- `src/main_window.py`: builds the PySide6 UI, owns table widgets, source controls, classification controls, import/paste actions, validation orchestration, worker thread setup, log formatting, and output-folder opening. Current size: about 1,014 lines.
- `src/video_processor.py`: prepares YouTube/local sources, sanitizes project names, downloads with `yt-dlp`, resolves bundled/system ffmpeg, builds ffmpeg commands, cuts clips with and without exclusions, validates output duration, classifies clips, and creates export/report artifacts through `export_utils`. Current size: about 1,340 lines.
- `src/message_parser.py`: parses pasted WhatsApp/Telegram-style clip requests, including Arabic-Indic digits, continuation lines, begin/end blocks, and exclusions. Current size: about 472 lines.
- `src/import_utils.py`: imports Excel/CSV rows and normalizes times/exclusions.
- `src/validation.py`: validates clip rows, ranges, required text, and exclusions.
- `src/classification.py`: duration-based classification rules and validation.
- `src/exclusions.py`: parsing, validation, normalization, and kept-segment calculation for internal cuts.
- `src/export_utils.py`: ZIP creation, report creation, output folder validation, and report data models.
- `src/file_utils.py`: generic file helpers and filename sanitization.
- `tests/`: focused tests exist for classification, exclusions, export, import, main window behavior, message parsing, time parsing, validation, and video processing.
- Packaging/runtime files now live at the repository root: batch launchers, PyInstaller build helpers, desktop shortcut helpers, assets, and bundled `tools/ffmpeg.exe`.

The functional boundaries are already partly modular: parsing, import, classification, exclusions, validation, and export each have their own modules. The two modules that are becoming architectural bottlenecks are `main_window.py` and `video_processor.py`.

## Risks

- `src/video_processor.py` mixes several layers: source preparation, YouTube download, project-folder creation, ffmpeg command construction, ffmpeg execution, media probing, classification application, exclusion cutting, and export/report orchestration. This makes future cutting features risky because a change in one area can unintentionally affect another.
- `src/main_window.py` mixes UI construction with UI state, validation orchestration, table-to-model conversion, import/paste orchestration, processing worker setup, source selection, and logging. More UI features will make this file harder to test and review.
- YouTube behavior is operationally sensitive. Browser cookies, best video/audio format selection, progress hooks, bundled ffmpeg location, and yt-dlp error translation are all coupled in one download function.
- ffmpeg behavior is also sensitive. Command building, executable resolution, subprocess options, error summarization, output verification, segment cutting, concat file generation, and cleanup share one module.
- Export/report logic is mostly separate, but `ProcessingReportData` still carries legacy `reels_count` and `benefits_count` fields alongside dynamic classification counts. This is a compatibility risk during future multi-folder work.
- Packaging files are root-level and practical for users, but packaging logic is not isolated from runtime assumptions yet. Build scripts, shortcut scripts, bundled ffmpeg, and source launchers should remain documented and deliberately owned.
- Some names and labels are Arabic-facing and should be treated as product behavior. Refactors that normalize or rename text casually could break user trust even when code still runs.

## Files and Modules Becoming Too Large

- `src/video_processor.py` is the highest-risk module. It currently contains:
  - source request/result models
  - project output folder creation
  - YouTube validation/download/progress/cookie handling
  - local file validation/copy
  - clip definition construction
  - classification application
  - ffmpeg command construction
  - external tool resolution
  - subprocess execution and hidden-window flags
  - output duration probing/verification
  - exclusion segment cutting and concat
  - batch clip processing
  - export/report orchestration
- `src/main_window.py` is the second-highest risk module. It currently contains:
  - all UI layout sections
  - table row insertion and normalization
  - classification table management
  - paste-message conversion flow
  - Excel import flow
  - source validation flow
  - processing validation and worker setup
  - log formatting and output-folder opening
  - processing-state enable/disable rules
- `src/message_parser.py` is acceptable for now, but it is dense. It should be protected by tests before any parser cleanup because real-world Arabic message parsing has many edge cases.
- `src/export_utils.py` is medium-sized and mostly cohesive, but it includes both ZIP mechanics and report formatting. It can stay as-is until export formats grow.

## Recommended Target Structure

Keep the app simple, but split by responsibility rather than feature history:

```text
src/
  app_controller.py              # Orchestrates validation, source prep, processing, export
  ui/
    main_window.py               # Main window wiring only
    widgets/
      clip_table.py              # Clip table read/write/normalization helpers
      classification_table.py    # Classification table read/write helpers
    workers.py                   # QThread/QObject worker classes
  domain/
    models.py                    # Clip, source, processing, report dataclasses
    time_utils.py
    validation.py
    classification.py
    exclusions.py
  input/
    message_parser.py
    import_utils.py
  video/
    source.py                    # Source validation, local copy, project folder prep
    youtube.py                   # yt-dlp options, cookies, progress, download errors
    ffmpeg_commands.py           # Pure command builders
    ffmpeg_runner.py             # subprocess execution, tool resolution, error handling
    cutting.py                   # single-cut, exclusion-cut, concat, cleanup
    media_probe.py               # ffprobe/ffmpeg duration checks
  output/
    export_utils.py              # ZIP creation
    report.py                    # report data and report text
  packaging/
    paths.py                     # runtime asset/tool path helpers if needed
```

This is a target, not a required immediate layout. The existing flat `src/` structure can continue until a safe staged refactor is planned.

## Separation Recommendations

- Cutting:
  - Move ffmpeg command builders into a pure module first.
  - Move subprocess execution, hidden console flags, executable resolution, and concise ffmpeg errors into a runner module.
  - Move exclusion segment cutting and concat cleanup into a cutting module.
- YouTube download:
  - Isolate yt-dlp options, cookies-from-browser handling, progress hooks, and YouTube-specific error translation.
  - Keep format selection tests around best video plus best audio before moving code.
- Parsing:
  - Keep pasted-message parsing separate from UI. If it grows, split patterns/normalization from parser state-machine logic.
  - Do not rewrite parsing rules until regression tests from real team messages are expanded.
- Validation:
  - Keep table/domain validation outside UI.
  - Consider a single `ClipInput`/`ClipDefinition` boundary so UI, parser, Excel import, and processor use the same data shape.
- Export:
  - Separate ZIP creation from final report text when report requirements grow.
  - Remove legacy reels/benefits-specific report fields only after tests prove dynamic folder counts fully replace them.
- Settings:
  - Add a future settings module only when persistent settings exist. For now, UI state is transient and does not need a settings layer.
- Packaging:
  - Keep build scripts at root for user convenience.
  - Document ownership of `tools/ffmpeg.exe`, assets, and launchers.
  - If packaging logic grows, introduce a `packaging/` or `scripts/` folder without changing runtime behavior.

## Safe Refactor Stages

1. Baseline freeze:
   - Keep current behavior unchanged.
   - Run all tests and app startup before any extraction.
   - Add any missing regression tests for current YouTube options, ffmpeg commands, exclusions, ZIPs, reports, and UI table columns.

2. Pure extraction from `video_processor.py`:
   - Extract pure ffmpeg command builders first.
   - Extract project/source dataclasses only if import paths are updated mechanically.
   - Keep public function names re-exported or wrapped temporarily to avoid breaking tests and UI.

3. Runner extraction:
   - Move external tool resolution and subprocess execution into a dedicated ffmpeg runner.
   - Preserve exact command list behavior, UTF-8 subprocess settings, hidden Windows console behavior, and concise error messages.

4. YouTube extraction:
   - Move yt-dlp download options, browser-cookie selection, progress hook, bundled ffmpeg location, and error translation into a YouTube module.
   - Keep tests that assert best video plus best audio and cookies support.

5. UI decomposition:
   - Extract table read/write helpers from `MainWindow`.
   - Extract `ProcessingWorker` into a worker module.
   - Extract classification table helpers after preserving current default rows and Arabic validation logs.

6. Orchestration boundary:
   - Introduce an app/service controller only after processor and UI helpers are stable.
   - The controller should accept plain data and callbacks, not PySide widgets.

7. Export/report cleanup:
   - Split report formatting from ZIP creation if report output evolves.
   - Remove legacy reels/benefits fields only after dynamic classification report tests are explicit.

## Tests Needed Before Any Refactor

- Full existing test suite must stay green before and after each stage.
- UI smoke test that instantiates `MainWindow` and verifies:
  - clip table columns, including `استثناءات`
  - classification default rows
  - source selection enable/disable behavior
  - processing buttons disabled/enabled state
- Source preparation tests:
  - local file copy to `input.mp4`
  - sanitized project folder names
  - missing/empty YouTube URL and local file errors
  - yt-dlp options for best video plus best audio
  - browser cookies options for Chrome, Edge, Brave, and Firefox
- ffmpeg tests:
  - single-cut command construction
  - exclusion segment command construction
  - concat file escaping for Arabic paths and spaces
  - non-zero ffmpeg exit fails even if a partial output file exists
  - concise ffmpeg error output
  - missing ffmpeg Arabic error
  - temp segment cleanup on success and failure
- Parser/import tests:
  - real Arabic pasted-message examples with continuation lines, notes, parenthesized exclusions, and malformed spacing
  - Excel/CSV rows with and without optional `exclusions`
  - Arabic titles preserved
- Export/report tests:
  - dynamic classification folder ZIPs
  - complete ZIP includes all output folders
  - report includes rules, per-folder counts, ZIP paths, and clip exclusions
- Packaging smoke:
  - `app.py` starts
  - asset paths resolve in source mode
  - bundled `tools/ffmpeg.exe` can be resolved when present

## What Should Not Be Changed Yet

- Do not change user-facing Arabic labels or wording unless fixing a clear bug.
- Do not change cutting behavior, ffmpeg command semantics, output filenames, classification thresholds, or exclusion behavior during an architecture-only task.
- Do not change YouTube download behavior, format selection, browser cookies support, or progress/error messages during structural work.
- Do not rewrite the pasted-message parser without a larger corpus of real examples and regression tests.
- Do not introduce smart preflight, speed/fade/audio features, Excel enhancements, or packaging-as-EXE behavior as part of refactoring.
- Do not remove bundled ffmpeg or packaging helper scripts unless a separate packaging decision is made.
- Do not rename output folders, ZIP names, or report filenames during refactors.

## Conclusion

The current structure is not blocking small fixes, but it is starting to block safe feature growth. The main risk is not the flat folder layout itself; it is that `video_processor.py` and `main_window.py` now each own several responsibilities. The next safe step is to add regression coverage around the current behavior, then extract pure and low-risk pieces from `video_processor.py` before touching UI decomposition.
