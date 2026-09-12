from pathlib import Path
import json
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.import_zip import import_archive_zip, parse_image_member


class ImportZipTests(unittest.TestCase):
    def test_parse_image_member(self):
        self.assertEqual(parse_image_member("Images/42.jpg"), (42, "jpg"))
        self.assertEqual(parse_image_member("Images/nope.jpg"), (None, ""))
        self.assertEqual(parse_image_member("Other/42.jpg"), (None, ""))

    def test_import_archive_zip_writes_archive_entries_and_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "archive.zip"
            archive = {
                "meta": {"diary_count": 1, "first_date": "2026-09-10", "last_date": "2026-09-10"},
                "diaries": [
                    {
                        "id": 7,
                        "user": 1,
                        "createddate": "2026-09-10",
                        "title": "Sample",
                        "content": "hello [图42]",
                    }
                ],
                "image_ids": [42],
                "content_image_ids": [42],
                "validation": {"status": "ok"},
            }
            with ZipFile(source, "w") as zf:
                zf.writestr("archive.json", json.dumps(archive))
                zf.writestr("Images/42.jpg", b"image-bytes")

            report = import_archive_zip(source, root / "vault")

            self.assertEqual(report["diary_count"], 1)
            self.assertTrue((root / "vault" / "raw" / "archive.json").exists())
            self.assertTrue((root / "vault" / "entries" / "2026" / "2026-09-10-7.md").exists())
            self.assertEqual((root / "vault" / "images" / "42.jpg").read_bytes(), b"image-bytes")


if __name__ == "__main__":
    unittest.main()

