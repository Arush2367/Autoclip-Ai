import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services import secure_storage


class SecureStorageTests(unittest.TestCase):
    def test_posix_storage_uses_owner_only_permissions(self):
        if os.name == "nt":
            self.skipTest("POSIX permission bits do not apply on Windows")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_auth.json"
            secure_storage.save_secure_json(path, {"token": "test-secret"})
            self.assertEqual(secure_storage.load_secure_json(path), {"token": "test-secret"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_windows_mode_encrypts_and_decrypts_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_auth.json"
            def fake_protect(value, *, protect):
                if protect:
                    return b"cipher:" + base64.b64encode(bytes(byte ^ 0xA5 for byte in value))
                encrypted = base64.b64decode(value.removeprefix(b"cipher:"))
                return bytes(byte ^ 0xA5 for byte in encrypted)
            with patch.object(secure_storage, "IS_WINDOWS", True), \
                 patch.object(secure_storage, "_dpapi_transform", side_effect=fake_protect):
                secure_storage.save_secure_json(path, {"token": "not-plaintext"})
                raw = path.read_bytes()
                self.assertTrue(raw.startswith(secure_storage.DPAPI_PREFIX))
                self.assertNotIn(b"not-plaintext", raw)
                self.assertEqual(secure_storage.load_secure_json(path), {"token": "not-plaintext"})

    def test_legacy_plaintext_migrates_to_dpapi_on_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "youtube_token.json"
            path.write_text(json.dumps({"refresh_token": "legacy-secret"}), encoding="utf-8")
            def fake_protect(value, *, protect):
                if protect:
                    return b"cipher:" + base64.b64encode(bytes(byte ^ 0xA5 for byte in value))
                encrypted = base64.b64decode(value.removeprefix(b"cipher:"))
                return bytes(byte ^ 0xA5 for byte in encrypted)
            with patch.object(secure_storage, "IS_WINDOWS", True), \
                 patch.object(secure_storage, "_dpapi_transform", side_effect=fake_protect):
                loaded = secure_storage.load_secure_json(path)
                self.assertEqual(loaded["refresh_token"], "legacy-secret")
                self.assertTrue(path.read_bytes().startswith(secure_storage.DPAPI_PREFIX))
                self.assertNotIn(b"legacy-secret", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
