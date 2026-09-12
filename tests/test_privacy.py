from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.privacy import PRIVACY_END, PRIVACY_START, decrypt_privacy_markers


class PrivacyTests(unittest.TestCase):
    def test_no_marker_is_passthrough(self):
        result = decrypt_privacy_markers("plain text", 123)
        self.assertEqual(result.content, "plain text")
        self.assertEqual(result.found_count, 0)

    def test_marker_without_crypto_keeps_ciphertext_or_reports_failure(self):
        result = decrypt_privacy_markers(f"a{PRIVACY_START}not-cipher{PRIVACY_END}b", 123)
        self.assertEqual(result.found_count, 1)
        if not result.crypto_available:
            self.assertEqual(result.failed_count, 1)
            self.assertIn("not-cipher", result.content)


if __name__ == "__main__":
    unittest.main()

