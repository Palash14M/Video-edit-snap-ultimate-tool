# Private Short Studio design

The user authorized autonomous implementation and GitHub upload with “confirmed, start”. Their 129-feature list is required product scope, delivered in verified phases. This authorization replaces further design approval. No invented completion claims or simulated AI outputs.

## Product and constraints

Private browser video editor, one owner across devices, practical 720p–1080p H.264 MP4. Calm editable theme, consistent 8px spacing, accessible controls, responsive layouts. URL-first YouTube input plus local-file support (required feature 114). No Google Console, Drive integration, permanent video library, or source download. Keep only previous input URLs persistently; media and editing state expire. Advanced features stay visibly unavailable until implemented and verified, never silently omitted. Original numbered list must remain in a coverage manifest.

## Approach

Use one self-hostable FastAPI application, static HTML/CSS/JavaScript, FFmpeg rendering, yt-dlp ingestion, and optional locally installed speech models. A separate bounded background thread runs serial CPU-heavy jobs; HTTP and editor interactions stay responsive. No paid provider is used without separate authorization. Open-source software is free; permanent cloud CPU/GPU hosting is not guaranteed free. No installed chat plugin is assumed to be a production application backend.

Compared with browser-only processing this handles longer inputs without holding entire files in browser memory. Compared with a large microservice stack it is easier to run privately. Private YouTube download is not promised by YouTube Data API; private access needs an actual supported authenticated import mechanism and verification.

## Data and security

Private access uses a deployment access password exchanged for an HttpOnly SameSite session cookie, with no password in frontend source. Bind loopback by default, require explicit private access configuration for deployment. Media paths are random IDs; no user-controlled filesystem paths or arbitrary download URLs. yt-dlp destinations restricted to explicitly supported source hosts; reject playlists and excessive duration, size, traversal, and nonfinite timings. Limit upload size, workers and output durations. Temporary files have expiry cleanup; process arguments never use a shell. No public source download route. Metadata and edit state are transient except URL history.

## Phases

1. Real private application, ingestion, inspection, timeline selection and reordered multi-segment MP4 export; progress, cancellation, error recovery, aspect ratios, output qualities, captions/text/audio options; validate with actual media.
2. Transcription and model-backed highlight selection; word timing and text edits; run models only when available, report concrete model/network blockers.
3. Track and implement remaining editor, AI, branding, social, collaboration and integration requirements in the coverage registry. External services and multi-user scope conflicts must be explicit; features requiring credentials cannot be called working without tests.

## Verification

Tests must exercise real FFmpeg outputs and probe duration, resolution, audio streams, segment ordering, captions, bad input, private endpoints, job status, cleanup, cancellation and API errors. Browser checks cover import, empty/loading/error states, editing and exports, keyboard access and mobile overflow. No zero-test or placeholder checks.
