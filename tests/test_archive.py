from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.archive import build_image_plan, choose_diaries, choose_recent_diaries, merge_diaries, select_raw


class ArchiveTests(unittest.TestCase):
    def test_select_raw_modes(self):
        raw = {
            "diaries": [{"id": 1}],
            "diaries_paired": [{"id": 2}],
            "images": [{"image_id": 10}],
            "images_paired": [{"image_id": 20}],
        }
        self.assertEqual([d["id"] for d in select_raw(raw, "mine")[0]], [1])
        self.assertEqual([d["id"] for d in select_raw(raw, "partner")[0]], [2])
        self.assertEqual([d["id"] for d in select_raw(raw, "all")[0]], [1, 2])

    def test_choose_diaries_samples_newest_then_returns_oldest_order(self):
        diaries = [
            {"id": 1, "createddate": "2026-01-01"},
            {"id": 2, "createddate": "2026-03-01"},
            {"id": 3, "createddate": "2026-02-01"},
        ]
        self.assertEqual([d["id"] for d in choose_diaries(diaries, limit=2, order="newest")], [3, 2])

    def test_build_image_plan_classifies_refs(self):
        plan = build_image_plan(
            [{"id": 1, "user": 9, "content": "[图1]\n[图2]"}],
            [{"image_id": 1, "user": 9}, {"image_id": 3, "user": 9}],
            9,
        )
        self.assertEqual(plan["image_ids"], [1])
        self.assertEqual(plan["referenced_not_indexed"], [2])
        self.assertEqual(plan["indexed_not_referenced"], [3])
        self.assertEqual(plan["owner_by_id"][1], 9)

    def test_choose_recent_diaries_uses_inclusive_day_window(self):
        diaries = [
            {"id": 1, "createddate": "2026-09-07"},
            {"id": 2, "createddate": "2026-09-08"},
            {"id": 3, "createddate": "2026-09-10"},
            {"id": 4, "createddate": "not-a-date"},
        ]

        chosen = choose_recent_diaries(diaries, days=3, today=date(2026, 9, 10))

        self.assertEqual([d["id"] for d in chosen], [2, 3])

    def test_merge_diaries_replaces_matching_user_and_id(self):
        existing = [
            {"id": 1, "user": 9, "content": "old"},
            {"id": 2, "user": 9, "content": "keep"},
        ]
        updates = [{"id": 1, "user": 9, "content": "new"}]

        merged = merge_diaries(existing, updates)

        self.assertEqual([d["id"] for d in merged], [1, 2])
        self.assertEqual(merged[0]["content"], "new")


if __name__ == "__main__":
    unittest.main()
