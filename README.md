# Private Short Studio

A private, open-source browser workspace for turning source videos into short MP4 clips. Built for one owner across devices, with a calm, editable interface, temporary video processing, and retained source-URL history.

**This is an early implementation of a 129-feature roadmap, not a completed OpusClip replacement.** Read [the feature registry](docs/FEATURES.md) for the complete original scope, dependencies, and conflicts with later requirements. A listed feature is not a promise that its backend is connected. The interface exposes actual capability status rather than fabricating AI output.

## Workflow

1. Open the private studio and enter its access password.
2. Import a supported public YouTube URL or upload a video you are authorized to process.
3. Preview the source and select the time ranges to keep. Add and reorder segments.
4. Choose the frame, output resolution, text/captions, and audio settings.
5. Export, wait for the real FFmpeg job, then download the finished MP4 clip.

The core targets 720p/1080p H.264 MP4 with AAC audio. Media inspection, rendering, job progress, cancellation, error states, and cleanup run on the application server. Transcription is an optional local-model capability; it is unavailable until the speech runtime and model are installed. Model-based features must not be mistaken for generative video, reliable virality predictions, voice cloning, publishing, or external editor integrations.

Inputs are normalized to a browser-compatible H.264/AAC MP4 preview before editing. Measured scene-cut detection and silence detection can propose source regions; you review and apply those proposals. Silence detection measures low audio energy, not whether a person is speaking. Generated clips can be renamed or downloaded together in a ZIP. Text, captions, frame fit, playback speed, mute/volume and deterministic noise-reduction filters are applied by the real renderer.

## Temporary assets and output branding

The editor supports uploaded logo images, background music and custom fonts. Real-media tests verify rendered pixels and decoded audio; browser acceptance tests cover uploading, selecting, rendering, and restoring temporary assets after refresh.

- Upload a raster logo, music file or self-contained TTF/OTF font to the current temporary project. SVG images and fonts with embedded SVG content are not supported.
- Choose a logo corner; adjust music volume; use custom caption/text colors and clean/bold caption styling. Uploaded music can loop to fill the exported duration and can be mixed with source audio or accompany a muted source.
- Select a short fade for segment transitions. A fade does not invent extra source footage or change the requested total timeline duration.
- Use media and fonts you have permission to use.

Limits: at most 10 assets per temporary project; 25 MiB per raster logo or music upload; 5 MiB per font; 16 million decoded pixels per logo; music duration at most ten minutes. Logos are normalized to PNG, bounded to 2048 pixels in each dimension, and stripped of metadata. Only the first frame of an animated image is used. Music is normalized to AAC, and fonts are validated and reserialized. Assets are restricted to their originating project, count toward temporary storage, and expire or are cleared with it. This does not create a permanent media library or saved brand-template system.

## Run locally

Prerequisites: Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and FFmpeg/ffprobe on `PATH`. FFmpeg must include H.264/AAC encoders and `drawtext` support. Install a normal Unicode font such as DejaVu Sans.

On Debian/Ubuntu the system dependencies are `ffmpeg` and `fonts-dejavu-core`. On other systems use their normal package managers and preserve package and TLS verification.

From the checkout:

```sh
uv sync --frozen --extra dev
.venv/bin/python -m studio
```

The server binds `127.0.0.1:8000` by default. Open that address in your own browser. Do not run multiple app workers against the same data directory: temporary jobs and sessions live in the single process.

At first start the app creates a random access password in `.runtime/access-password`, with restrictive local permissions. Read it privately on your own machine and enter it in the studio's login screen. Do not upload or send that file, tokens, or account passwords to anyone. Alternatively set `STUDIO_PASSWORD` through your deployment's secure environment settings before startup; it must contain at least 16 characters. No default/shared password is shipped.

Configuration:

| Variable | Purpose |
| --- | --- |
| `STUDIO_PASSWORD` | Private studio password; at least 16 characters. Set securely, never in committed files. |
| `STUDIO_HOST` | Bind address; defaults to `127.0.0.1`. Containers require `0.0.0.0`. |
| `PORT` | Listening port; defaults to `8000`. |
| `STUDIO_DATA_DIR` | Runtime directory; defaults to `.runtime` in the checkout. Keep it private and outside public/static paths. |
| `STUDIO_PUBLIC_ORIGIN` | Optional explicit external HTTPS origin for a custom-domain deployment, for example `https://your-private-host.example`; no trailing slash or path. Takes precedence over Render's automatically provided `RENDER_EXTERNAL_URL`. Used for origin validation and secure cookies without trusting forwarded headers. |
| `STUDIO_WHISPER_MODEL` | Optional local faster-whisper model directory; no implicit model download. |

## Temporary media, privacy, and limits

- Only previous successful source URLs and their timestamps persist as application history. The access-password file is local authentication configuration.
- Source bytes, clips, captions, timeline state and other project state are temporary. They expire after two hours and are cleared on application restart. Download wanted clips before expiry. Background cleanup runs periodically; in-flight jobs may delay deletion until the job ends.
- Clearing a project removes its temporary files. Cancel active processing before clearing it.
- Current guards limit source uploads to 1 GiB, source duration to two hours, a rendered clip to ten minutes, and generated clips to 20 per temporary project. A 2 GiB temporary-storage admission budget and export-space reservations limit concurrent work; video processing still needs enough disk space and RAM for source, normalized preview, and output files.
- A source preview must deliver video bytes to the browser. Hiding the source download button is a UI choice, not DRM or a guarantee that a browser owner cannot save preview bytes. Only generated clips have explicit download actions.
- One owner can sign in from different devices, but all devices use the same private workspace. No separate team accounts, public share links, Google Drive connection, or permanent media library are configured.
- Source URLs are retained; the app does not store Google passwords, private YouTube browser cookies, or social login sessions.

