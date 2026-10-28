import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio.analysis import AnalysisUnavailable, model_available, suggest_clips, transcribe_video
from studio.media import MediaError


class AnalysisTests(unittest.TestCase):
    def test_missing_local_model_cannot_fabricate_transcript(self):
        with patch.dict(os.environ, {"STUDIO_WHISPER_MODEL": ""}):
            self.assertFalse(model_available())
            with self.assertRaisesRegex(AnalysisUnavailable, "STUDIO_WHISPER_MODEL"):
                transcribe_video(Path("does-not-exist.mp4"), lambda _: None, lambda: False)

    def test_empty_model_directory_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STUDIO_WHISPER_MODEL": directory}):
            self.assertFalse(model_available())

    def test_empty_transcript_produces_no_suggestions(self):
        self.assertEqual(suggest_clips([], 120, ""), [])

    def test_suggestions_are_source_aligned_and_inside_duration(self):
        transcript = [
            {"start": 2, "end": 12, "text": "An introduction to the story."},
            {"start": 13, "end": 25, "text": "Here is the main discovery."},
            {"start": 26, "end": 44, "text": "This sentence explains how it works."},
            {"start": 45, "end": 65, "text": "The final outcome and next steps."},
        ]
        suggestions = suggest_clips(transcript, 65, "")
        self.assertTrue(suggestions)
        for clip in suggestions:
            self.assertIn(clip["start"], [2, 13, 26, 45])
            self.assertIn(clip["end"], [12, 25, 44, 65])
            self.assertLess(clip["start"], clip["end"])
            self.assertLessEqual(clip["end"], 65)
            self.assertIn("reason", clip)
            self.assertNotIn("virality", clip)

    def test_keywords_filter_rather_than_ignoring_request(self):
        transcript = [
            {"start": 0, "end": 15, "text": "The basketball game starts here."},
            {"start": 100, "end": 120, "text": "A discussion about gardening and plants."},
        ]
        selected = suggest_clips(transcript, 130, "gardening")
        self.assertTrue(selected)
        self.assertEqual(selected[0]["start"], 100)
        self.assertEqual(suggest_clips(transcript, 130, "astronomy"), [])

    def test_keyword_matching_supports_non_latin_text(self):
        selected = suggest_clips([{"start": 4, "end": 20, "text": "यह क्रिकेट की कहानी है"}], 30, "क्रिकेट")
        self.assertEqual(selected[0]["start"], 4)

    def test_nonfinite_or_negative_durations_are_rejected(self):
        for duration in (0, -1, math.nan, math.inf):
            with self.subTest(duration=duration), self.assertRaises(MediaError):
                suggest_clips([], duration, "")

    def test_invalid_transcript_timing_cannot_create_invalid_clips(self):
        transcript = [
            {"start": math.nan, "end": 3, "text": "bad"},
            {"start": 12, "end": 11, "text": "backwards"},
            {"start": -2, "end": 5, "text": "negative"},
            {"start": 20, "end": 80, "text": "past the video"},
        ]
        with self.assertRaises(MediaError):
            suggest_clips(transcript, 30, "")

    def test_out_of_order_transcript_is_normalized(self):
        transcript = [{"start": 20, "end": 30, "text": "Second sentence."}, {"start": 0, "end": 10, "text": "First sentence."}]
        clips = suggest_clips(transcript, 30, "first")
        self.assertEqual(clips[0]["start"], 0)
        self.assertLessEqual(clips[0]["end"], 30)

    def test_requested_clip_duration_limits_sentence_grouping(self):
        transcript = [
            {"start": 0, "end": 8, "text": "First sentence."},
            {"start": 8, "end": 16, "text": "Second sentence."},
            {"start": 16, "end": 24, "text": "Third sentence."},
        ]
        clips = suggest_clips(transcript, 24, clip_duration=10)
        self.assertEqual(clips[0]["end"], 8)
        self.assertTrue(all(clip["end"] - clip["start"] <= 10 for clip in clips))

    def test_requested_long_clip_duration_can_group_past_sixty_seconds(self):
        transcript = [{"start": n, "end": n + 10, "text": f"Sentence {n}."} for n in range(0, 120, 10)]
        clips = suggest_clips(transcript, 120, clip_duration=90)
        self.assertGreater(clips[0]["end"], 60)
        self.assertLessEqual(clips[0]["end"], 90)

    def test_requested_clip_duration_rejects_nonfinite_or_unsupported_values(self):
        for duration in (1, 181, math.nan, math.inf, "bad"):
            with self.subTest(duration=duration), self.assertRaises(MediaError):
                suggest_clips([], 100, clip_duration=duration)


if __name__ == "__main__":
    unittest.main()
