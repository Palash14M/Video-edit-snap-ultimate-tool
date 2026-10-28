import json
import math
import array
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio.media import Cancelled, MediaError, prepare_preview, probe, render, validate_url


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.temp.name) / "source.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=12:d=2",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=12:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-threads", "1",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.source),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, name):
        return Path(self.temp.name) / name

    def test_probe_reports_real_video_streams(self):
        info = probe(self.source)
        self.assertAlmostEqual(info["duration"], 4, delta=.1)
        self.assertEqual((info["width"], info["height"]), (320, 240))
        self.assertTrue(info["has_audio"])

    def test_reorders_segments_and_preserves_audio(self):
        output = self.output("reordered.mp4")
        progress = []
        render(self.source, output, {"segments": [{"start": 2, "end": 3}, {"start": 0, "end": 1}]}, progress.append, lambda: False)
        info = probe(output)
        self.assertAlmostEqual(info["duration"], 2, delta=.15)
        self.assertTrue(info["has_audio"])
        self.assertEqual(progress[-1], 1)
        frame = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "0.3", "-i", str(output), "-vf", "scale=1:1", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True).stdout
        self.assertGreater(frame[2], frame[0] + 100)

    def test_vertical_contain_and_mute(self):
        output = self.output("vertical.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": .5}], "aspect": "9:16", "resolution": 720, "fit": "contain", "mute": True}, lambda _: None, lambda: False)
        info = probe(output)
        self.assertEqual((info["width"], info["height"]), (720, 1280))
        self.assertFalse(info["has_audio"])

    def test_square_cover_captions_text_audio_enhancement(self):
        output = self.output("square.mp4")
        render(self.source, output, {"segments": [{"start": .5, "end": 1.5}], "aspect": "1:1", "fit": "cover", "text": "It's 50%: [safe] \\ text", "captions": [{"start": 0, "end": .8, "text": "hello {world} \\ N"}], "enhance_audio": True, "volume": .5}, lambda _: None, lambda: False)
        info = probe(output)
        self.assertEqual((info["width"], info["height"]), (720, 720))
        self.assertAlmostEqual(info["duration"], 1, delta=.15)
        self.assertTrue(info["has_audio"])

    def test_silent_source_exports_without_inventing_audio(self):
        silent = self.output("silent.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(self.source), "-an", "-c:v", "copy", str(silent)], check=True)
        output = self.output("silent-output.mp4")
        render(silent, output, {"segments": [{"start": 1, "end": 2}], "enhance_audio": True}, lambda _: None, lambda: False)
        self.assertFalse(probe(output)["has_audio"])

    def test_caption_styles_change_actual_caption_pixels(self):
        frames = []
        for style in ('clean', 'bold'):
            output = self.output(f'caption-{style}.mp4')
            render(self.source, output, {'segments':[{'start':0,'end':1}],
                   'captions':[{'start':0,'end':.8,'text':'A real caption'}], 'caption_style':style},
                   lambda _:None, lambda:False)
            frame = subprocess.run(['ffmpeg','-v','error','-ss','0.3','-i',str(output),
                                    '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],
                                   check=True, capture_output=True).stdout
            frames.append(frame)
        # A missing bold-font selection would make the decoded frames identical.
        self.assertEqual(len(frames[0]), 320 * 240 * 3)
        self.assertNotEqual(frames[0], frames[1])

    def test_playback_speed_changes_real_audio_video_duration(self):
        output = self.output("speed.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 2}], "speed": 2}, lambda _: None, lambda: False)
        metadata = probe(output)
        self.assertAlmostEqual(metadata["duration"], 1, delta=.15)
        self.assertTrue(metadata["has_audio"])

    def test_invalid_timing_is_rejected_before_output(self):
        for start, end in [(-1, 1), (2, 1), (0, 8), (math.nan, 2), (0, math.inf)]:
            with self.subTest(start=start, end=end), self.assertRaises(MediaError):
                render(self.source, self.output("invalid.mp4"), {"segments": [{"start": start, "end": end}]}, lambda _: None, lambda: False)
        self.assertFalse(self.output("invalid.mp4").exists())

    def test_cancel_does_not_publish_partial_output(self):
        output = self.output("cancelled.mp4")
        with self.assertRaises(Cancelled):
            render(self.source, output, {"segments": [{"start": 0, "end": 1}]}, lambda _: None, lambda: True)
        self.assertFalse(output.exists())

    def test_url_validation_only_accepts_single_youtube_video(self):
        self.assertEqual(validate_url("https://youtu.be/abcdefghijk"), "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(validate_url("https://www.youtube.com/watch?v=abcdefghijk&t=20"), "https://www.youtube.com/watch?v=abcdefghijk")
        for url in ["http://127.0.0.1/video", "https://youtube.com.evil.test/watch?v=abcdefghijk", "https://user:pass@youtube.com/watch?v=abcdefghijk", "file:///etc/passwd", "https://youtube.com/playlist?list=abc", "https://youtube.com/watch?v=abcdefghijk&list=abc", "https://youtube.com:444/watch?v=abcdefghijk", "https://youtube.com/watch?v=short"]:
            with self.subTest(url=url), self.assertRaises(MediaError):
                validate_url(url)

    def test_probe_rejects_nonvideo(self):
        invalid = self.output("not-video.txt")
        invalid.write_text("not a video")
        with self.assertRaises(MediaError):
            probe(invalid)

    def test_uploaded_concat_playlist_cannot_read_another_local_file(self):
        playlist = self.output("hostile.mp4")
        playlist.write_text("ffconcat version 1.0\nfile 'source.mp4'\nduration 4\n")
        with self.assertRaises(MediaError):
            probe(playlist)

    def test_public_errors_do_not_expose_private_filesystem_paths(self):
        source = self.output("private-location-123.mp4")
        source.write_bytes(b"not video")
        with self.assertRaises(MediaError) as raised:
            probe(source)
        self.assertNotIn(str(source), str(raised.exception))
        self.assertNotIn("private-location-123", str(raised.exception))

    def test_uploaded_hls_playlist_is_rejected_even_for_local_segments(self):
        transport = self.output("segment.ts")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(self.source), "-c", "copy", str(transport)], check=True)
        playlist = self.output("hostile.m3u8")
        playlist.write_text("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXTINF:4.0,\nsegment.ts\n#EXT-X-ENDLIST\n")
        with self.assertRaises(MediaError):
            probe(playlist)

    def test_common_self_contained_containers_remain_supported(self):
        for extension in ("webm", "mov", "avi", "ts"):
            with self.subTest(extension=extension):
                source = self.output("container-test." + extension)
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(self.source), "-t", "0.5", "-an", "-threads", "1", str(source)], check=True)
                self.assertGreater(probe(source)["duration"], .1)

    def test_webm_preview_is_browser_h264_aac_mp4(self):
        source = self.output("preview-input.webm")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(self.source), "-t", "1", "-threads", "1", str(source)], check=True)
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            progress = []
            output = prepare_preview(source, Path(directory), progress.append, lambda: False)
            metadata = json.loads(subprocess.run(["ffprobe", "-loglevel", "error", "-show_format", "-show_streams", "-of", "json", str(output)], check=True, capture_output=True).stdout)
            self.assertEqual(output.suffix, ".mp4")
            self.assertEqual(next(s["codec_name"] for s in metadata["streams"] if s["codec_type"] == "video"), "h264")
            self.assertEqual(next(s["codec_name"] for s in metadata["streams"] if s["codec_type"] == "audio"), "aac")
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 1, delta=.15)
            self.assertEqual(progress[-1], 1)
            raw = output.read_bytes()
            self.assertLess(raw.index(b"moov"), raw.index(b"mdat"))

    def test_preview_cancel_does_not_publish_partial_media(self):
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            with self.assertRaises(Cancelled):
                prepare_preview(self.source, Path(directory), lambda _: None, lambda: True)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_preview_retains_small_original_dimensions(self):
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            output = prepare_preview(self.source, Path(directory), lambda _: None, lambda: False)
            self.assertEqual((probe(output)["width"], probe(output)["height"]), (320, 240))

    def test_preview_can_cancel_after_encoder_has_started(self):
        checks = []
        def cancel():
            checks.append(True)
            return len(checks) >= 3
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            with self.assertRaises(Cancelled):
                prepare_preview(self.source, Path(directory), lambda _: None, cancel)
            self.assertFalse((Path(directory) / "preview.mp4").exists())
            self.assertFalse((Path(directory) / "preview.partial.mp4").exists())

    def test_export_size_limit_rejects_truncation_and_removes_partial(self):
        output = self.output("limited-export.mp4")
        with patch("studio.media.MAX_OUTPUT_BYTES", 1024):
            with self.assertRaises(MediaError):
                render(self.source, output, {"segments": [{"start": 0, "end": 4}]}, lambda _: None, lambda: False)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_name("limited-export.partial.mp4").exists())

    def test_export_rejects_more_than_fifty_segments(self):
        with self.assertRaises(MediaError):
            render(self.source, self.output("too-many-segments.mp4"), {"segments": [{"start": 0, "end": 1}] * 51}, lambda _: None, lambda: False)

    def test_export_rejects_more_than_ten_minutes(self):
        source = self.output("long-source.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:r=1:d=601", "-c:v", "libx264", "-threads", "1", str(source)], check=True)
        with self.assertRaises(MediaError):
            render(source, self.output("too-long-export.mp4"), {"segments": [{"start": 0, "end": 601}]}, lambda _: None, lambda: False)

    def decoded_frame(self, path, timestamp="0.5"):
        return subprocess.run(["ffmpeg", "-v", "error", "-ss", timestamp, "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout

    def test_fade_transition_starts_black_without_changing_timeline_length(self):
        output = self.output("fade.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 1}, {"start": 2, "end": 3}], "transition": "fade"}, lambda _: None, lambda: False)
        first = self.decoded_frame(output, "0")
        middle = self.decoded_frame(output)
        self.assertLess(max(first[:3]), 15)
        self.assertGreater(middle[0], 200)
        self.assertAlmostEqual(probe(output)["duration"], 2, delta=.15)

    def test_caption_color_and_custom_font_change_rendered_pixels(self):
        font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")
        self.assertTrue(font.is_file())
        output = self.output("colored-caption.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 1}], "font_path": font,
               "captions": [{"start": 0, "end": 1, "text": "Custom caption"}], "caption_color": "#00FF00",
               "caption_background": "#0000FF", "caption_style": "bold"}, lambda _: None, lambda: False)
        frame = self.decoded_frame(output)
        pixels = [frame[index:index+3] for index in range(0, len(frame), 3)]
        self.assertTrue(any(g > 130 and g > r * 1.5 and g > b * 1.5 for r, g, b in pixels))
        self.assertTrue(any(b > 100 and b > r * 1.5 and b > g * 1.5 for r, g, b in pixels))
        default = self.output("default-font-caption.mp4")
        render(self.source, default, {"segments": [{"start": 0, "end": 1}], "captions": [{"start": 0, "end": 1, "text": "Custom caption"}], "caption_color": "#00FF00", "caption_background": "#0000FF", "caption_style": "bold"}, lambda _: None, lambda: False)
        self.assertNotEqual(frame, self.decoded_frame(default))

    def test_logo_appears_only_in_selected_corner(self):
        logo = self.output("logo.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=lime:s=64x32", "-frames:v", "1", "-threads", "1", str(logo)], check=True)
        for corner, x, y in [("top-left", 16, 16), ("bottom-right", 304, 224)]:
            with self.subTest(corner=corner):
                output = self.output("logo-" + corner + ".mp4")
                render(self.source, output, {"segments": [{"start": 0, "end": 1}], "logo_path": logo, "logo_position": corner}, lambda _: None, lambda: False)
                frame = self.decoded_frame(output)
                point = (y * 320 + x) * 3
                r, g, b = frame[point:point+3]
                self.assertGreater(g, r + 100)
                opposite = ((240 - y) * 320 + (320 - x)) * 3
                self.assertGreater(frame[opposite], frame[opposite+1] + 100)

    def test_music_mixes_new_frequency_and_loops_to_full_export_duration(self):
        music = self.output("music.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.25:sample_rate=8000", str(music)], check=True)
        output = self.output("music-mix.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 2}], "music_path": music, "music_volume": 1}, lambda _: None, lambda: False)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(output), "-t", "0.25", "-ar", "8000", "-ac", "1", "-f", "s16le", "pipe:1"], check=True, capture_output=True).stdout
        samples = array.array("h", raw)
        def energy(frequency):
            sine = sum(value * math.sin(2 * math.pi * frequency * n / 8000) for n, value in enumerate(samples))
            cosine = sum(value * math.cos(2 * math.pi * frequency * n / 8000) for n, value in enumerate(samples))
            return math.hypot(sine, cosine) / len(samples)
        self.assertGreater(energy(440), 100)
        self.assertGreater(energy(880), 100)
        self.assertAlmostEqual(probe(output)["duration"], 2, delta=.15)

    def test_music_can_supply_audio_when_source_is_muted(self):
        music = self.output("muted-music.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.25", str(music)], check=True)
        output = self.output("muted-music.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 1}], "mute": True, "music_path": music}, lambda _: None, lambda: False)
        self.assertTrue(probe(output)["has_audio"])

    def test_logo_music_and_text_can_render_together(self):
        music = self.output("combined-music.wav")
        logo = self.output("combined-logo.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.25", str(music)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=lime:s=64x32", "-frames:v", "1", "-threads", "1", str(logo)], check=True)
        output = self.output("combined-branding.mp4")
        render(self.source, output, {"segments": [{"start": 0, "end": 1}], "music_path": music,
               "logo_path": logo, "logo_position": "bottom-left", "text": "Brand", "text_color": "#00FFFF",
               "transition": "fade"}, lambda _: None, lambda: False)
        frame = self.decoded_frame(output)
        point = (224 * 320 + 16) * 3
        self.assertGreater(frame[point+1], frame[point] + 100)
        self.assertTrue(probe(output)["has_audio"])
        pixels = [frame[index:index+3] for index in range(0, len(frame), 3)]
        self.assertTrue(any(g > 130 and b > 130 and r < 80 for r, g, b in pixels))

    def test_invalid_branding_options_are_rejected_without_filter_injection(self):
        invalid_options = [
            {"caption_color": "red:fontsize=999"}, {"caption_background": "#000000,negate"}, {"text_color": "green"},
            {"transition": "spin"}, {"logo_position": "x=2"}, {"music_volume": math.nan}, {"music_volume": 2},
            {"font_path": "/etc/passwd"}, {"logo_path": "/etc/passwd"}, {"music_path": "/etc/passwd"},
        ]
        for invalid in invalid_options:
            with self.subTest(options=invalid), self.assertRaises(MediaError):
                render(self.source, self.output("invalid-branding.mp4"), {"segments": [{"start": 0, "end": 1}], **invalid}, lambda _: None, lambda: False)


if __name__ == "__main__":
    unittest.main()