## Optional speech models

Install the optional speech runtime:

```sh
uv sync --frozen --extra dev --extra ai
```

Obtain a compatible faster-whisper model from its official/maintainer source, observe its licence and artifact integrity, and set `STUDIO_WHISPER_MODEL` to the verified local directory. Restart the studio. The model and local runtime must be usable before the app enables transcription. Supported languages and accuracy are those of the actual model. Large models need considerable RAM or GPU resources; installing a package alone is not validation of transcription quality.

## YouTube and external services

Public YouTube ingestion uses yt-dlp. A successful local-file test does not prove public URL import works in a given cloud network: source restrictions, bot checks, extractor changes and outbound-network policy can prevent retrieval. The app reports these failures. It does not bypass private access.

Private YouTube imports remain blocked until a supported authenticated retrieval method is configured and verified. The YouTube Data API does not generally provide arbitrary video downloads; enabling that API is not sufficient. No Google Console setup is required for the open-source core, and no cookie/password sharing workflow is included.

Stock media, generated B-roll, voice cloning, dubbing, social publishing/analytics, team systems, and external editor/automation integrations need additional verified work and, where applicable, provider authorization. See [all 129 requirements](docs/features.json). No paid service or public deployment is automatically created by starting this repository.

## Tests

From the checkout:

```sh
uv sync --frozen --extra dev
.venv/bin/python -m pytest -q
```

Media tests generate small real FFmpeg fixtures and inspect outputs. Tests cover invalid inputs and private API behavior as well as successful editing. No real social-account credentials are required for the core suite.

Browser tests:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

By default Playwright starts an isolated loopback test server on port 8765 with a temporary runtime directory and a test-only password. Do not reuse that password on a remote deployment. To test a separately running server instead, set `STUDIO_TEST_URL` and `STUDIO_TEST_PASSWORD` securely to match it. Browser tests are development dependencies; they are not needed for serving the website.

## Self-hosting and containers

The Docker image installs FFmpeg and fonts, installs locked Python dependencies, copies the app, and runs it as an unprivileged user. Supply a strong `STUDIO_PASSWORD` in your secure runtime environment. The image does not contain a personal credential or AI model.

```sh
docker build -t private-short-studio .
docker run --rm -p 127.0.0.1:8000:8000 --env STUDIO_PASSWORD private-short-studio
```

The example forwards an already-set `STUDIO_PASSWORD` from your shell; it does not print its value or place it in command history. Without a mounted data directory, URL history is lost when the container is removed, which is acceptable for an ephemeral deployment. Never mount permanent media storage merely to keep temporary projects alive.

In a managed environment with an HTTPS inspection proxy, keep the platform's proxy settings and build with its combined CA trust bundle as an ephemeral BuildKit secret:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t private-short-studio .
```

The Dockerfile uses that optional mount only while pip/uv fetch dependencies. It does not copy the session CA into the image or disable TLS verification. Ordinary builds without an inspection proxy can omit the secret. Runtime network clients in such managed environments likewise need the platform-approved read-only CA mount and client trust configuration; credentials and session trust must not be baked into the image.

The app needs one long-running server process with FFmpeg, temporary filesystem space, and background execution. It is **not** a suitable all-in-one Vercel serverless function. Vercel may host a separate future frontend, but does not replace the video worker.

`render.yaml` supplies an optional single-instance Render Docker blueprint with no persistent disk. It is a template, not a deployed or verified public service. Its free instance is suitable only for assessing small inputs if the provider supports the workload; larger videos or AI will often exceed free memory, CPU, disk, or time limits. Review provider limits and pricing yourself before creating resources. Free software does not guarantee free always-on cloud processing.

On Render, the app automatically uses the provider's `RENDER_EXTERNAL_URL` for HTTPS origin validation and secure cookies; no hostname needs to be entered before deployment. For another reverse proxy or a custom domain, set `STUDIO_PUBLIC_ORIGIN` to the exact HTTPS origin you open in your browser, with no trailing slash or path. This explicit setting takes precedence over the assigned Render hostname. Forwarded request headers are not trusted. Check login, import, preview, export and cleanup through the actual deployed HTTPS address before treating a host as ready.

Deployment requires an authenticated hosting account. Repository push access alone cannot provision a Render service. For agent-operated deployment, add `RENDER_API_KEY` securely in the cloud environment settings, scoped by the proxy to `api.render.com`; never paste it into chat or commit it. The environment must allow `api.render.com` and the assigned service host. These requirements have been saved in the environment draft, but saving a draft does not apply networking or supply the credential.

## Appearance

Shared spacing, typography, colors and component geometry live in `studio/static/theme.css`. The Settings page supports browser-local appearance preferences. Styling can change later without rewriting the media pipeline.

## Development scope

The design and phased plan are in [docs/superpowers](docs/superpowers). The original scope remains traceable in [docs/FEATURES.md](docs/FEATURES.md). A working manual editor is not evidence that all AI, social and collaboration requirements are complete; each must earn its own verification.
