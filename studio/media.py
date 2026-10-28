"""Bounded real-media operations. No shell commands or fabricated results."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse


LOGGER = logging.getLogger(__name__)
MAX_OUTPUT_BYTES = 512 * 1024**2
# Only self-contained media containers; never playlists, concat scripts or
# manifests that can cause FFmpeg to read other files or network destinations.
INPUT_OPTIONS = ["-protocol_whitelist", "file,pipe", "-format_whitelist",
                 "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpegts,ogg,flv"]


class MediaError(ValueError):
    pass


class Cancelled(MediaError):
    pass


def _run(command, cancelled=lambda: False, timeout=3600, progress=None):
    if cancelled():
        raise Cancelled("Processing cancelled.")
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            if cancelled():
                raise Cancelled("Processing cancelled.")
            if time.monotonic() - started > timeout:
                raise MediaError("Processing exceeded its time limit.")
            try:
                stdout, stderr = process.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired as error:
                if progress and error.output:
                    progress(error.output.decode("utf-8", "replace"))
        if process.returncode:
            # Diagnostic details are for the server, never URL credentials.
            detail = stderr.decode("utf-8", "replace")[-1600:]
            if command[0] in ("ffmpeg", "ffprobe"):
                LOGGER.warning("%s failed: %s", command[0], re.sub(r"https?://[^\s]+", "[remote URL]", detail))
                raise MediaError("Video processing failed. The file may be damaged, unsupported, or exceed processing limits.")
            raise MediaError("YouTube import failed. The video may be private, restricted, unavailable, or require a newer yt-dlp release.")
        return stdout
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def probe(path: Path) -> dict:
    try:
        raw = _run(["ffprobe", "-v", "error", *INPUT_OPTIONS, "-show_format", "-show_streams", "-of", "json", str(path)], timeout=30)
        metadata = json.loads(raw)
        video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
        duration = float(metadata.get("format", {}).get("duration") or video.get("duration") or 0)
        width, height = int(video["width"]), int(video["height"])
        if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
            raise ValueError("invalid video metadata")
        # ffmpeg auto-rotates on decode; report the resulting display geometry.
        rotation = next((int(side.get("rotation", 0)) for side in video.get("side_data_list", []) if "rotation" in side), 0)
        if abs(rotation) % 180 == 90:
            width, height = height, width
        return {"duration": duration, "width": width, "height": height,
                "has_audio": any(s["codec_type"] == "audio" for s in metadata["streams"])}
    except (StopIteration, KeyError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, MediaError):
            raise
        raise MediaError("The file is not a readable video with a finite duration.") from error


def validate_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        if parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            raise ValueError()
        query = parse_qs(parsed.query)
        if "list" in query:
            raise ValueError()
        if parsed.hostname == "youtu.be":
            video_id = parsed.path.lstrip("/")
        elif parsed.path == "/watch":
            video_id = query.get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            video_id = parsed.path.split("/")[2]
        else:
            raise ValueError()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError()
        return "https://www.youtube.com/watch?v=" + video_id
    except (ValueError, AttributeError, IndexError) as error:
        raise MediaError("Enter a single public YouTube video URL using HTTPS. Playlists and other hosts are not supported.") from error


def import_url(url: str, directory: Path, progress, cancelled) -> Path:
    url = validate_url(url)
    directory.mkdir(parents=True, exist_ok=True)
    progress(.02)
    command = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-cache-dir",
               "--no-warnings", "--no-progress", "--socket-timeout", "20", "--retries", "2", "--fragment-retries", "2",
               "--max-filesize", "1G", "--match-filter", "duration <= 7200 & !is_live",
               "-f", "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mp4",
               "--restrict-filenames", "--no-write-thumbnail", "--no-write-info-json",
               "-o", str(directory / "source.%(ext)s"), "--", url]
    _run(command, cancelled, timeout=1800)
    paths = [p for p in directory.glob("source.*") if p.is_file() and p.suffix not in {".part", ".ytdl"}]
    if len(paths) != 1 or paths[0].stat().st_size > 1024**3:
        raise MediaError("No supported video was imported. Maximum input: 2 hours and 1 GB.")
    metadata = probe(paths[0])
    if metadata["duration"] > 7200:
        paths[0].unlink(missing_ok=True)
        raise MediaError("Maximum input duration is 2 hours.")
    progress(1)
    return paths[0]


def prepare_preview(source: Path, directory: Path, progress, cancelled) -> Path:
    """Normalize any accepted container/codec to browser-playable H.264/AAC.

    This intentionally transcodes rather than trusting a filename or container:
    MP4 itself does not imply a codec the browser can decode. Media is capped at
    1080p, remains below 1 GiB and is only published once completely encoded.
    """
    metadata = probe(source)
    if metadata["duration"] > 7200:
        raise MediaError("Maximum input duration is 2 hours.")
    if cancelled():
        raise Cancelled("Preview preparation cancelled.")
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "preview.mp4"
    partial = directory / "preview.partial.mp4"
    width, height = metadata["width"], metadata["height"]
    factor = min(1, 1920 / max(width, height), 1080 / min(width, height))
    width, height = max(2, int(width * factor) // 2 * 2), max(2, int(height * factor) // 2 * 2)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *INPUT_OPTIONS,
               "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
               "-vf", f"scale={width}:{height},setsar=1", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", "-fs", str(1024**3), "-progress", "pipe:1", str(partial)]
    def report(raw):
        matches = re.findall(r"out_time_us=(\d+)", raw)
        if matches:
            progress(min(.98, int(matches[-1]) / 1_000_000 / metadata["duration"]))
    progress(.01)
    try:
        _run(command, cancelled, timeout=1800, progress=report)
        if cancelled():
            raise Cancelled("Preview preparation cancelled.")
        normalized = probe(partial)
        if partial.stat().st_size >= 1024**3 or abs(normalized["duration"] - metadata["duration"]) > max(.25, metadata["duration"] * .001):
            raise MediaError("The normalized video exceeds processing size limits. Use a shorter or smaller source.")
        os.replace(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    progress(1)
    return output


def _number(value, name, minimum=None, maximum=None):
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise MediaError(f"{name} must be a finite number.") from error
    if not math.isfinite(number) or (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise MediaError(f"{name} is outside the supported range.")
    return number


def _filter_path(path):
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")


def _color(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise MediaError(f"{name} must be a six-digit hexadecimal color.")
    return "0x" + value[1:]


def _asset_path(value, name, extensions):
    if value is None:
        return None
    if not isinstance(value, (str, Path)):
        raise MediaError(f"The selected {name} asset is invalid.")
    path = Path(value)
    if path.suffix.lower() not in extensions or not path.is_file() or path.stat().st_size <= 0:
        raise MediaError(f"The selected {name} asset is missing or unsupported.")
    return path


def render(source: Path, output: Path, options: dict, progress, cancelled) -> None:
    metadata = probe(source)
    segments = options.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 50:
        raise MediaError("Choose between 1 and 50 timeline segments.")
    intervals = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise MediaError("Each timeline segment needs a start and end.")
        start = _number(segment.get("start"), "Segment start", 0, metadata["duration"])
        end = _number(segment.get("end"), "Segment end", 0, metadata["duration"] + .001)
        if end - start < .05:
            raise MediaError("Each segment must last at least 0.05 seconds.")
        intervals.append((start, end))
    speed = _number(options.get("speed", 1), "Playback speed", .5, 2)
    duration = sum(end - start for start, end in intervals) / speed
    if duration > 600:
        raise MediaError("An exported clip cannot exceed 10 minutes.")
    aspect = options.get("aspect", "original")
    resolution = options.get("resolution", 720)
    if resolution not in (720, 1080) or aspect not in ("original", "9:16", "16:9", "1:1"):
        raise MediaError("Choose a supported aspect ratio and 720p or 1080p output.")
    fit = options.get("fit", "contain")
    if fit not in ("contain", "cover"):
        raise MediaError("Fit must be contain or cover.")
    volume = _number(options.get("volume", 1), "Volume", 0, 2)
    transition = options.get("transition", "none")
    if transition not in ("none", "fade"):
        raise MediaError("Transition must be none or fade.")
    caption_color = _color(options.get("caption_color", "#FFFFFF"), "Caption color")
    caption_background = _color(options.get("caption_background", "#000000"), "Caption background")
    text_color = _color(options.get("text_color", "#FFFFFF"), "Overlay text color")
    music_volume = _number(options.get("music_volume", .2), "Music volume", 0, 1)
    font_path = _asset_path(options.get("font_path"), "font", {".ttf", ".otf"})
    music_path = _asset_path(options.get("music_path"), "music", {".wav", ".m4a", ".aac", ".mp3", ".flac", ".ogg"})
    logo_path = _asset_path(options.get("logo_path"), "logo", {".png"})
    logo_position = options.get("logo_position", "top-right")
    if logo_position not in ("top-left", "top-right", "bottom-left", "bottom-right"):
        raise MediaError("Choose a supported logo corner.")
    text = options.get("text", "")
    if not isinstance(text, str) or len(text) > 500:
        raise MediaError("Overlay text must be at most 500 characters.")
    captions = options.get("captions", [])
    if not isinstance(captions, list) or len(captions) > 500:
        raise MediaError("Use at most 500 caption lines per export.")
    checked_captions = []
    for caption in captions:
        start = _number(caption.get("start"), "Caption start", 0, duration)
        end = _number(caption.get("end"), "Caption end", 0, duration + .001)
        line = caption.get("text", "")
        if end <= start or not isinstance(line, str) or len(line) > 500:
            raise MediaError("Caption timing or text is invalid.")
        checked_captions.append((start, end, line))
    if options.get("caption_style", "clean") not in ("clean", "bold"):
        raise MediaError("Unsupported caption style.")
    if cancelled():
        raise Cancelled("Processing cancelled.")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mp4")
    audio = metadata["has_audio"] and not options.get("mute", False)
    count = len(intervals)
    filters = []
    for index, (start, end) in enumerate(intervals):
        segment_duration = (end - start) / speed
        fade_duration = min(.2, segment_duration / 4)
        fade_start = max(0, segment_duration - fade_duration)
        visual_fade = f",fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_start}:d={fade_duration}" if transition == "fade" else ""
        audio_fade = f",afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_start}:d={fade_duration}" if transition == "fade" else ""
        filters.append(f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},setsar=1{visual_fade}[v{index}]")
        if audio:
            filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,atempo={speed}{audio_fade}[a{index}]")
    joined = "".join(f"[v{i}]" + (f"[a{i}]" if audio else "") for i in range(count))
    filters.append(f"{joined}concat=n={count}:v=1:a={int(audio)}[joined]" + ("[audio]" if audio else ""))
    if aspect == "original":
        width, height = metadata["width"], metadata["height"]
        scale = min(1, (resolution * 16 / 9) / max(width, height), resolution / min(width, height))
        width, height = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
    else:
        width, height = {"9:16": (resolution, resolution * 16 // 9), "16:9": (resolution * 16 // 9, resolution), "1:1": (resolution, resolution)}[aspect]
        width, height = width // 2 * 2, height // 2 * 2
    if fit == "cover":
        visual = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    else:
        visual = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    with tempfile.TemporaryDirectory(prefix="studio-render-", dir=output.parent) as temp:
        font_size = max(16, round(min(width, height) * .045))
        font = "DejaVu Sans"
        overlay_font = f"fontfile='{_filter_path(font_path)}'" if font_path else f"font='{font}'"
        if text:
            text_file = Path(temp) / "overlay.txt"
            text_file.write_text(text, encoding="utf-8")
            visual += f",drawtext={overlay_font}:textfile='{_filter_path(text_file)}':expansion=none:fontsize={font_size}:fontcolor={text_color}:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-text_w)/2:y=h*0.08"
        for index, (start, end, line) in enumerate(checked_captions):
            caption_file = Path(temp) / f"caption-{index}.txt"
            caption_file.write_text(line, encoding="utf-8")
            bold = options.get("caption_style") == "bold"
            caption_font = "DejaVu Sans\\:style=Bold" if bold else font
            caption_font_option = f"fontfile='{_filter_path(font_path)}'" if font_path else f"font='{caption_font}'"
            custom_bold = f":borderw=1:bordercolor={caption_color}" if font_path and bold else ""
            # drawtext textfiles with expansion disabled preserve literal braces,
            # percent signs and backslashes without evaluating filter markup.
            visual += f",drawtext={caption_font_option}:textfile='{_filter_path(caption_file)}':expansion=none:fontsize={font_size}:fontcolor={caption_color}:box=1:boxcolor={caption_background}@0.7:boxborderw=10:x=(w-text_w)/2:y=h*0.85-text_h{custom_bold}:enable='gte(t,{start})*lt(t,{end})'"
        filters.append(f"[joined]{visual}" + ("[composed]" if logo_path else "[video]"))
        if logo_path:
            logo_index = 2 if music_path else 1
            logo_width, logo_height = max(2, width // 5), max(2, height // 5)
            margin = max(8, round(min(width, height) * .03))
            x = str(margin) if logo_position.endswith("left") else f"W-w-{margin}"
            y = str(margin) if logo_position.startswith("top") else f"H-h-{margin}"
            filters.append(f"[{logo_index}:v]scale={logo_width}:{logo_height}:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba[logo]")
            filters.append(f"[composed][logo]overlay=x={x}:y={y}:eof_action=repeat:shortest=0[video]")
        if audio:
            audio_filter = f"volume={volume}"
            if options.get("enhance_audio", False):
                audio_filter += ",highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"
            filters.append(f"[audio]{audio_filter}" + ("[foreground]" if music_path else "[sound]"))
        if music_path:
            filters.append(f"[1:a]atrim=start=0:duration={duration},asetpts=PTS-STARTPTS,volume={music_volume}" + ("[background]" if audio else "[sound]"))
            if audio:
                filters.append("[foreground][background]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[sound]")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *INPUT_OPTIONS, "-i", str(source)]
        if music_path:
            command += ["-stream_loop", "-1", "-protocol_whitelist", "file,pipe", "-format_whitelist", "wav,aac,mov,mp4,m4a,mp3,flac,ogg", "-i", str(music_path)]
        if logo_path:
            command += ["-protocol_whitelist", "file,pipe", "-format_whitelist", "png_pipe", "-i", str(logo_path)]
        command += ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters), "-map", "[video]"]
        if audio or music_path:
            command += ["-map", "[sound]", "-c:a", "aac", "-b:a", "160k"]
        command += ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", "2", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-t", str(duration), "-fs", str(MAX_OUTPUT_BYTES), "-progress", "pipe:1", str(partial)]
        def report(raw):
            matches = re.findall(r"out_time_us=(\d+)", raw)
            if matches:
                progress(min(.98, int(matches[-1]) / 1_000_000 / duration))
        progress(.01)
        try:
            _run(command, cancelled, progress=report)
            if cancelled():
                raise Cancelled("Processing cancelled.")
            rendered = probe(partial)
            if partial.stat().st_size >= MAX_OUTPUT_BYTES or abs(rendered["duration"] - duration) > max(.25, duration * .001):
                raise MediaError("The clip exceeds the 512 MiB export limit or did not render completely. Use a shorter clip or lower resolution.")
            os.replace(partial, output)
        finally:
            partial.unlink(missing_ok=True)
    progress(1)
