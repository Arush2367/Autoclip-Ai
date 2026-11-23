import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services import meta_publisher
from backend.services.secure_storage import IS_WINDOWS, load_secure_json


class UnifiedLoginAccountTests(unittest.TestCase):
    def test_discovers_business_id_and_assigned_instagram_accounts(self):
        replies = [
            {"data": [{"id": "ig-1", "username": "reel_for_everything"}]},
        ]
        with patch.object(meta_publisher, "graph_request", side_effect=replies) as graph:
            business_id, accounts = meta_publisher.fetch_unified_instagram_accounts("SUAT-test-token")

        self.assertIsNone(business_id)
        self.assertEqual(accounts, [{"id": "ig-1", "username": "reel_for_everything"}])
        self.assertEqual(graph.call_count, 1)
        self.assertEqual(graph.call_args.args[:2], ("GET", "me/assigned_instagram_accounts"))
        self.assertEqual(graph.call_args.kwargs["access_token"], "SUAT-test-token")

    def test_missing_assigned_instagram_account_has_actionable_error(self):
        with patch.object(meta_publisher, "graph_request", return_value={"data": []}):
            with self.assertRaisesRegex(meta_publisher.MetaPublisherError, "no Instagram accounts"):
                meta_publisher.fetch_unified_instagram_accounts("token")

    def test_connect_saves_token_locally_and_never_returns_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            token_file = Path(temp_dir) / "meta_auth.json"
            with patch.object(meta_publisher, "META_TOKEN_FILE", token_file), \
                 patch.object(meta_publisher, "fetch_unified_instagram_accounts",
                              return_value=("business-1", [{"id": "ig-1", "username": "reel_for_everything"}])):
                result = meta_publisher.connect_with_tokens(
                    instagram_access_token="private-suat-token",
                )

            stored_bytes = token_file.read_bytes()
            saved = load_secure_json(token_file)
            self.assertTrue(result["instagram"]["connected"])
            self.assertEqual(result["instagram"]["account_name"], "reel_for_everything")
            self.assertNotIn("private-suat-token", json.dumps(result))
            self.assertEqual(saved["instagram"]["access_token"], "private-suat-token")
            if IS_WINDOWS:
                self.assertNotIn(b"private-suat-token", stored_bytes)

    def test_facebook_page_token_resolves_page_identity_without_category_field(self):
        replies = [
            {"data": {"is_valid": True, "app_id": "app-1", "type": "PAGE", "profile_id": "page-1"}},
            {"id": "page-1", "name": "Ashu"},
        ]
        with patch.object(meta_publisher, "META_APP_ID", "app-1"), \
             patch.object(meta_publisher, "META_APP_SECRET", "app-secret"), \
             patch.object(meta_publisher, "graph_request", side_effect=replies) as graph:
            page = meta_publisher.fetch_facebook_page("page-token")
        self.assertEqual(page, {"id": "page-1", "name": "Ashu"})
        self.assertEqual(graph.call_args_list[0].args[:2], ("GET", "debug_token"))
        self.assertEqual(graph.call_args_list[0].kwargs["params"], {"input_token": "page-token"})
        self.assertEqual(graph.call_args_list[1].args[:2], ("GET", "me"))
        self.assertEqual(graph.call_args_list[1].kwargs["params"], {"fields": "id,name"})

    def test_facebook_user_token_is_not_accepted_as_a_page_token(self):
        with patch.object(meta_publisher, "META_APP_ID", "app-1"), \
             patch.object(meta_publisher, "META_APP_SECRET", "app-secret"), \
             patch.object(meta_publisher, "graph_request", return_value={"data": {"is_valid": True, "app_id": "app-1", "type": "USER"}}):
            with self.assertRaisesRegex(meta_publisher.MetaPublisherError, "Facebook User token, not a Page token"):
                meta_publisher.fetch_facebook_page("user-token")

    def test_facebook_token_from_another_app_is_rejected(self):
        with patch.object(meta_publisher, "META_APP_ID", "app-1"), \
             patch.object(meta_publisher, "META_APP_SECRET", "app-secret"), \
             patch.object(meta_publisher, "graph_request", return_value={"data": {"is_valid": True, "app_id": "other-app", "type": "PAGE"}}):
            with self.assertRaisesRegex(meta_publisher.MetaPublisherError, "different Meta app"):
                meta_publisher.fetch_facebook_page("page-token")

    def test_safe_connection_status_never_returns_tokens(self):
        result = meta_publisher.safe_connection_status({
            "instagram": {"access_token": "secret-ig", "account_id": "ig-1", "account_name": "reel_for_everything"},
            "facebook": {"access_token": "secret-page", "page_id": "page-1", "page_name": "Ashu"},
        })
        self.assertTrue(result["instagram"]["connected"])
        self.assertTrue(result["facebook"]["connected"])
        self.assertNotIn("secret-ig", json.dumps(result))
        self.assertNotIn("secret-page", json.dumps(result))


