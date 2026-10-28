"""Detection must be driven by real media events, not inferred fake AI output."""
import math
import subprocess

import pytest

from studio.media import Cancelled, MediaError


@pytest.fixture(scope='module')
def sources(tmp_path_factory):
    directory = tmp_path_factory.mktemp('detection')
    cut = directory / 'cut.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=red:s=160x120:r=20:d=1', '-f', 'lavfi', '-i',
                    'color=blue:s=160x120:r=20:d=1', '-filter_complex',
                    '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]',
                    '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(cut)], check=True)
    sound = directory / 'sound.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=green:s=160x120:r=20:d=4', '-f', 'lavfi', '-i',
                    'anullsrc=r=16000:cl=mono:d=1', '-f', 'lavfi', '-i',
                    'sine=frequency=440:sample_rate=16000:duration=2', '-f', 'lavfi', '-i',
                    'anullsrc=r=16000:cl=mono:d=1', '-filter_complex',
                    '[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]', '-map', '0:v', '-map', '[a]',
                    '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', str(sound)], check=True)
    return cut, sound


def test_detect_scenes_finds_hard_color_cut(sources):
    from studio.detection import detect_scenes
    result = detect_scenes(sources[0])
    assert len(result) == 2
    assert result[0]['start'] == 0
    assert result[0]['end'] == pytest.approx(1, abs=.08)
    assert result[1]['start'] == pytest.approx(1, abs=.08)
    assert result[1]['end'] == pytest.approx(2, abs=.08)


def test_single_visual_scene_is_preserved(sources):
    from studio.detection import detect_scenes
    assert detect_scenes(sources[1]) == [{'start': 0.0, 'end': 4.0}]


def test_silence_removal_preserves_only_tone_region(sources):
    from studio.detection import detect_speech_regions
    regions = detect_speech_regions(sources[1])
    assert len(regions) == 1
    assert regions[0]['start'] == pytest.approx(1, abs=.1)
    assert regions[0]['end'] == pytest.approx(3, abs=.1)


def test_silent_video_without_audio_fails_explicitly(sources):
    from studio.detection import detect_speech_regions
    with pytest.raises(MediaError, match='audio'):
        detect_speech_regions(sources[0])


@pytest.mark.parametrize('threshold', [-.1, 1.1, math.nan, math.inf, 'bad'])
def test_invalid_scene_threshold_rejected(sources, threshold):
    from studio.detection import detect_scenes
    with pytest.raises(MediaError):
        detect_scenes(sources[0], threshold)


@pytest.mark.parametrize('kwargs', [{'noise_db': 1}, {'noise_db': math.nan},
                                    {'min_silence': 0}, {'min_silence': math.inf}])
def test_invalid_audio_threshold_rejected(sources, kwargs):
    from studio.detection import detect_speech_regions
    with pytest.raises(MediaError):
        detect_speech_regions(sources[1], **kwargs)


def test_cancelled_detection_does_not_run(sources):
    from studio.detection import detect_scenes, detect_speech_regions
    with pytest.raises(Cancelled):
        detect_scenes(sources[0], cancelled=lambda: True)
    with pytest.raises(Cancelled):
        detect_speech_regions(sources[1], cancelled=lambda: True)
