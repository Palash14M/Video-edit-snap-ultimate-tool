"""Measured scene cuts and non-silent audio regions, without semantic AI claims.

Non-silent audio may contain music or noise: this is not speech recognition.
Both helpers return source timestamps for review before applying destructive edits.
"""
from pathlib import Path
import math
import re

from .media import Cancelled, MediaError, _run, probe


_FORMATS = 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpegts,mpeg,mpegvideo,ogg,flv,asf'


def _finite(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaError(f'{name} must be a finite number.') from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise MediaError(f'{name} must be between {minimum} and {maximum}.')
    return number


def _input(source):
    return ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-protocol_whitelist', 'file,pipe', '-format_whitelist', _FORMATS,
            '-i', str(source), '-threads', '2', '-filter_threads', '1']


def detect_scenes(source: Path, threshold: float = .3, cancelled=lambda: False) -> list[dict]:
    """Split the source on measured hard visual cuts exceeding threshold 0..1."""
    threshold = _finite(threshold, 'Scene threshold', 0, 1)
    if cancelled():
        raise Cancelled('Scene detection cancelled.')
    duration = probe(source)['duration']
    raw = _run(_input(source) + ['-vf',
               f'select=gt(scene\\,{threshold}),metadata=mode=print:file=-',
               '-an', '-f', 'null', '-'], cancelled, timeout=600).decode('utf-8', 'replace')
    cuts = [0.0]
    for stamp in re.findall(r'\bpts_time:([0-9.eE+-]+)', raw):
        value = float(stamp)
        if math.isfinite(value) and .05 < value < duration - .05:
            cuts.append(value)
    cuts = sorted(set(cuts)) + [duration]
    return [{'start': round(start, 3), 'end': round(end, 3)}
            for start, end in zip(cuts, cuts[1:]) if end - start >= .05]


def detect_speech_regions(source: Path, noise_db: float = -35,
                          min_silence: float = .4, cancelled=lambda: False) -> list[dict]:
    """Return the complement of measured silence; does not classify speech."""
    noise_db = _finite(noise_db, 'Noise threshold', -90, -1)
    min_silence = _finite(min_silence, 'Minimum silence', .05, 10)
    if cancelled():
        raise Cancelled('Silence detection cancelled.')
    media = probe(source)
    if not media['has_audio']:
        raise MediaError('The source has no audio track to analyze.')
    raw = _run(_input(source) + ['-vn', '-af',
               f'silencedetect=noise={noise_db}dB:d={min_silence},ametadata=mode=print:file=-',
               '-f', 'null', '-'], cancelled, timeout=600).decode('utf-8', 'replace')
    events = re.findall(r'lavfi\.silence_(start|end)=([0-9.eE+-]+)', raw)
    silences = []
    current = None
    duration = media['duration']
    for event, stamp in events:
        value = float(stamp)
        if not math.isfinite(value):
            continue
        value = min(duration, max(0.0, value))
        if event == 'start':
            current = value
        elif current is not None:
            silences.append((current, value))
            current = None
    if current is not None:
        silences.append((current, duration))
    regions = []
    cursor = 0.0
    for start, end in sorted(silences):
        if start - cursor >= .05:
            regions.append({'start': round(cursor, 3), 'end': round(start, 3)})
        cursor = max(cursor, end)
    if duration - cursor >= .05:
        regions.append({'start': round(cursor, 3), 'end': round(duration, 3)})
    return regions
