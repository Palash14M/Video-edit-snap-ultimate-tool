# Private Short Studio Implementation Plan

> **For agentic workers:** Execute task-by-task with tests and fresh review. The user already authorized autonomous execution and all routine decisions.

**Goal:** Deliver a real private video editing workflow and maintain complete traceability of all 129 requirements.

**Architecture:** FastAPI static app plus serial background jobs, FFmpeg, yt-dlp and optional local speech models. Temporary media and edit state, durable URL history only.

**Tech Stack:** Python 3.12, FastAPI, vanilla ES modules, FFmpeg, yt-dlp, pytest and Playwright.

**Spec:** docs/superpowers/specs/2026-10-28-short-studio-design.md

## Global Constraints

- Open source first; no paid service use without authorization.
- Keep only previous input URLs persistently; temporary media expires.
- No fake AI results or inactive controls presented as working.
- Track every original numbered requirement.
- Calm editable theme, accessible responsive interface, single owner.

## Review Focus

- Hostile URLs and filenames cannot fetch internal network resources or escape the media directory.
- Export timings must be finite, ordered within each segment and inside the source duration.
- Failed jobs must preserve useful errors and permit another job.
- Media without audio and portrait/odd-size videos must export correctly.
- Expiry, cancellation and restarts must not leave jobs permanently stuck or expose source downloads.

### Task 1: Media engine

Files: `studio/media.py`, `tests/test_media.py`.
Interfaces: `probe(path) -> dict`; `render(source, output, options, progress, cancelled) -> None`; `import_url(url, directory, progress, cancelled) -> Path`.
- [ ] Write tests using actual generated FFmpeg media for duration, concatenation, crop/pad ratios, captions, audio filters and invalid input; observe failures.
- [ ] Implement bounded subprocess operations with argument arrays and cancellation.
- [ ] Run `python -m pytest tests/test_media.py -q` and inspect real media probes.

### Task 2: Private API and job lifecycle

Files: `studio/app.py`, `studio/jobs.py`, `tests/test_api.py`.
Interfaces: `/api/health`, `/api/session`, `/api/projects`, `/api/projects/{id}`, `/api/projects/{id}/export`, `/api/jobs/{id}`, `/api/jobs/{id}/cancel`, `/api/clips/{id}`, `/api/history`, `/api/capabilities`.
- [ ] Write failing TestClient tests for authentication, uploads, range previews, export, invalid timings, cancellation and expiry.
- [ ] Implement one bounded worker, random identifiers and media cleanup.
- [ ] Run full pytest with a real import/export cycle and inspect output.

### Task 3: Browser editor

Files: `studio/static/index.html`, `studio/static/app.js`, `studio/static/theme.css`, `tests/browser.spec.js`.
- [ ] Write browser checks for the source form, real upload/export and mobile layout.
- [ ] Implement source URL/upload, progress, player, editable segments, aspect ratios, caption/text/audio controls, clip download and URL history.
- [ ] Run browser tests on desktop and mobile, inspect screenshots and fix failures.

### Task 4: AI and complete scope registry

Files: `studio/analysis.py`, `docs/features.json`, `docs/FEATURES.md`, `tests/test_analysis.py`.
- [ ] Record all 129 entries and distinguish implemented, blocked and pending using evidence.
- [ ] Add real optional speech transcription and transcript-based editing where models can be verified.
- [ ] List precise external prerequisites for blocked tasks; do not fake outputs.

### Task 5: Handoff and publication

Files: `README.md`, deployment files, reproducible setup instructions.
- [ ] Run full test suite and fresh review, exercise saved startup instructions.
- [ ] Commit and push to authorized GitHub repository without force or overwriting remote work.
- [ ] Save reusable environment configuration and report actual completion and blockers.
