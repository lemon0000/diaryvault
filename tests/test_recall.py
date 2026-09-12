from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.index import index_vault
from diaryvault.recall import recall_vault
from diaryvault.client import NiderijiError
from diaryvault.vault import init_vault, write_json


class RecallTests(unittest.TestCase):
    def test_recall_returns_best_matching_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = recall_vault(root, "工作压力", limit=2)

            self.assertGreaterEqual(report["count"], 1)
            self.assertEqual(report["results"][0]["diary_id"], 2)
            self.assertGreater(report["results"][0]["score"], 0)

    def test_recall_applies_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = recall_vault(root, "工作压力", date_to="2026-09-09")

            self.assertEqual(report["count"], 0)

    def test_recall_filters_unrelated_ascii_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = recall_vault(root, "__diaryvault_no_match__", limit=2)

            self.assertEqual(report["count"], 0)

    def test_recall_groups_results_by_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_group_fixture(tmp)

            report = recall_vault(root, "work pressure", limit=5, group_by="year")

            self.assertEqual(report["group_by"], "year")
            self.assertEqual([group["key"] for group in report["groups"]], ["2025", "2026"])
            self.assertEqual(sum(group["count"] for group in report["groups"]), report["count"])
            self.assertEqual(report["groups"][0]["date_from"], "2025-03-01")

    def test_recall_rejects_unknown_grouping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            with self.assertRaises(NiderijiError):
                recall_vault(root, "工作压力", group_by="month")


def _indexed_fixture(tmp: str) -> Path:
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
                    "title": "散步",
                    "content": "天气晴朗，出去散步。",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "工作",
                    "content": "今天记录工作压力和后续计划。",
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
            "meta": {"user_id": 9, "diary_count": 3},
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
                {
                    "id": 13,
                    "user": 9,
                    "createddate": "2026-05-01",
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


if __name__ == "__main__":
    unittest.main()
