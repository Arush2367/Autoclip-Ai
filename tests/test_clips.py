import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services import clip_renderer
from backend.services.clip_renderer import build_srt, build_video_filter, render_clip


class SubtitleTests(unittest.TestCase):
    def test_build_srt_clips_segment_to_clip_boundaries(self):
        srt = build_srt(
            [
                {"start": 8.0, "end": 14.0, "text": "This begins before the clip."},
                {"start": 12.0, "end": 18.0, "text": "This is inside the clip."},
                {"start": 38.0, "end": 44.0, "text": "This continues after the clip."},
            ],
            10.0,
            40.0,
        )
        self.assertIn("00:00:00,000 --> 00:00:04,000", srt)
        self.assertIn("00:00:02,000 --> 00:00:08,000", srt)
        self.assertIn("00:00:28,000 --> 00:00:30,000", srt)
        self.assertEqual(srt.count(" --> "), 3)

    def test_build_srt_ignores_invalid_or_outside_segments(self):
        srt = build_srt(
            [
                {"start": 0, "end": 2, "text": "Outside"},
                {"start": 32, "end": 30, "text": "Invalid"},
                {"start": 31, "end": 33, "text": ""},
            ],
            10,
            40,
        )
        self.assertEqual(srt, "")

    def test_video_filter_has_vertical_dimensions_and_optional_subtitles(self):
        no_subtitles = build_video_filter()
        with_subtitles = build_video_filter("sample.srt")
        self.assertIn("scale=1080:1920", no_subtitles)
        self.assertIn("crop=1080:1920", no_subtitles)
        self.assertNotIn("subtitles=", no_subtitles)
        self.assertIn("subtitles=filename='sample.srt'", with_subtitles)

    def test_render_rejects_out_of_range_duration_before_external_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            source.write_bytes(b"test")
            with self.assertRaisesRegex(ValueError, "between 30 and 40 seconds"):
                render_clip(
                    source_path=source,
                    output_path=root / "clips" / "out.mp4",
                    temp_dir=root / "temp",
                    clip_id="clip-test",
                    clip_start=0,
                    clip_end=20,
                    transcript_segments=[],
                )

    def test_render_clip_creates_verified_output_with_mocked_ffmpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            output = root / "clips" / "clip.mp4"
            temp_dir = root / "temp"

            def fake_run(command, **kwargs):
                # First subprocess is FFprobe audio detection; second is FFmpeg rendering.
                if command[0] == "ffprobe":
                    return type("Result", (), {"returncode": 0, "stdout": "0\n", "stderr": ""})()
                partial = Path(command[-1])
                partial.parent.mkdir(parents=True, exist_ok=True)
                partial.write_bytes(b"rendered mp4")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            metadata = {
                "duration_seconds": 35.0,
                "width": 1080,
                "height": 1920,
                "video_codec": "h264",
            }
            with patch.object(clip_renderer.shutil, "which", side_effect=lambda name: name), \
                 patch.object(clip_renderer.subprocess, "run", side_effect=fake_run), \
                 patch.object(clip_renderer, "probe_video", return_value=metadata):
                result = render_clip(
                    source_path=source,
                    output_path=output,
                    temp_dir=temp_dir,
                    clip_id="clip-test",
                    clip_start=5,
                    clip_end=40,
                    transcript_segments=[{"start": 5, "end": 12, "text": "A caption appears."}],
                )

            self.assertTrue(output.is_file())
            self.assertEqual(result["metadata"], metadata)
            self.assertEqual(result["subtitle_status"], "burned_in")
            self.assertFalse((temp_dir / "clip-test.srt").exists())


if __name__ == "__main__":
    unittest.main()
