"""Decode uploaded assets into bounded, self-contained rendering inputs.

Callers supply a private opaque directory. Filenames and extensions supplied by
the browser are ignored; originals are never removed by this module.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile

from .media import Cancelled, MediaError, _run


MAX_ASSET_BYTES = 25 * 1024**2
MAX_FONT_BYTES = 5 * 1024**2
MAX_PIXELS = 16_000_000
_AUDIO_INPUT = ['-protocol_whitelist', 'file,pipe', '-format_whitelist',
                'mp3,wav,flac,aac,ogg,mov,mp4,m4a,3gp,3g2,mj2']


def _cancel(cancelled):
    if cancelled():
        raise Cancelled('Asset preparation cancelled.')


def _image(source, working, cancelled):
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(source) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP', 'BMP', 'TIFF', 'GIF'):
                raise MediaError('Upload a PNG, JPEG, WebP, BMP, TIFF or GIF logo. SVG is unsupported.')
            if image.width * image.height > MAX_PIXELS:
                raise MediaError('A logo must contain at most 16 million pixels.')
            # Normalize only the first frame and apply orientation before scaling.
            image.seek(0)
            oriented = ImageOps.exif_transpose(image)
            oriented.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            _cancel(cancelled)
            rgba = oriented.convert('RGBA')
            # A fresh image avoids transferring EXIF, embedded ICC, comments or paths.
            clean = Image.new('RGBA', rgba.size)
            clean.paste(rgba)
            output = working / 'logo.png'
            clean.save(output, format='PNG', optimize=True)
            return output, {'width': clean.width, 'height': clean.height}
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, MediaError):
            raise
        raise MediaError('The logo is not a supported, readable raster image.') from exc


def _font(source, working, cancelled):
    from fontTools.ttLib import TTFont
    try:
        with source.open('rb') as stream:
            magic = stream.read(4)
        if magic not in (b'\x00\x01\x00\x00', b'OTTO'):
            raise MediaError('Upload a self-contained TrueType (.ttf) or OpenType (.otf) font.')
        with TTFont(source, lazy=False, recalcBBoxes=True, recalcTimestamp=False) as font:
            required = {'head', 'hhea', 'maxp', 'hmtx', 'cmap', 'name'}
            if not required.issubset(font.keys()):
                raise MediaError('The font is missing required layout tables.')
            if not ({'glyf', 'loca'}.issubset(font.keys()) or 'CFF ' in font or 'CFF2' in font):
                raise MediaError('The font does not contain supported outlines.')
            if not 0 < font['maxp'].numGlyphs <= 65535 or not font.getBestCmap():
                raise MediaError('The font needs a valid character map and glyphs.')
            if 'SVG ' in font:
                raise MediaError('Fonts with embedded SVG content are unsupported.')
            # Force table validation before output rather than trusting the header.
            font.ensureDecompiled()
            _cancel(cancelled)
            if 'DSIG' in font:
                del font['DSIG']  # A reserialized font invalidates its original signature.
            name = 'font.otf' if magic == b'OTTO' else 'font.ttf'
            output = working / name
            font.save(output, reorderTables=True)
        return output, {}
    except (Cancelled, MediaError):
        raise
    except Exception as exc:
        raise MediaError('The file is not a valid supported TrueType or OpenType font.') from exc


def _audio_info(source, cancelled):
    raw = _run(['ffprobe', '-v', 'error', *_AUDIO_INPUT, '-show_format', '-show_streams',
                '-of', 'json', str(source)], cancelled, timeout=60)
    try:
        metadata = json.loads(raw)
        stream = next(item for item in metadata['streams'] if item.get('codec_type') == 'audio')
        duration = float(metadata.get('format', {}).get('duration') or stream.get('duration') or 0)
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        raise MediaError('The asset must contain a readable audio track with a finite duration.') from exc
    if not math.isfinite(duration) or not 0 < duration <= 600:
        raise MediaError('Music must have a positive finite duration of at most 600 seconds.')
    return duration


def _music(source, working, cancelled):
    _audio_info(source, cancelled)
    output = working / 'audio.m4a'
    _run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *_AUDIO_INPUT,
          '-i', str(source), '-map', '0:a:0', '-vn', '-map_metadata', '-1', '-t', '600',
          '-c:a', 'aac', '-b:a', '160k', '-ac', '2', '-ar', '48000', '-threads', '2',
          '-movflags', '+faststart', str(output)], cancelled, timeout=120)
    duration = _audio_info(output, cancelled)
    return output, {'duration': duration}


def prepare_asset(source: Path, directory: Path, kind: str, cancelled=lambda: False) -> dict:
    """Prepare logo/music/font; return its canonical path plus inspected metadata."""
    if kind not in ('logo', 'music', 'font'):
        raise MediaError('Choose a logo, music or font asset.')
    _cancel(cancelled)
    source, directory = Path(source), Path(directory)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise MediaError('The uploaded asset could not be read.') from exc
    maximum = MAX_FONT_BYTES if kind == 'font' else MAX_ASSET_BYTES
    if size <= 0:
        raise MediaError('Choose a non-empty asset.')
    if size > maximum:
        raise MediaError(f'The maximum {kind} size is {maximum // 1024**2} MiB.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=directory) as temporary:
        working = Path(temporary)
        output, metadata = {'logo': _image, 'font': _font, 'music': _music}[kind](source, working, cancelled)
        _cancel(cancelled)
        if output.stat().st_size > maximum:
            raise MediaError('The normalized asset exceeds its supported size limit.')
        target = directory / output.name
        try:
            # Same-filesystem atomic link neither overwrites preexisting files nor
            # publishes partially written bytes. Temporary files are cleaned below.
            os.link(output, target)
        except FileExistsError as exc:
            raise MediaError('This asset directory already contains a prepared asset.') from exc
    return {'path': target, 'kind': kind, **metadata}
