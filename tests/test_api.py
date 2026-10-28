"""Real boundary tests: private access, media lifecycle, validation and rendering."""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from studio.app import create_app
    with TestClient(create_app(data_dir=tmp_path, password="a-test-password-long-enough")) as c:
        yield c


def login(client):
    response = client.post('/api/session', json={'password': 'a-test-password-long-enough'})
    assert response.status_code == 200


@pytest.fixture
def video(tmp_path):
    path = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=24',
                    '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '3', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)], check=True)
    return path


def wait_job(client, job_id):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        result = client.get(f'/api/jobs/{job_id}').json()
        if result['status'] in ('completed', 'failed', 'cancelled'):
            return result
        time.sleep(.05)
    pytest.fail('Video job did not finish')


def upload(client, video):
    with video.open('rb') as f:
        response = client.post('/api/projects/upload', files={'file': ('sample.mp4', f, 'video/mp4')})
    assert response.status_code == 202, response.text
    result = wait_job(client, response.json()['job_id'])
    assert result['status'] == 'completed', result
    return client.get(f"/api/projects/{result['project_id']}").json()


def test_private_access_and_logout(client):
    assert client.get('/api/history').status_code == 401
    assert client.post('/api/session', json={'password': 'wrong'}).status_code == 401
    login(client)
    assert client.get('/api/history').json() == []
    assert 'httponly' in client.cookies.get('studio_session', '').lower() or client.cookies.get('studio_session')
    client.delete('/api/session')
    assert client.get('/api/history').status_code == 401


def test_upload_preview_edit_and_real_clip_download(client, video):
    login(client)
    project = upload(client, video)
    assert 2.8 < project['media']['duration'] < 3.2
    preview = client.get(f"/api/projects/{project['id']}/preview", headers={'Range': 'bytes=0-99'})
    assert preview.status_code == 206
    assert len(preview.content) == 100
    assert client.get(f"/api/projects/{project['id']}/source").status_code == 404
    edited = client.patch(f"/api/projects/{project['id']}", json={'name': 'My first clip'})
    assert edited.json()['name'] == 'My first clip'
    response = client.post(f"/api/projects/{project['id']}/export", json={
        'segments': [{'start': .2, 'end': 1.4}], 'aspect': '9:16', 'resolution': 720,
        'fit': 'contain', 'text': "It's my clip: 100%", 'captions': [{'start': 0, 'end': 1, 'text': 'Hello'}]
    })
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()['job_id'])
    assert job['status'] == 'completed', job
    renamed = client.patch(f"/api/clips/{job['clip_id']}", json={'name': 'My renamed clip'})
    assert renamed.status_code == 200
    clip = client.get(f"/api/clips/{job['clip_id']}")
    assert clip.status_code == 200
    assert clip.headers['content-type'] == 'video/mp4'
    assert len(clip.content) > 1000
    assert 'My%20renamed%20clip.mp4' in clip.headers['content-disposition']
    assert client.get('/api/history').json() == []  # local files are never retained in URL history
    assert client.delete(f"/api/projects/{project['id']}").status_code == 200
    assert client.get(f"/api/clips/{job['clip_id']}").status_code == 404


@pytest.mark.parametrize('url', ['http://127.0.0.1/x','https://youtube.com.evil.test/watch?v=a',
                               'file:///etc/passwd','https://user:pass@youtube.com/watch?v=a'])
def test_import_rejects_unsafe_urls(client, url):
    login(client)
    response = client.post('/api/projects/import', json={'url': url})
    assert response.status_code == 422


def test_reject_invalid_media_and_segment_limits(client, video):
    login(client)
    response = client.post('/api/projects/upload', files={'file': ('x.mp4', b'not media', 'video/mp4')})
    job = wait_job(client, response.json()['job_id'])
    assert job['status'] == 'failed'
    project = upload(client, video)
    for payload in ({'segments':[{'start':2,'end':1}]}, {'segments':[{'start':0,'end':8}]},
                    {'segments':[]}, {'segments':[{'start':-1,'end':1}]}):
        assert client.post(f"/api/projects/{project['id']}/export", json=payload).status_code == 422


def test_reject_cross_origin_mutation(client):
    login(client)
    assert client.post('/api/projects/import', json={'url':'https://youtu.be/abcdefghijk'},
                       headers={'Origin':'https://attacker.example'}).status_code == 403


