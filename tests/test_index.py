from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.index import index_vault
from diaryvault.vault import init_vault, write_image, write_json


class IndexTests(unittest.TestCase):
    def test_index_vault_builds_sqlite_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = init_vault(tmp)
            write_json(
                root / "raw" / "archive.json",
                {
                    "meta": {"user_id": 9, "diary_count": 2},
                    "diaries": [
                        {
                            "id": 1,
                            "user": 9,
                            "createddate": "2026-09-09",
                            "createdtime": 100,
                            "title": "Alpha day",
                            "content": "alpha body",
                            "weather": "sunny",
                            "mood": "calm",
                            "space": "home",
                            "image_ids": [10],
                        },
                        {
                            "id": 2,
                            "user": 9,
                            "createddate": "2026-09-10",
                            "createdtime": 200,
                            "title": "Beta day",
                            "content": "beta body",
                            "image_ids": [11],
                        },
                    ],
                    "images": [{"image_id": 10}],
                    "image_ids": [10],
                    "content_image_ids": [10, 11],
                    "image_exts": {"10": "jpg"},
                },
            )
            write_image(root, 10, "jpg", b"img")

            report = index_vault(root)

            self.assertTrue(Path(report["db_path"]).exists())
            self.assertEqual(report["diary_count"], 2)
            self.assertEqual(report["diary_image_count"], 2)
            self.assertEqual(report["chunk_count"], 2)
            self.assertEqual(report["image_row_count"], 2)
            self.assertEqual(report["image_file_count"], 1)

            con = sqlite3.connect(report["db_path"])
            try:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM diaries").fetchone()[0], 2)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM diary_images").fetchone()[0], 2)
                self.assertEqual(
                    con.execute("SELECT has_file FROM images WHERE image_id = 10").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    con.execute("SELECT has_file FROM images WHERE image_id = 11").fetchone()[0],
                    0,
                )
                if report["fts_enabled"]:
                    rows = con.execute(
                        "SELECT diary_id FROM diary_fts WHERE diary_fts MATCH ? ORDER BY diary_id",
                        ("alpha",),
                    ).fetchall()
                    self.assertEqual(rows, [(1,)])
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