class MetaPublishingFlowTests(unittest.TestCase):
    def test_instagram_reel_uses_unified_login_suat_and_resumable_container(self):
        replies = [
            {"id": "container-1"},
            {"status_code": "FINISHED"},
            {"id": "media-1"},
            {"id": "media-1", "permalink": "https://www.instagram.com/reel/example/"},
        ]
        with patch.object(meta_publisher, "graph_request", side_effect=replies) as graph, \
             patch.object(meta_publisher, "upload_local_video", return_value={"success": True}) as upload, \
             patch.object(meta_publisher.time, "sleep"):
            result = meta_publisher.publish_instagram_reel(
                instagram_account_id="ig-1", instagram_access_token="suat-token",
                video_path=Path(__file__), caption="Test caption", is_ai_generated=True,
            )
        self.assertEqual(result["media_id"], "media-1")
        self.assertEqual(result["url"], "https://www.instagram.com/reel/example/")
        self.assertEqual(graph.call_count, 4)
        self.assertEqual(graph.call_args_list[0].args[:2], ("POST", "ig-1/media"))
        self.assertEqual(graph.call_args_list[0].kwargs["access_token"], "suat-token")
        self.assertEqual(graph.call_args_list[2].args[:2], ("POST", "ig-1/media_publish"))
        self.assertEqual(upload.call_count, 1)

    def test_facebook_reel_uses_page_access_token_start_upload_finish(self):
        replies = [
            {"id": "page-1", "name": "Ashu"},
            {"video_id": "fb-video-1", "upload_url": "https://rupload.facebook.com/video-upload/v27.0/fb-video-1"},
            {"success": True, "post_id": "fb-post-1"},
        ]
        with patch.object(meta_publisher, "graph_request", side_effect=replies) as graph, \
             patch.object(meta_publisher, "upload_local_video", return_value={"success": True}) as upload:
            result = meta_publisher.publish_facebook_reel(
                page_id="page-1", page_access_token="page-token", video_path=Path(__file__),
                title="Demo", caption="Demo caption", is_ai_generated=True,
            )
        self.assertEqual(result["media_id"], "fb-post-1")
        self.assertEqual(graph.call_count, 3)
        self.assertEqual(graph.call_args_list[0].args[:2], ("GET", "page-1"))
        self.assertEqual(graph.call_args_list[0].kwargs["access_token"], "page-token")
        self.assertEqual(graph.call_args_list[1].args[:2], ("POST", "page-1/video_reels"))
        self.assertEqual(graph.call_args_list[1].kwargs["data"]["upload_phase"], "start")
        self.assertEqual(graph.call_args_list[2].kwargs["data"]["upload_phase"], "finish")
        self.assertEqual(graph.call_args_list[0].kwargs["params"], {"fields": "id,name"})
        self.assertEqual(upload.call_count, 1)

    def test_upload_rejects_untrusted_meta_upload_host(self):
        with self.assertRaisesRegex(meta_publisher.MetaPublisherError, "unexpected media upload URL"):
            meta_publisher.upload_local_video("https://attacker.example/upload", "token", Path(__file__))

    def test_upload_rejects_meta_hostname_with_userinfo_or_nonstandard_port(self):
        for url in (
            "https://attacker@rupload.facebook.com/upload",
            "https://rupload.facebook.com:8443/upload",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(meta_publisher.MetaPublisherError, "unexpected media upload URL"):
                    meta_publisher.upload_local_video(url, "token", Path(__file__))


if __name__ == "__main__":
    unittest.main()
