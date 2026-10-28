"""Temporary custom assets must render and disappear with their project."""
import subprocess

import pytest
from fastapi.testclient import TestClient

from test_api import login, upload, wait_job


@pytest.fixture
def client(tmp_path):
    from studio.app import create_app
    with TestClient(create_app(data_dir=tmp_path, password='a-test-password-long-enough')) as client:
        yield client


@pytest.fixture
def video(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=24:d=2',
                    '-c:v','libx264',str(source)],check=True)
    return source


def test_upload_logo_and_music_then_render(client, video):
    login(client)
    project = upload(client, video)
    from PIL import Image
    logo = video.parent / 'logo.png'
    Image.new('RGB',(64,32),'red').save(logo)
    music = video.parent / 'music.wav'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=880:duration=1',str(music)],check=True)
    assets = {}
    for kind, path in [('logo',logo),('music',music)]:
        with path.open('rb') as file:
            response = client.post(f"/api/projects/{project['id']}/assets/{kind}",
                                   files={'file':(path.name,file)})
        assert response.status_code == 202, response.text
        job = wait_job(client,response.json()['job_id'])
        assert job['status']=='completed',job
        state = client.get(f"/api/projects/{project['id']}").json()
        assets[kind] = next(asset['id'] for asset in state['assets'] if asset['kind']==kind)
        assert all('path' not in asset for asset in state['assets'])
    response = client.post(f"/api/projects/{project['id']}/export",json={
        'segments':[{'start':0,'end':1.5}], 'logo_asset_id':assets['logo'],
        'music_asset_id':assets['music'], 'music_volume':.3,'transition':'fade',
        'caption_color':'#ffff00','captions':[{'start':0,'end':1,'text':'Custom brand'}]
    })
    assert response.status_code==202,response.text
    job=wait_job(client,response.json()['job_id'])
    assert job['status']=='completed',job
    clip=client.get(f"/api/clips/{job['clip_id']}")
    output=video.parent/'output.mp4'
    output.write_bytes(clip.content)
    from studio.media import probe
    assert probe(output)['has_audio'] is True
    assert 1.3<probe(output)['duration']<1.7
    assert client.delete(f"/api/projects/{project['id']}").status_code==200
    assert not (video.parent/'temporary'/project['id']).exists()


def test_assets_cannot_reference_another_projects_files(client, video):
    login(client)
    project=upload(client,video)
    response=client.post(f"/api/projects/{project['id']}/export",json={
        'segments':[{'start':0,'end':1}],'logo_asset_id':'../../etc/passwd'})
    assert response.status_code==422
    response=client.post(f"/api/projects/{project['id']}/assets/not-a-kind",files={'file':('x',b'x')})
    assert response.status_code==422


def test_asset_upload_rejects_invalid_image_as_failed_job(client, video):
    login(client)
    project=upload(client,video)
    response=client.post(f"/api/projects/{project['id']}/assets/logo",files={'file':('fake.png',b'not an image')})
    assert response.status_code==202
    assert wait_job(client,response.json()['job_id'])['status']=='failed'
    state=client.get(f"/api/projects/{project['id']}").json()
    assert state['assets']==[]


def test_actual_asset_is_private_to_its_project(client, video):
    from pathlib import Path
    login(client)
    first=upload(client,video)
    font=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    with font.open('rb') as file:
        response=client.post(f"/api/projects/{first['id']}/assets/font",files={'file':('brand.ttf',file)})
    assert wait_job(client,response.json()['job_id'])['status']=='completed'
    first=client.get(f"/api/projects/{first['id']}").json()
    font_id=first['assets'][0]['id']
    second=upload(client,video)
    response=client.post(f"/api/projects/{second['id']}/export",json={
        'segments':[{'start':0,'end':1}],'font_asset_id':font_id})
    assert response.status_code==422
    response=client.post(f"/api/projects/{first['id']}/export",json={
        'segments':[{'start':0,'end':1}],'font_asset_id':font_id,
        'caption_color':'#22FF55','captions':[{'start':0,'end':.8,'text':'Brand font'}]})
    assert response.status_code==202
    assert wait_job(client,response.json()['job_id'])['status']=='completed'


@pytest.mark.parametrize('options',[{'font_path':'/etc/passwd'}, {'caption_color':'white:box=0'},
                                  {'transition':'shell'}, {'music_volume':10}])
def test_asset_render_parameters_reject_injected_values(client, video, options):
    login(client)
    project=upload(client,video)
    response=client.post(f"/api/projects/{project['id']}/export",json={
        'segments':[{'start':0,'end':1}],**options})
    assert response.status_code==422
