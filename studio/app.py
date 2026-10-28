"""Private HTTP application. Video bytes expire; only URL history persists."""
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, RLock, Thread
import hmac
import json
import os
import re
import secrets
import shutil
import time
import uuid
import zipfile

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .jobs import Jobs
from .media import MediaError, import_url, prepare_preview, probe, render, validate_url

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 1024 * 1024 * 1024
TTL = 2 * 3600


class Login(BaseModel):
    password: str = Field(max_length=1024)


class Source(BaseModel):
    url: str = Field(max_length=2048)


class Segment(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class Caption(Segment):
    text: str = Field(max_length=500)


class Export(BaseModel):
    model_config = ConfigDict(extra='forbid')
    segments: list[Segment] = Field(min_length=1, max_length=50)
    aspect: str = 'original'
    resolution: int = 720
    fit: str = 'contain'
    mute: bool = False
    enhance_audio: bool = False
    volume: float = Field(default=1, ge=0, le=2, allow_inf_nan=False)
    speed: float = Field(default=1, ge=.5, le=2, allow_inf_nan=False)
    text: str = Field(default='', max_length=500)
    captions: list[Caption] = Field(default_factory=list, max_length=500)
    caption_style: str = 'clean'
    transition: str = 'none'
    caption_color: str = '#FFFFFF'
    caption_background: str = '#000000'
    text_color: str = '#FFFFFF'
    music_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    logo_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    font_asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    music_volume: float = Field(default=.2, ge=0, le=1, allow_inf_nan=False)
    logo_position: str = 'top-right'

    @field_validator('caption_color', 'caption_background', 'text_color')
    @classmethod
    def color_valid(cls, value):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('Choose a six-digit hexadecimal color.')
        return value.upper()

    @field_validator('transition')
    @classmethod
    def transition_valid(cls, value):
        if value not in ('none', 'fade'):
            raise ValueError('Choose no transition or a short fade.')
        return value

    @field_validator('logo_position')
    @classmethod
    def logo_position_valid(cls, value):
        if value not in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
            raise ValueError('Choose one of the four logo corners.')
        return value

    @field_validator('aspect')
    @classmethod
    def aspect_valid(cls, value):
        if value not in ('original', '9:16', '1:1', '16:9'):
            raise ValueError('Unsupported aspect ratio')
        return value

    @field_validator('resolution')
    @classmethod
    def resolution_valid(cls, value):
        if value not in (720, 1080):
            raise ValueError('Choose 720p or 1080p')
        return value

    @field_validator('fit')
    @classmethod
    def fit_valid(cls, value):
        if value not in ('contain', 'cover'):
            raise ValueError('Choose contain or cover')
        return value

    @field_validator('caption_style')
    @classmethod
    def style_valid(cls, value):
        if value not in ('clean', 'bold'):
            raise ValueError('Unsupported caption style')
        return value


class Rename(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    edits: Export | None = None


class Suggest(BaseModel):
    duration: float = Field(default=30, ge=5, le=180, allow_inf_nan=False)
    keywords: str = Field(default='', max_length=200)


def create_app(data_dir: Path | None = None, password: str | None = None):
    data_dir = Path(data_dir or os.environ.get('STUDIO_DATA_DIR', ROOT / '.runtime')).resolve()
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if password is None:
        password = os.environ.get('STUDIO_PASSWORD')
        if not password:
            credential_file = data_dir / 'access-password'
            if not credential_file.exists():
                credential_file.touch(mode=0o600)
                credential_file.write_text(secrets.token_urlsafe(24))
            password = credential_file.read_text().strip()
    if len(password) < 16:
        raise RuntimeError('STUDIO_PASSWORD must be at least 16 characters.')
    # Unique per boot: no stale media or authenticated sessions survive a restart.
    media_root = data_dir / 'temporary'
    if media_root.exists():
        shutil.rmtree(media_root)
    media_root.mkdir(mode=0o700)
    sessions, attempts, projects, clips = {}, {}, {}, {}
    state_lock = RLock()
    jobs = Jobs()
    stop_cleanup = Event()
    history_file = data_dir / 'urls.json'
    public_origin = os.environ.get('STUDIO_PUBLIC_ORIGIN', '').rstrip('/')
    export_reservations = {}

    def project_public(p):
        result = {k: v for k, v in p.items() if k not in ('source', 'directory') and not k.startswith('_')}
        with jobs.lock:
            result['active_job'] = next((j.public() for j in jobs.entries.values()
                                        if j.project_id == p['id'] and j.status in ('queued', 'running')), None)
        return result

    def used_bytes():
        total = 0
        for path in media_root.rglob('*'):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                pass
        return total

    def project_get(project_id):
        with state_lock:
            project = projects.get(project_id)
            if not project or project['expires_at'] < time.time():
                raise HTTPException(404, 'Project expired or not found. Import the video again.')
            return project

    def remove_project(project_id):
        with jobs.lock:
            active = [j for j in jobs.entries.values()
                      if j.project_id == project_id and j.status in ('queued', 'running')]
        if active:
            raise HTTPException(409, 'Cancel the active job before clearing this project.')
        with state_lock:
            project = projects.pop(project_id, None)
            if project:
                for clip in project['clips']:
                    clips.pop(clip['id'], None)
                shutil.rmtree(project['directory'], ignore_errors=True)

    def cleanup():
        while not stop_cleanup.wait(30):
            with state_lock:
                expired = [p['id'] for p in projects.values() if p['expires_at'] < time.time()]
            for project_id in expired:
                try:
                    remove_project(project_id)
                except HTTPException:
                    pass
            with jobs.lock:
                jobs.entries = {k: j for k, j in jobs.entries.items()
                                if j.status in ('queued', 'running') or j.created_at + TTL > time.time()}
            with state_lock:
                for key in list(sessions):
                    if sessions[key] < time.time():
                        del sessions[key]

    @asynccontextmanager
    async def lifespan(app):
        cleaner = Thread(target=cleanup, daemon=True)
        cleaner.start()
        yield
        stop_cleanup.set()
        cleaner.join(timeout=2)
        jobs.close()
        shutil.rmtree(media_root, ignore_errors=True)

    app = FastAPI(title='Private Short Studio', lifespan=lifespan)
    app.state.jobs = jobs
    app.state.projects = projects

    @app.middleware('http')
    async def private_access(request: Request, call_next):
        path = request.url.path
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            expected = public_origin or f'{request.url.scheme}://{request.url.netloc}'
            if origin and origin != expected:
                return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        if path.startswith('/api/') and path not in ('/api/session', '/api/health'):
            session = request.cookies.get('studio_session', '')
            if sessions.get(session, 0) <= time.time():
                return JSONResponse({'detail': 'Sign in to your private studio.'}, status_code=401)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'ffmpeg': bool(shutil.which('ffmpeg'))}

    @app.get('/api/session')
    def session(request: Request):
        return {'authenticated': sessions.get(request.cookies.get('studio_session', ''), 0) > time.time()}

    @app.post('/api/session')
    def login(payload: Login, request: Request):
        peer = request.client.host if request.client else 'local'
        now = time.time()
        attempts[peer] = [t for t in attempts.get(peer, []) if t > now - 60]
        if len(attempts[peer]) >= 10:
            raise HTTPException(429, 'Too many attempts. Wait one minute.')
        attempts[peer].append(now)
        if not hmac.compare_digest(payload.password.encode(), password.encode()):
            raise HTTPException(401, 'Incorrect studio password.')
        token = secrets.token_urlsafe(32)
        sessions[token] = now + 12 * 3600
        attempts[peer] = []
        response = JSONResponse({'authenticated': True})
        response.set_cookie('studio_session', token, httponly=True, samesite='strict',
                            secure=public_origin.startswith('https://') or request.url.scheme == 'https',
                            max_age=12 * 3600)
        return response

    @app.delete('/api/session')
    def logout(request: Request):
        sessions.pop(request.cookies.get('studio_session', ''), None)
        response = JSONResponse({'authenticated': False})
        response.delete_cookie('studio_session')
        return response

    @app.get('/api/capabilities')
    def capabilities():
        from .analysis import model_available
        available = model_available()
        return {'ffmpeg': bool(shutil.which('ffmpeg')), 'transcription': available,
                'ai_reason': '' if available else 'Install faster-whisper and provide a local STUDIO_WHISPER_MODEL directory.',
                'private_youtube': False, 'automatic_highlights': available,
                'expires_after_hours': 2}

    @app.get('/api/features')
    def features():
        return json.loads((ROOT / 'docs' / 'features.json').read_text())

    def read_history():
        if not history_file.exists():
            return []
        try:
            return json.loads(history_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    @app.get('/api/history')
    def history():
        return read_history()

    @app.delete('/api/history')
    def clear_history():
        history_file.unlink(missing_ok=True)
        return {'cleared': True}

    def new_project(name, url=None):
        with state_lock:
            if len(projects) >= 8:
                raise HTTPException(429, 'Clear a temporary project before importing another.')
            if used_bytes() + len(export_reservations) * (MAX_UPLOAD // 2) > 2 * MAX_UPLOAD:
                raise HTTPException(507, 'Temporary storage is full. Clear an existing project.')
            project_id = uuid.uuid4().hex
            directory = media_root / project_id
            directory.mkdir(mode=0o700)
            project = {'id': project_id, 'name': name, 'url': url, 'media': None, 'clips': [],
                       'assets': [], '_asset_files': {}, '_asset_pending': set(),
                       'transcript': [], 'edits': None, 'created_at': time.time(),
                       'expires_at': time.time() + TTL, 'directory': directory, 'source': None}
            projects[project_id] = project
            return project

    def queue(kind, project, task):
        def finalize(job):
            if kind in ('import', 'inspect') and job.status in ('cancelled', 'failed'):
                with state_lock:
                    projects.pop(project['id'], None)
                    shutil.rmtree(project['directory'], ignore_errors=True)
        try:
            return jobs.submit(kind, project['id'], task, finalize)
        except ValueError as exc:
            raise HTTPException(429, str(exc)) from exc

    @app.get('/api/projects')
    def project_list():
        with state_lock:
            return [project_public(p) for p in projects.values() if p['expires_at'] > time.time()]

    @app.post('/api/projects/import', status_code=202)
    def import_project(payload: Source):
        try:
            url = validate_url(payload.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        project = new_project('YouTube video', url)

        def task(job, progress):
            try:
                source = import_url(url, project['directory'], progress, job.cancel_event.is_set)
                preview = prepare_preview(source, project['directory'], progress, job.cancel_event.is_set)
                project.update(source=preview, media=probe(preview))
                if source != preview:
                    source.unlink(missing_ok=True)
                with state_lock:
                    previous = [row for row in read_history() if row['url'] != url]
                    previous.insert(0, {'url': url, 'used_at': time.time()})
                    temporary = history_file.with_suffix('.tmp')
                    temporary.write_text(json.dumps(previous[:100]))
                    temporary.replace(history_file)
            except Exception:
                shutil.rmtree(project['directory'], ignore_errors=True)
                projects.pop(project['id'], None)
                raise
        try:
            job = queue('import', project, task)
        except HTTPException:
            remove_project(project['id'])
            raise
        return {'job_id': job['id']}

    @app.post('/api/projects/upload', status_code=202)
    async def upload_project(file: UploadFile = File(...)):
        # Ignore filename path components and extensions. ffprobe inspects actual bytes.
        project = new_project(Path(file.filename or 'Uploaded video').name[:100])
        source = project['directory'] / 'source.media'
        size = 0
        try:
            with source.open('wb') as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, 'Maximum file size is 1 GB.')
                    with state_lock:
                        if used_bytes() + len(export_reservations) * (MAX_UPLOAD // 2) + len(chunk) > 2 * MAX_UPLOAD:
                            raise HTTPException(507, 'Temporary storage is full. Clear a project first.')
                    target.write(chunk)
            if size == 0:
                raise HTTPException(422, 'Choose a non-empty video.')
        except Exception:
            remove_project(project['id'])
            raise
        finally:
            await file.close()

        def task(job, progress):
            try:
                media = probe(source)
                if media['duration'] > 7200:
                    raise MediaError('Maximum source duration is two hours.')
                preview = prepare_preview(source, project['directory'], progress, job.cancel_event.is_set)
                project.update(source=preview, media=probe(preview))
                if source != preview:
                    source.unlink(missing_ok=True)
            except Exception:
                shutil.rmtree(project['directory'], ignore_errors=True)
                projects.pop(project['id'], None)
                raise
        try:
            job = queue('inspect', project, task)
        except HTTPException:
            remove_project(project['id'])
            raise
        return {'job_id': job['id']}

    @app.get('/api/projects/{project_id}')
    def get_project(project_id: str):
        return project_public(project_get(project_id))

    @app.post('/api/projects/{project_id}/assets/{kind}', status_code=202)
    async def upload_asset(project_id: str, kind: str, file: UploadFile = File(...)):
        project = project_get(project_id)
        if kind not in ('logo', 'music', 'font'):
            await file.close()
            raise HTTPException(422, 'Choose a logo image, background music, or a custom font.')
        asset_id = uuid.uuid4().hex
        with state_lock:
            if len(project['assets']) + len(project['_asset_pending']) >= 10:
                await file.close()
                raise HTTPException(429, 'Maximum 10 temporary assets per project.')
            project['_asset_pending'].add(asset_id)
        directory = project['directory'] / 'assets' / asset_id
        directory.mkdir(parents=True, mode=0o700)
        incoming = directory / 'input.bin'

        def finalize(job):
            with state_lock:
                project['_asset_pending'].discard(asset_id)
                if job is None or job.status in ('failed', 'cancelled'):
                    project['_asset_files'].pop(asset_id, None)
                    project['assets'] = [asset for asset in project['assets'] if asset['id'] != asset_id]
                    shutil.rmtree(directory, ignore_errors=True)
        try:
            total = 0
            with incoming.open('wb') as target:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 25 * 1024 * 1024:
                        raise HTTPException(413, 'Maximum asset size is 25 MB (5 MB for fonts).')
                    with state_lock:
                        if used_bytes() + len(export_reservations) * (MAX_UPLOAD // 2) + len(chunk) > 2 * MAX_UPLOAD:
                            raise HTTPException(507, 'Temporary storage is full. Clear a project first.')
                    target.write(chunk)
            if not total:
                raise HTTPException(422, 'Choose a non-empty media asset.')
        except Exception:
            finalize(None)
            raise
        finally:
            await file.close()

        def task(job, progress):
            from .assets import prepare_asset
            try:
                prepared = prepare_asset(incoming, directory, kind, job.cancel_event.is_set)
                with state_lock:
                    project['_asset_files'][asset_id] = prepared['path']
                    project['assets'].append({'id': asset_id, 'kind': kind,
                                              'name': Path(file.filename or kind).name[:100],
                                              **{key: value for key, value in prepared.items()
                                                 if key not in ('path', 'kind', 'name')}})
            finally:
                incoming.unlink(missing_ok=True)
        try:
            job = jobs.submit('asset-upload', project_id, task, finalize)
        except ValueError as exc:
            finalize(None)
            raise HTTPException(429, str(exc)) from exc
        return {'job_id': job['id']}

    @app.patch('/api/projects/{project_id}')
    def update_project(project_id: str, payload: Rename):
        project = project_get(project_id)
        if payload.name:
            project['name'] = payload.name.strip() or 'Untitled clip'
        if payload.edits:
            validate_export(project, payload.edits)
            project['edits'] = payload.edits.model_dump()
        return project_public(project)

    @app.delete('/api/projects/{project_id}')
    def delete_project(project_id: str):
        project_get(project_id)
        remove_project(project_id)
        return {'deleted': True}

    @app.get('/api/projects/{project_id}/preview')
    def preview(project_id: str):
        project = project_get(project_id)
        if not project['source']:
            raise HTTPException(409, 'Source is still processing.')
        return FileResponse(project['source'], media_type='video/mp4', content_disposition_type='inline')

    def validate_export(project, payload):
        if not project['media']:
            raise HTTPException(409, 'Wait for video inspection to finish.')
        for kind in ('music', 'logo', 'font'):
            asset_id = getattr(payload, f'{kind}_asset_id')
            if asset_id and not any(asset['id'] == asset_id and asset['kind'] == kind for asset in project['assets']):
                raise HTTPException(422, f'The selected {kind} asset does not belong to this project.')
        for segment in payload.segments:
            if segment.end <= segment.start or segment.end > project['media']['duration'] + .01:
                raise HTTPException(422, 'Each segment must start before its end and stay inside the source.')
        duration = sum(s.end - s.start for s in payload.segments) / payload.speed
        if duration > 600:
            raise HTTPException(422, 'Each export is limited to 10 minutes.')
        for caption in payload.captions:
            if caption.end <= caption.start or caption.end > duration + .01:
                raise HTTPException(422, 'Caption timings must stay inside the output duration.')

    @app.post('/api/projects/{project_id}/export', status_code=202)
    def export(project_id: str, payload: Export):
        project = project_get(project_id)
        validate_export(project, payload)
        clip_id = uuid.uuid4().hex
        output = project['directory'] / f'{clip_id}.mp4'
        with state_lock:
            active_count = sum(pid == project_id for pid in export_reservations.values())
            if len(project['clips']) + active_count >= 20:
                raise HTTPException(429, 'Maximum 20 clips per temporary project. Clear the project to start over.')
            if used_bytes() + (len(export_reservations) + 1) * (MAX_UPLOAD // 2) > 2 * MAX_UPLOAD:
                raise HTTPException(507, 'Not enough temporary storage for another export. Clear a project first.')
            export_reservations[clip_id] = project_id

        def task(job, progress):
            try:
                options = payload.model_dump()
                for kind in ('music', 'logo', 'font'):
                    asset_id = getattr(payload, f'{kind}_asset_id')
                    if asset_id:
                        options[f'{kind}_path'] = project['_asset_files'][asset_id]
                render(project['source'], output, options, progress, job.cancel_event.is_set)
                media = probe(output)
                if job.cancel_event.is_set():
                    from .media import Cancelled
                    raise Cancelled('Export cancelled.')
                clip = {'id': clip_id, 'name': project['name'], 'duration': media['duration'],
                        'created_at': time.time(), 'media': media}
                with state_lock:
                    project['clips'].append(clip)
                    clips[clip_id] = {'path': output, 'project_id': project_id, 'public': clip}
                    job.clip_id = clip_id
            except Exception:
                output.unlink(missing_ok=True)
                raise
        def finalize(job):
            with state_lock:
                export_reservations.pop(clip_id, None)
        try:
            job = jobs.submit('export', project_id, task, finalize)
        except ValueError as exc:
            finalize(None)
            raise HTTPException(429, str(exc)) from exc
        return {'job_id': job['id']}

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str):
        with jobs.lock:
            job = jobs.entries.get(job_id)
            if not job:
                raise HTTPException(404, 'Job not found.')
            return job.public()

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id: str):
        with jobs.lock:
            job = jobs.entries.get(job_id)
            if not job:
                raise HTTPException(404, 'Job not found.')
            job.cancel_event.set()
            return job.public()

    def clip_get(clip_id):
        entry = clips.get(clip_id)
        if not entry:
            raise HTTPException(404, 'Clip expired or not found.')
        project_get(entry['project_id'])
        return entry

    @app.get('/api/clips/{clip_id}')
    def download(clip_id: str):
        entry = clip_get(clip_id)
        name = ''.join(c for c in entry['public']['name'] if c.isalnum() or c in ' -_')[:80] or 'clip'
        return FileResponse(entry['path'], media_type='video/mp4', filename=f'{name}.mp4')

    @app.get('/api/clips/{clip_id}/preview')
    def clip_preview(clip_id: str):
        return FileResponse(clip_get(clip_id)['path'], media_type='video/mp4', content_disposition_type='inline')

    @app.get('/api/projects/{project_id}/download-all')
    def download_all(project_id: str):
        project = project_get(project_id)
        with state_lock:
            entries = [clip_get(clip['id']) for clip in project['clips']]
        if not entries:
            raise HTTPException(409, 'Export at least one clip first.')
        # Separate random archive per request avoids readers seeing a partial rebuild.
        archive = project['directory'] / f'{uuid.uuid4().hex}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as bundle:
            for index, entry in enumerate(entries, 1):
                name = ''.join(c for c in entry['public']['name'] if c.isalnum() or c in ' -_')[:60] or 'clip'
                bundle.write(entry['path'], f'{index:02d}-{name}.mp4')
        from starlette.background import BackgroundTask
        return FileResponse(archive, media_type='application/zip', filename='clips.zip',
                            background=BackgroundTask(archive.unlink, missing_ok=True))

    @app.patch('/api/clips/{clip_id}')
    def rename_clip(clip_id: str, payload: Rename):
        entry = clip_get(clip_id)
        if payload.name:
            entry['public']['name'] = payload.name.strip() or 'Untitled clip'
        return entry['public']

    @app.post('/api/projects/{project_id}/transcribe', status_code=202)
    def transcribe(project_id: str):
        from .analysis import model_available, transcribe_video
        project = project_get(project_id)
        if not project['source']:
            raise HTTPException(409, 'Wait for import to finish.')
        if not model_available():
            raise HTTPException(503, 'A local speech model is required. See README: optional AI setup.')

        def task(job, progress):
            project['transcript'] = transcribe_video(project['source'], progress, job.cancel_event.is_set)
        job = queue('transcribe', project, task)
        return {'job_id': job['id']}

    def detect(project_id, kind):
        from .detection import detect_scenes, detect_speech_regions
        project = project_get(project_id)
        if not project['source']:
            raise HTTPException(409, 'Wait for import to finish.')

        def task(job, progress):
            operation = detect_scenes if kind == 'detect-scenes' else detect_speech_regions
            detected = operation(project['source'], cancelled=job.cancel_event.is_set)
            with state_lock:
                project['detected_segments'] = detected
                project['detection_kind'] = 'scenes' if kind == 'detect-scenes' else 'non_silent'
        job = queue(kind, project, task)
        return {'job_id': job['id']}

    @app.post('/api/projects/{project_id}/detect-scenes', status_code=202)
    def scene_detection(project_id: str):
        return detect(project_id, 'detect-scenes')

    @app.post('/api/projects/{project_id}/remove-silence', status_code=202)
    def silence_detection(project_id: str):
        return detect(project_id, 'remove-silence')

    @app.post('/api/projects/{project_id}/suggest')
    def suggest(project_id: str, payload: Suggest):
        from .analysis import suggest_clips
        project = project_get(project_id)
        if not project['transcript']:
            raise HTTPException(409, 'Transcribe this video first to find spoken passages.')
        return suggest_clips(project['transcript'], project['media']['duration'], payload.keywords,
                             clip_duration=payload.duration)

    static = Path(__file__).parent / 'static'
    static.mkdir(exist_ok=True)
    app.mount('/', StaticFiles(directory=static, html=True), name='website')
    return app
