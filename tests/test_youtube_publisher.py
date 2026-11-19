import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.youtube_publisher import (
    YouTubePublisherError,
    build_video_body,
    parse_tags,
    upload_video,
)


class YouTubeMetadataTests(unittest.TestCase):
    def test_build_body_keeps_selected_visibility(self):
        body = build_video_body(
            title="A test Short",
            description="Test description",
            tags=["shorts", "story"],
            privacy_status="private",
            made_for_kids=False,
        )
        self.assertEqual(body["snippet"]["title"], "A test Short")
        self.assertEqual(body["snippet"]["tags"], ["shorts", "story"])
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])
        self.assertNotIn("containsSyntheticMedia", body["status"])

    def test_build_body_includes_synthetic_disclosure_only_when_selected(self):
        body = build_video_body(
            title="Test",
            description="",
            tags=[],
            privacy_status="unlisted",
            made_for_kids=True,
            contains_synthetic_media=True,
        )
        self.assertTrue(body["status"]["containsSyntheticMedia"])

    def test_invalid_privacy_is_rejected(self):
        with self.assertRaises(YouTubePublisherError):
            build_video_body(
                title="Test", description="", tags=[], privacy_status="friends", made_for_kids=False
            )

    def test_title_limit_is_enforced(self):
        with self.assertRaises(YouTubePublisherError):
            build_video_body(
                title="x" * 101, description="", tags=[], privacy_status="private", made_for_kids=False
            )

    def test_description_limit_is_enforced(self):
        with self.assertRaises(YouTubePublisherError):
            build_video_body(
                title="Test", description="x" * 5001, tags=[], privacy_status="private", made_for_kids=False
            )

    def test_parse_tags_deduplicates_case_insensitively(self):
        self.assertEqual(parse_tags("Shorts, story, shorts, Story"), ["Shorts", "story"])

    def test_parse_tags_enforces_combined_limit(self):
        with self.assertRaises(YouTubePublisherError):
            parse_tags("a" * 251 + "," + "b" * 250)

    def test_upload_uses_resumable_media_and_reports_progress(self):
        class FakeMediaFileUpload:
            def __init__(self, filename, **kwargs):
                self.filename = filename
                self.kwargs = kwargs

        class FakeUploadStatus:
            def progress(self):
                return 0.5

        class FakeRequest:
            def __init__(self):
                self.calls = 0

            def next_chunk(self, num_retries=0):
                self.calls += 1
                if self.calls == 1:
                    return FakeUploadStatus(), None
                return None, {"id": "youtube-video-123"}

        class FakeVideos:
            def __init__(self):
                self.request = FakeRequest()
                self.kwargs = None

            def insert(self, **kwargs):
                self.kwargs = kwargs
                return self.request

        class FakeService:
            def __init__(self):
                self.video_resource = FakeVideos()

            def videos(self):
                return self.video_resource

        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "clip.mp4"
            video.write_bytes(b"sample mp4")
            fake_service = FakeService()
            fake_http_module = types.ModuleType("googleapiclient.http")
            fake_http_module.MediaFileUpload = FakeMediaFileUpload
            fake_package = types.ModuleType("googleapiclient")
            fake_package.__path__ = []
            fake_package.http = fake_http_module
            progress = []
            with patch.dict(sys.modules, {
                "googleapiclient": fake_package,
                "googleapiclient.http": fake_http_module,
            }), patch("backend.services.youtube_publisher._load_credentials", return_value=object()), \
                 patch("backend.services.youtube_publisher._build_service", return_value=fake_service):
                result = upload_video(
                    video_path=video,
                    title="A test Short",
                    description="",
                    tags=["test"],
                    privacy_status="private",
                    made_for_kids=False,
                    progress_callback=progress.append,
                )

        self.assertEqual(result["id"], "youtube-video-123")
        self.assertEqual(progress, [50])
        self.assertTrue(fake_service.video_resource.kwargs["media_body"].kwargs["resumable"])
        self.assertEqual(fake_service.video_resource.kwargs["body"]["status"]["privacyStatus"], "private")
        self.assertFalse(fake_service.video_resource.kwargs["body"]["status"]["selfDeclaredMadeForKids"])


if __name__ == "__main__":
    unittest.main()
