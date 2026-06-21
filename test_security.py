import json
import tempfile
import unittest
from pathlib import Path

from eic.secure_store import EncryptedStoreError, Fernet, get_or_create_key, read_encrypted_json, write_encrypted_json


class SecureStoreTests(unittest.TestCase):
    def test_profile_is_encrypted_and_authenticated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.enc"
            key = Fernet.generate_key()
            payload = {"filing_status": "single", "earned_income": 28000}
            write_encrypted_json(path, payload, key)
            raw = path.read_bytes()
            self.assertNotIn(b"filing_status", raw)
            self.assertNotIn(b"28000", raw)
            self.assertEqual(read_encrypted_json(path, key), payload)

    def test_wrong_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.enc"
            write_encrypted_json(path, {"agi": 12000}, Fernet.generate_key())
            with self.assertRaises(EncryptedStoreError):
                read_encrypted_json(path, Fernet.generate_key())

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.enc"
            key = Fernet.generate_key()
            write_encrypted_json(path, {"agi": 12000}, key)
            raw = bytearray(path.read_bytes())
            raw[-5] ^= 1
            path.write_bytes(raw)
            with self.assertRaises(EncryptedStoreError):
                read_encrypted_json(path, key)

    def test_local_key_is_reusable_and_not_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            first = get_or_create_key(directory, env_name="UNSET_TEST_PROFILE_KEY")
            second = get_or_create_key(directory, env_name="UNSET_TEST_PROFILE_KEY")
            self.assertEqual(first, second)
            stored = (Path(directory) / "profile.key").read_bytes()
            if __import__("os").name == "nt":
                self.assertTrue(stored.startswith(b"dpapi:"))
                self.assertNotIn(first, stored)


if __name__ == "__main__":
    unittest.main()