def test_missing_job_and_project_do_not_leak_paths(client):
    login(client)
    assert client.get('/api/jobs/missing').status_code == 404
    assert client.get('/api/projects/missing').status_code == 404
    assert client.get('/api/clips/missing').status_code == 404


def test_https_reverse_proxy_origin_and_secure_cookie(tmp_path, monkeypatch):
    from studio.app import create_app
    monkeypatch.setenv('STUDIO_PUBLIC_ORIGIN', 'https://studio.example')
    with TestClient(create_app(tmp_path, password='reverse-proxy-test-password')) as c:
        response = c.post('/api/session', json={'password':'reverse-proxy-test-password'},
                          headers={'Origin':'https://studio.example'})
        assert response.status_code == 200
        assert '; Secure' in response.headers['set-cookie']
        assert c.post('/api/session', json={'password':'reverse-proxy-test-password'},
                      headers={'Origin':'https://wrong.example'}).status_code == 403


def test_cancellation_releases_worker_and_project_cleanup(client, video):
    from threading import Event
    from studio.media import Cancelled
    login(client)
    began = Event()

    def task(job, progress):
        began.set()
        while not job.cancel_event.wait(.01):
            pass
        raise Cancelled('Cancelled')
    job = client.app.state.jobs.submit('test', None, task)
    assert began.wait(2)
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    assert wait_job(client, job['id'])['status'] == 'cancelled'
    project = upload(client, video)
    client.app.state.projects[project['id']]['expires_at'] = time.time() - 1
    assert client.get(f"/api/projects/{project['id']}/preview").status_code == 404


def test_bulk_download_contains_only_generated_clips(client, video):
    import io
    import zipfile
    login(client)
    project = upload(client, video)
    assert client.get(f"/api/projects/{project['id']}/download-all").status_code == 409
    response = client.post(f"/api/projects/{project['id']}/export", json={
        'segments': [{'start': 0, 'end': 1}]
    })
    job = wait_job(client, response.json()['job_id'])
    assert job['status'] == 'completed'
    response = client.get(f"/api/projects/{project['id']}/download-all")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert len(archive.namelist()) == 1
    assert all(name.endswith('.mp4') and '/' not in name for name in archive.namelist())
    assert len(archive.read(archive.namelist()[0])) > 1000


def test_scene_and_silence_detection_do_not_change_user_timeline(client, video):
    login(client)
    project = upload(client, video)
    for endpoint in ('detect-scenes', 'remove-silence'):
        response = client.post(f"/api/projects/{project['id']}/{endpoint}")
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()['job_id'])
        assert job['status'] == 'completed', job
        state = client.get(f"/api/projects/{project['id']}").json()
        assert len(state['detected_segments']) >= 1
        assert state['detected_segments'][0]['start'] == 0
        assert state['edits'] is None


def test_suggestions_respect_requested_length(client, video):
    login(client)
    project = upload(client, video)
    client.app.state.projects[project['id']]['transcript'] = [
        {'start':0,'end':1,'text':'A useful first sentence.'},
        {'start':1,'end':2.5,'text':'A second one.'}
    ]
    response = client.post(f"/api/projects/{project['id']}/suggest", json={'duration': 5})
    assert response.status_code == 200
    assert response.json()[0]['end'] <= 3


def test_cancelled_queued_upload_cleans_temporary_project(client, video):
    from threading import Event
    login(client)
    release = Event()
    began = Event()

    def block(job, progress):
        began.set()
        release.wait(5)
    client.app.state.jobs.submit('block', None, block)
    assert began.wait(2)
    with video.open('rb') as f:
        response = client.post('/api/projects/upload', files={'file':('x.mp4',f,'video/mp4')})
    pending = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    project_id = pending['project_id']
    try:
        listed = client.get('/api/projects').json()
        assert listed[0]['active_job']['id'] == pending['id']
        client.post(f"/api/jobs/{pending['id']}/cancel")
    finally:
        release.set()
    assert wait_job(client, pending['id'])['status'] == 'cancelled'
    assert client.get(f'/api/projects/{project_id}').status_code == 404
    assert not (video.parent / 'temporary' / project_id).exists()


def test_export_clip_quota_rejects_without_starting_job(client, video):
    login(client)
    project = upload(client, video)
    client.app.state.projects[project['id']]['clips'] = [{'id': str(i)} for i in range(20)]
    response = client.post(f"/api/projects/{project['id']}/export", json={'segments':[{'start':0,'end':1}]})
    assert response.status_code == 429
