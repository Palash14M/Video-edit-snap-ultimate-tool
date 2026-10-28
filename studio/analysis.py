"""Optional local speech recognition and transparent transcript passage selection.

Passage suggestions are text matching, not visual understanding or a prediction
of social engagement. A missing model is an actionable error, never demo text.
"""

from __future__ import annotations

import importlib.util
import math
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path

from studio.media import Cancelled, MediaError, _run, probe


class AnalysisUnavailable(MediaError):
    pass


def _model_path() -> Path | None:
    setting = os.environ.get("STUDIO_WHISPER_MODEL", "").strip()
    if not setting:
        return None
    directory = Path(setting).expanduser().resolve()
    if not directory.is_dir():
        return None
    if not all((directory / name).is_file() and (directory / name).stat().st_size for name in ("model.bin", "config.json", "tokenizer.json")):
        return None
    return directory


def model_available() -> bool:
    return _model_path() is not None and importlib.util.find_spec("faster_whisper") is not None


@lru_cache(maxsize=1)
def _load_model(directory: str):
    from faster_whisper import WhisperModel

    return WhisperModel(directory, device="cpu", compute_type="int8", cpu_threads=2,
                        num_workers=1, local_files_only=True)


def transcribe_video(source: Path, progress, cancelled) -> list[dict]:
    if not model_available():
        raise AnalysisUnavailable("Speech recognition needs the optional faster-whisper package and a complete local CTranslate2 Whisper model. Set STUDIO_WHISPER_MODEL to its directory (model.bin, config.json, tokenizer.json). No model is downloaded automatically.")
    if cancelled():
        raise Cancelled("Transcription cancelled.")
    metadata = probe(source)
    if not metadata["has_audio"]:
        raise MediaError("This video has no audio track to transcribe.")
    progress(.02)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="studio-speech-") as directory:
        audio = Path(directory) / "speech.wav"
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
              "-protocol_whitelist", "file,pipe", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
              "-c:a", "pcm_s16le", "-t", "7200", str(audio)], cancelled, timeout=300)
        progress(.08)
        try:
            model = _load_model(str(_model_path()))
            segments, _info = model.transcribe(str(audio), beam_size=5, word_timestamps=True,
                                               vad_filter=False, condition_on_previous_text=False)
            transcript = []
            for segment in segments:
                if cancelled():
                    raise Cancelled("Transcription cancelled.")
                if time.monotonic() - started > 3600:
                    raise MediaError("Transcription exceeded its one-hour processing limit.")
                start = max(0, float(segment.start))
                end = min(float(segment.end), metadata["duration"])
                text = segment.text.strip()
                if not math.isfinite(start) or not math.isfinite(end) or end <= start or not text:
                    continue
                item = {"start": round(start, 3), "end": round(end, 3), "text": text}
                words = []
                for word in getattr(segment, "words", None) or []:
                    word_start, word_end = float(word.start), float(word.end)
                    if math.isfinite(word_start) and math.isfinite(word_end) and 0 <= word_start < word_end <= metadata["duration"] + .05:
                        words.append({"start": round(word_start, 3), "end": round(word_end, 3), "word": word.word})
                if words:
                    item["words"] = words
                transcript.append(item)
                if len(transcript) > 20000:
                    raise MediaError("Transcript exceeds the supported 20,000-segment limit.")
                progress(min(.99, .08 + .9 * end / metadata["duration"]))
        except (Cancelled, MediaError):
            raise
        except Exception as error:
            raise AnalysisUnavailable("The configured local speech model could not run. Check its files, language support, package compatibility and available memory.") from error
    if cancelled():
        raise Cancelled("Transcription cancelled.")
    progress(1)
    return transcript


def suggest_clips(transcript: list, duration: float, keywords: str = "", *, clip_duration: float = 30) -> list[dict]:
    """Find up to ten real, non-overlapping transcript passages.

    Comma-separated search phrases use case-insensitive substring matching. This
    intentionally makes no claim of semantic topic recognition or virality.
    """
    try:
        duration = float(duration)
    except (ValueError, TypeError) as error:
        raise MediaError("Video duration must be a positive finite number.") from error
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("Video duration must be a positive finite number.")
    try:
        clip_duration = float(clip_duration)
    except (TypeError, ValueError) as error:
        raise MediaError("Requested clip duration must be between 5 and 180 seconds.") from error
    if not math.isfinite(clip_duration) or not 5 <= clip_duration <= 180:
        raise MediaError("Requested clip duration must be between 5 and 180 seconds.")
    if not isinstance(transcript, list) or len(transcript) > 20000:
        raise MediaError("Transcript must contain at most 20,000 timed segments.")
    if not isinstance(keywords, str) or len(keywords) > 500:
        raise MediaError("Search phrases must be at most 500 characters.")
    phrases = [phrase.strip().casefold() for phrase in keywords.split(",") if phrase.strip()]
    rows = []
    for item in transcript:
        try:
            start, end = float(item["start"]), float(item["end"])
            text = item["text"]
        except (TypeError, KeyError, ValueError) as error:
            raise MediaError("Transcript segments need valid start, end and text fields.") from error
        if not all(map(math.isfinite, (start, end))) or not 0 <= start < end <= duration + .001 or not isinstance(text, str):
            raise MediaError("Transcript timings must fall inside the source video.")
        if text.strip():
            rows.append({"start": start, "end": end, "text": text.strip()})
    rows.sort(key=lambda row: row["start"])
    candidates = []
    last_end = -1
    for index, row in enumerate(rows):
        matches = [phrase for phrase in phrases if phrase in row["text"].casefold()]
        if phrases and not matches:
            continue
        if row["start"] < last_end or row["end"] - row["start"] > clip_duration:
            continue
        end = row["end"]
        for following in rows[index + 1:]:
            if following["start"] - end > 5 or following["end"] - row["start"] > clip_duration:
                break
            end = max(end, following["end"])
        reason = ("Transcript passage matching: " + ", ".join(matches) + ".") if phrases else "Consecutive transcript sentences, grouped at their original timestamps."
        candidates.append({"start": row["start"], "end": end, "reason": reason + " Review the passage before exporting."})
        last_end = end
        if len(candidates) == 10:
            break
    return candidates
