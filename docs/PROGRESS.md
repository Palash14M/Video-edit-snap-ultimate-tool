# Implementation ledger

Plan: `docs/superpowers/plans/2026-10-28-short-studio.md`.

User authorized autonomous build and GitHub upload. The original 129 features remain required scope; this is a verified core milestone, not completion of the whole product.

## Verified work

- Real FFmpeg media engine: trim, concatenate/reorder, speed, aspect/fit, audio controls, literal overlay and two caption styles. Tests inspect decoded frames, dimensions, duration and audio.
- Private API, random media IDs, finite bounded timing validation, one background worker, cancellation, source normalization, authenticated downloads, ZIP export, expiry/restart cleanup and URL-only retained history.
- Hard-cut scene detection and non-silent section detection, with explicit owner approval before applying selections. These are deterministic tools, not semantic AI or virality predictions.
- Responsive browser editor: real input/playback/edit/export/download workflow, theme preferences, error/progress states, job restoration, original project tracking and temporary autosave.
- Optional offline faster-whisper integration and transcript-passage selection implemented with clear unavailability states. Actual speech-model inference remains unverified because no model can be retrieved in this environment yet.
- Docker build and actual nonroot-container upload/render/download smoke test passed. Render template provided; no hosted deployment was performed.

## Review and corrections

- Reviewer reproduced incomplete queued-upload cancellation leaving source files: lifecycle finalizers now clear cancelled/failed source projects even before a task runs. Regression test passes.
- Refresh during an import and switching projects during export: pending jobs now exposed by API; UI restores polling and uses the originating project ID.
- Browser-incompatible uploaded codecs: inspection now normalizes real accepted media to H.264/AAC MP4; tests cover VP9/Opus conversion and actual playback.
- Export storage exhaustion: admission reserves output capacity, limits each project to 20 clips, and FFmpeg enforces a 512 MiB output cap with duration validation to reject truncation.
- FFmpeg input manifests could reference other files: input protocol/container restrictions now reject uploaded HLS/concat manifests. Tests reproduce local-file-reference input.
- HTTPS reverse proxies: explicit `STUDIO_PUBLIC_ORIGIN` controls origin checks and secure cookies; forwarded headers are not trusted blindly.
- Repeated browser tests reached the deliberate eight-project quota: tests now run their own disposable server and remove only their own resources. This was a test isolation defect; the server quota was retained.
- Direct caption-style verification caught an unescaped FFmpeg font-style separator in bold captions; corrected escaping and verified decoded pixels differ between clean and bold captions.

## Rulings

- Build the core as one self-hostable Python service with a dependency-free browser UI. This avoids an unnecessary frontend hosting/server split; long jobs stay in one bounded worker.
- Use latest explicit user storage/privacy decisions: no Drive, no permanent media library, no multi-user system. Twelve original features are retained as scope conflicts rather than silently implemented against those decisions.
- Normalize previews up to 1080p, retaining original aspect and avoiding enlargement of small inputs. This adds import processing time in exchange for reliable browser playback.
- Keep source/clip bytes and edit state for two hours, clear them on restart, retain only successful source URLs as history. Temporary source preview bytes are accessible to an authorized browser; hiding a download action is not DRM.
- No paid services, third-party publishing, personal account credentials, secret extraction, or public deployment were used.

## Concrete remaining blockers

- A real public YouTube check returned proxy HTTP 403. YouTube and media-CDN domains were saved in the environment draft; they are not applied merely by saving.
- A real request to the official faster-whisper model host returned proxy HTTP 403. Hugging Face model destinations were saved in that draft. No model weights or transcript results were invented.
- Private YouTube retrieval has no supported authenticated implementation here. Enabling a metadata API would not solve video download access.
- Generative video/audio, voice cloning, semantic multimodal clipping/tracking, external publishing and analytics need actual tested models/providers and, for account operations, supported authorization. The current free setup does not supply them.
- Always-on cloud CPU/GPU hosting has not been provisioned. Free software does not guarantee free compute for two-hour inputs.

The complete implementation/pending/blocked/conflict classification is maintained in `features.json` and `FEATURES.md`. All remaining items require more work; the feature registry itself does not implement them.

## Final milestone evidence

- Frozen install `uv sync --frozen --extra dev --extra ai` succeeded. The optional faster-whisper 1.2.1 runtime imports successfully; weights are still unavailable.
- `.venv/bin/python -m pytest -q`: 64 passed, 26 subtests passed; one upstream Starlette/AnyIO deprecation warning.
- `.venv/bin/ruff check studio tests`: passed. `node --check studio/static/app.js`: passed.
- `npm run test:browser`: 5 passed in 19.2 seconds in the independently run final suite. An isolated disposable server prevents contamination of the owner's state.
- Restarted the actual local application using its generated private password and verified health, unauthorized rejection, login, 129 feature entries and an empty transient workspace without printing credentials.
- External public YouTube import and speech-model host remain unverified because their actual requests returned policy HTTP 403. Saved network changes are a draft, not a running policy change or deployment.
- Final Docker rebuild passed as UID 10001: unauthorized rejection/login, normalized preview, bold-caption 720×1280 and clean-caption 1920×1080 exports with audio, rename/download filename, scene/silence jobs and a ZIP containing exactly two generated clips. Public deployment remains unperformed.

## Next verified stage: temporary assets and branding

Continued independent work while network access remained blocked. Added normalized raster logos, validated TTF/OTF fonts, normalized background music, custom caption/overlay colors, logo positions, music mixing/volume, and short fades. Assets are private to a temporary project, never a permanent media library. Enforced ten assets per project, 25 MiB uploads (5 MiB fonts), image pixel limits, media-format restrictions and cancellation cleanup.

TDD and verification: 97 backend tests and 38 subtests passed; Ruff and JavaScript syntax checks passed. The independent real Chromium suite passed all seven workflows in 28.6 seconds, including three actual asset uploads, branded video rendering/decoding, audio presence, restored selections, queued asset refresh and expanded mobile controls. Pixel tests verify logos/colors/fonts/fades; decoded audio tests verify music mixing and looping. A fresh read-only review found no new Important or Critical defects and independently checked queued-asset cleanup and extreme logo dimensions.

Coverage at this milestone: 30 implemented, 62 pending, 25 blocked and 12 scope conflicts, preserving every original requirement. The full product remains incomplete. No paid provider or public deployment has been used; the saved network draft remains unapplied in the running instance.

Final phase-two Docker verification passed against the updated code as unprivileged UID 10001: real source/logo/music/font uploads, branded export, normalized source and output playback, project removal, and feature registry counts. Decoded output measured 1.7 seconds at 320×240 with audio; sampled logo pixels were red, and decoded audio contained both the 440 Hz source and 880 Hz background music. No public deployment was performed.
