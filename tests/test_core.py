from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.client import NiderijiError
from diaryvault.core import get_diary, get_index_health, get_recent_diaries, recall_memories, search_diaries
from diaryvault.index import index_vault
from diaryvault.vault import init_vault, write_json


class CoreTests(unittest.TestCase):
    def test_index_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            health = get_index_health(root)
            self.assertEqual(health["diaries"], 3)
            self.assertEqual(health["chunks"], 3)
            self.assertEqual(health["vectors"], 3)
            self.assertEqual(health["unembedded_chunks"], 0)
            self.assertEqual(health["vector_dim"], 512)

    def test_search_and_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            search = search_diaries("work", vault=root, top_k=5)
            self.assertEqual(search["count"], 1)
            self.assertEqual(search["results"][0]["diary_id"], 2)
            self.assertIn("score", search["results"][0])

            recall = recall_memories("work pressure", vault=root, top_k=5)
            self.assertGreaterEqual(recall["count"], 1)
            self.assertEqual(recall["results"][0]["diary_id"], 2)

    def test_recall_memories_groups_compact_results_by_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_group_fixture(tmp)

            recall = recall_memories("work pressure", vault=root, top_k=5, group_by="year")

            self.assertEqual(recall["group_by"], "year")
            self.assertEqual([group["key"] for group in recall["groups"]], ["2025", "2026"])
            self.assertIn("excerpt", recall["groups"][0]["results"][0])
            self.assertNotIn("text", recall["groups"][0]["results"][0])

    def test_get_diary_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            diary = get_diary(2, vault=root, max_chars=10)
            self.assertEqual(diary["diary_id"], 2)
            self.assertTrue(diary["truncated"])
            self.assertLessEqual(len(diary["content"]), 10)

            with self.assertRaises(NiderijiError):
                get_diary(2, vault=root, max_chars=10001)

    def test_get_recent_diaries_anchors_to_latest_archive_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            recent = get_recent_diaries(vault=root, days=2)
            self.assertEqual(recent["start_date"], "2026-09-09")
            self.assertEqual(recent["end_date"], "2026-09-10")
            self.assertEqual([item["diary_id"] for item in recent["results"]], [3, 2])


def _indexed_fixture(tmp: str) -> Path:
    root = init_vault(tmp)
    write_json(
        root / "raw" / "archive.json",
        {
            "meta": {"user_id": 9, "diary_count": 3},
            "diaries": [
                {
                    "id": 1,
                    "user": 9,
                    "createddate": "2026-09-08",
                    "title": "walk",
                    "content": "sunny walk outside",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-09",
                    "title": "work",
                    "content": "today I recorded work pressure and uncertainty about direction",
                },
                {
                    "id": 3,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "reading",
                    "content": "quiet reading at night",
                },
            ],
            "images": [],
            "image_ids": [],
            "content_image_ids": [],
            "image_exts": {},
        },
    )
    index_vault(root)
    return root


def _indexed_group_fixture(tmp: str) -> Path:
    root = init_vault(tmp)
    write_json(
        root / "raw" / "archive.json",
        {
            "meta": {"user_id": 9, "diary_count": 2},
            "diaries": [
                {
                    "id": 11,
                    "user": 9,
                    "createddate": "2025-03-01",
                    "title": "work",
                    "content": "old work pressure about career direction",
                },
                {
                    "id": 12,
                    "user": 9,
                    "createddate": "2026-04-01",
                    "title": "work",
                    "content": "new work pressure about future direction",
                },
            ],
            "images": [],
            "image_ids": [],
            "content_image_ids": [],
            "image_exts": {},
        },
    )
    index_vault(root)
    return root


if __name__ == "__main__":
    unittest.main()
