"""Uploaded assets are decoded and canonicalized, never trusted by extension."""
import subprocess
from pathlib import Path

import pytest

from studio.media import Cancelled, MediaError


def test_logo_converted_to_bounded_png_without_metadata(tmp_path):
    from PIL import Image
    from studio.assets import prepare_asset
    source = tmp_path / 'logo.jpg'
    image = Image.new('RGB', (3000, 1500), '#137d64')
    image.save(source, exif=b'Exif\x00\x00arbitrary-ignored-metadata')
    destination = tmp_path / 'prepared'
    asset = prepare_asset(source, destination, 'logo')
    assert asset['kind'] == 'logo'
    assert asset['path'] == destination / 'logo.png'
    with Image.open(asset['path']) as decoded:
        assert decoded.format == 'PNG'
        assert decoded.size == (2048, 1024)
        assert not decoded.info.get('exif')
        assert not decoded.info.get('icc_profile')
    assert source.exists()


def test_logo_preserves_alpha_and_original_small_dimensions(tmp_path):
    from PIL import Image
    from studio.assets import prepare_asset
    source = tmp_path / 'source.bin'
    Image.new('RGBA', (40, 20), (12, 45, 67, 120)).save(source, format='PNG')
    result = prepare_asset(source, tmp_path / 'out', 'logo')
    with Image.open(result['path']) as image:
        assert image.size == (40, 20)
        assert image.mode == 'RGBA'
        assert image.getpixel((1, 1))[3] == 120


def test_logo_rejects_large_decompressed_image(tmp_path):
    from PIL import Image
    from studio.assets import prepare_asset
    source = tmp_path / 'large.png'
    Image.new('L', (4100, 4000), 0).save(source)
    with pytest.raises(MediaError, match='16'):
        prepare_asset(source, tmp_path / 'out', 'logo')
    assert not list((tmp_path / 'out').glob('*'))


def test_svg_is_rejected_instead_of_served_as_active_content(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'fake.png'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    with pytest.raises(MediaError):
        prepare_asset(source, tmp_path / 'out', 'logo')
    assert not list((tmp_path / 'out').glob('*'))


def test_real_ttf_font_is_parsed_and_canonicalized(tmp_path):
    from fontTools.ttLib import TTFont
    from studio.assets import prepare_asset
    source = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    result = prepare_asset(source, tmp_path / 'out', 'font')
    assert result['path'].name == 'font.ttf'
    assert result['kind'] == 'font'
    with TTFont(result['path']) as font:
        assert font.getBestCmap()[ord('A')]
        assert font['maxp'].numGlyphs > 100
    assert source.exists()


def test_invalid_font_rejected_and_source_is_not_deleted(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'font.ttf'
    source.write_bytes(b'OTTOinvalid-font-data')
    with pytest.raises(MediaError):
        prepare_asset(source, tmp_path / 'out', 'font')
    assert source.exists()
    assert not list((tmp_path / 'out').glob('*'))


def test_music_normalizes_real_audio_to_aac(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'source.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=1.5', str(source)], check=True)
    result = prepare_asset(source, tmp_path / 'out', 'music')
    assert result['kind'] == 'music'
    assert result['path'].name == 'audio.m4a'
    assert result['duration'] == pytest.approx(1.5, abs=.1)
    import json
    output = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(result['path'])])
    streams = json.loads(output)['streams']
    assert len(streams) == 1
    assert streams[0]['codec_name'] == 'aac'
    assert source.exists()


def test_music_without_audio_is_rejected(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=red:s=64x64:d=0.2', '-c:v', 'libx264', str(source)], check=True)
    with pytest.raises(MediaError, match='audio'):
        prepare_asset(source, tmp_path / 'out', 'music')


def test_music_playlist_cannot_read_other_local_files(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'sound.mp3'
    source.write_text("ffconcat version 1.0\nfile '/etc/passwd'\n")
    with pytest.raises(MediaError):
        prepare_asset(source, tmp_path / 'out', 'music')


@pytest.mark.parametrize('kind,size', [('logo', 25 * 1024**2 + 1), ('font', 5 * 1024**2 + 1)])
def test_rejects_oversized_assets_before_decoding(tmp_path, kind, size):
    from studio.assets import prepare_asset
    source = tmp_path / 'oversized'
    with source.open('wb') as f:
        f.truncate(size)
    with pytest.raises(MediaError, match='MiB'):
        prepare_asset(source, tmp_path / 'out', kind)


@pytest.mark.parametrize('kind', ['', 'svg', '../logo'])
def test_unsupported_kind_rejected(tmp_path, kind):
    from studio.assets import prepare_asset
    source = tmp_path / 'asset'
    source.write_bytes(b'x')
    with pytest.raises(MediaError):
        prepare_asset(source, tmp_path / 'out', kind)


def test_empty_and_cancelled_assets_leave_no_partial(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'empty.png'
    source.touch()
    with pytest.raises(MediaError):
        prepare_asset(source, tmp_path / 'out', 'logo')
    source.write_bytes(b'not decoded because cancelled')
    with pytest.raises(Cancelled):
        prepare_asset(source, tmp_path / 'out', 'logo', cancelled=lambda: True)
    assert source.exists()
    assert not list((tmp_path / 'out').glob('*'))


def test_music_longer_than_ten_minutes_is_rejected_before_encoding(tmp_path):
    from studio.assets import prepare_asset
    source = tmp_path / 'long.flac'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'anullsrc=r=8000:cl=mono:d=601', '-c:a', 'flac', str(source)], check=True)
    with pytest.raises(MediaError, match='600'):
        prepare_asset(source, tmp_path / 'out', 'music')
    assert not list((tmp_path / 'out').glob('*'))


def test_preexisting_prepared_asset_cannot_be_overwritten(tmp_path):
    from PIL import Image
    from studio.assets import prepare_asset
    source = tmp_path / 'incoming.png'
    Image.new('RGB', (10, 10), 'red').save(source)
    destination = tmp_path / 'out'
    destination.mkdir()
    original = destination / 'logo.png'
    original.write_bytes(b'existing-user-file')
    with pytest.raises(MediaError, match='already'):
        prepare_asset(source, destination, 'logo')
    assert original.read_bytes() == b'existing-user-file'
    assert list(destination.iterdir()) == [original]


def test_cancellation_during_image_preparation_cleans_generated_files(tmp_path):
    from PIL import Image
    from studio.assets import prepare_asset
    source = tmp_path / 'incoming.png'
    Image.new('RGB', (10, 10), 'red').save(source)
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 3

    with pytest.raises(Cancelled):
        prepare_asset(source, tmp_path / 'out', 'logo', cancelled=cancelled)
    assert source.exists()
    assert not list((tmp_path / 'out').glob('*'))
