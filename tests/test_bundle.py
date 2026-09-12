from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.bundle import bundle_vault
from diaryvault.index import index_vault
from diaryvault.vault import init_vault, write_image, write_json, write_text


class BundleTests(unittest.TestCase):
    def test_bundle_vault_creates_zip_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(tmp)
            write_json(
                root / "raw" / "archive.json",
                {
                    "meta": {"user_id": 9, "diary_count": 1},
                    "diaries": [{"id": 1, "user": 9, "createddate": "2026-09-10", "content": "body"}],
                    "images": [],
                    "image_ids": [10],
                    "content_image_ids": [10],
                    "image_exts": {"10": "jpg"},
                },
            )
            write_text(root / "entries" / "2026" / "2026-09-10-1.md", "# body")
            write_image(root, 10, "jpg", b"img")
            write_text(root / ".secrets" / "nideriji.env", "NIDERIJI_PASSWORD=secret")
            index_vault(root)

            report = bundle_vault(root)

            self.assertTrue(Path(report["output_path"]).exists())
            with ZipFile(report["output_path"]) as zf:
                names = set(zf.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("raw/archive.json", names)
            self.assertIn("entries/2026/2026-09-10-1.md", names)
            self.assertIn("images/10.jpg", names)
            self.assertIn("db/diaryvault.sqlite", names)
            self.assertFalse(any(".secrets" in name for name in names))

    def test_bundle_vault_can_skip_images_and_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(tmp)
            write_json(
                root / "raw" / "archive.json",
                {
                    "meta": {"user_id": 9, "diary_count": 1},
                    "diaries": [{"id": 1, "user": 9, "createddate": "2026-09-10", "content": "body"}],
                },
            )
            write_image(root, 10, "jpg", b"img")
            index_vault(root)

            report = bundle_vault(root, include_images=False, include_db=False)

            with ZipFile(report["output_path"]) as zf:
                names = set(zf.namelist())
            self.assertFalse(any(name.startswith("images/") for name in names))
            self.assertFalse(any(name.startswith("db/") for name in names))


if __name__ == "__main__":
    unittest.main()
