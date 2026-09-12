from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.validate import validate_vault
from diaryvault.vault import init_vault, write_entries, write_image, write_json


class ValidateTests(unittest.TestCase):
    def test_validate_complete_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(Path(tmp) / "vault")
            diary = {
                "id": 1,
                "user": 9,
                "createddate": "2026-09-10",
                "title": "Ok",
                "content": "[图5]",
            }
            archive = {
                "meta": {"diary_count": 1, "first_date": "2026-09-10", "last_date": "2026-09-10"},
                "diaries": [diary],
                "image_ids": [5],
                "content_image_ids": [5],
                "image_exts": {"5": "jpg"},
                "validation": {"status": "ok"},
            }
            write_json(root / "raw" / "archive.json", archive)
            write_entries(root, [diary], image_exts={5: "jpg"})
            write_image(root, 5, "jpg", b"bytes")

            report = validate_vault(root)

            self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False))

    def test_validate_missing_image_fails_when_images_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(Path(tmp) / "vault")
            diary = {"id": 1, "createddate": "2026-09-10", "content": "[图5]"}
            write_json(
                root / "raw" / "archive.json",
                {
                    "meta": {"diary_count": 1},
                    "diaries": [diary],
                    "image_ids": [5],
                    "content_image_ids": [5],
                    "validation": {"status": "ok"},
                },
            )
            write_entries(root, [diary])

            report = validate_vault(root)

            self.assertFalse(report["ok"])
            self.assertIn("missing image files", report["errors"][0])

    def test_validate_warns_when_content_refs_are_not_in_archive_image_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(Path(tmp) / "vault")
            diary = {"id": 1, "createddate": "2026-09-10", "content": "[图5] [图6]"}
            write_json(
                root / "raw" / "archive.json",
                {
                    "meta": {"diary_count": 1},
                    "diaries": [diary],
                    "image_ids": [5],
                    "content_image_ids": [5, 6],
                    "image_exts": {"5": "jpg"},
                    "validation": {"status": "ok"},
                },
            )
            write_entries(root, [diary], image_exts={5: "jpg"})
            write_image(root, 5, "jpg", b"bytes")

            report = validate_vault(root)

            self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False))
            self.assertEqual(report["stats"]["referenced_not_archived_image_count"], 1)
            self.assertIn("content references images", report["warnings"][0])


if __name__ == "__main__":
    unittest.main()
