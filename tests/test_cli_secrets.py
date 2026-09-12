from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.cli import load_secrets_file, make_client
from diaryvault.client import NiderijiError


class CliSecretsTests(unittest.TestCase):
    def test_load_secrets_file_sets_supported_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nideriji.env"
            path.write_text("NIDERIJI_EMAIL=user@example.com\nNIDERIJI_PASSWORD=secret\n", encoding="utf-8")
            old_email = os.environ.pop("NIDERIJI_EMAIL", None)
            old_password = os.environ.pop("NIDERIJI_PASSWORD", None)
            try:
                loaded = load_secrets_file(path)
                self.assertEqual(os.environ["NIDERIJI_EMAIL"], "user@example.com")
                self.assertEqual(os.environ["NIDERIJI_PASSWORD"], "secret")
                self.assertEqual(loaded, {"NIDERIJI_EMAIL", "NIDERIJI_PASSWORD"})
            finally:
                os.environ.pop("NIDERIJI_EMAIL", None)
                os.environ.pop("NIDERIJI_PASSWORD", None)
                if old_email is not None:
                    os.environ["NIDERIJI_EMAIL"] = old_email
                if old_password is not None:
                    os.environ["NIDERIJI_PASSWORD"] = old_password

    def test_make_client_fails_fast_for_empty_secrets_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.env"
            path.write_text("", encoding="utf-8")
            old_email = os.environ.pop("NIDERIJI_EMAIL", None)
            old_password = os.environ.pop("NIDERIJI_PASSWORD", None)
            old_token = os.environ.pop("NIDERIJI_TOKEN", None)
            try:
                class Args:
                    secrets_file = str(path)
                    user_id = None
                    timeout = 30
                    email = None

                with self.assertRaises(NiderijiError):
                    make_client(Args())
            finally:
                if old_email is not None:
                    os.environ["NIDERIJI_EMAIL"] = old_email
                if old_password is not None:
                    os.environ["NIDERIJI_PASSWORD"] = old_password
                if old_token is not None:
                    os.environ["NIDERIJI_TOKEN"] = old_token


if __name__ == "__main__":
    unittest.main()
