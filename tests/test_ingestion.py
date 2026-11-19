import unittest

from backend.services.ingestion import get_extension, safe_display_filename, signature_matches


class IngestionHelperTests(unittest.TestCase):
    def test_safe_filename_removes_path(self):
        self.assertEqual(safe_display_filename(r"C:\\fake\\movie clip.mp4"), "movie clip.mp4")

    def test_extension_is_lowercase(self):
        self.assertEqual(get_extension("sample.MP4"), ".mp4")

    def test_mp4_signature(self):
        header = b"\x00\x00\x00\x18ftypisom0000"
        self.assertTrue(signature_matches(".mp4", header))
        self.assertFalse(signature_matches(".mp4", b"not a video file"))

    def test_webm_signature(self):
        self.assertTrue(signature_matches(".webm", bytes.fromhex("1A45DFA3") + b"rest"))

    def test_avi_signature(self):
        self.assertTrue(signature_matches(".avi", b"RIFF\x20\x00\x00\x00AVI "))


if __name__ == "__main__":
    unittest.main()
