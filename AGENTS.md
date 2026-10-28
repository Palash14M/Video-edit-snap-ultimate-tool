# Working on Short Studio

This checkout is already an isolated cloud task. Use it directly; do not create a worktree unless the user requests one.

Read `docs/superpowers/specs/2026-10-28-short-studio-design.md`, `docs/features.json`, and `docs/PROGRESS.md` first. The complete 129-feature scope is retained in the registry. Never mark a feature implemented because a button, route skeleton or provider interface exists. Record actual tests and unresolved dependencies.

The user authorized autonomous implementation and repository upload, prefers sequential verified phases, open source, a calm editable UI, private single-owner use, and 720p–1080p clips. Current requirements override earlier storage plans: no Google Drive or Google Console, no permanent media library; persist URL history only. Keep video files temporary and delete them on expiry/restart. Never request account passwords, browser cookies or secret values in chat.

Run `uv sync --frozen --extra dev` (use a writable UV_CACHE_DIR if needed), then `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check studio tests`. Real-media tests require FFmpeg and FFprobe. API tests need local event-loop sockets; sandbox-denied sockets require the supported escalation, not code workarounds. Browser tests use the running app with `STUDIO_TEST_URL` and `STUDIO_TEST_PASSWORD`, then `npm ci && npm run test:browser`; never commit a real password. Production frontend has no Node runtime requirement.

Keep all HTTP endpoints private except health/login/static shell. No external paid providers, publishing or deployment claims without the actual necessary configuration and evidence. Use argument arrays and input format/protocol restrictions for FFmpeg; no shell interpolation or arbitrary URL ingestion. Preserve queue, upload, duration, export and expiry limits. Show actual errors and progress; do not generate sample clips or fake AI results in production UI.
