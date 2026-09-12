from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.index import index_vault
from diaryvault.stats import stats_vault
from diaryvault.vault import init_vault, write_json


class StatsTests(unittest.TestCase):
    def test_stats_vault_counts_dates_and_streaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = stats_vault(root)

            self.assertEqual(report["overview"]["diary_count"], 3)
            self.assertEqual(report["overview"]["active_day_count"], 3)
            self.assertEqual(report["overview"]["first_date"], "2026-09-08")
            self.assertEqual(report["overview"]["last_date"], "2026-09-10")
            self.assertEqual(report["overview"]["current_streak_days"], 3)
            self.assertEqual(report["overview"]["longest_streak_days"], 3)
            self.assertEqual(report["by_year"], {"2026": 3})
            self.assertEqual(report["top_moods"][0], ("calm", 2))

    def test_stats_vault_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = stats_vault(root, write_report=True)

            self.assertTrue((root / "reports" / "stats.json").exists())
            self.assertTrue((root / "reports" / "stats.md").exists())
            self.assertEqual(len(report["written_reports"]), 2)


def _indexed_fixture(tmp: str) -> Path:
    root = init_vault(tmp)
    write_json(
        root / "raw" / "archive.json",
        {
            "meta": {"user_id": 9, "diary_count": 3},
            "diaries": [
                {"id": 1, "user": 9, "createddate": "2026-09-08", "content": "aaa", "mood": "calm"},
                {"id": 2, "user": 9, "createddate": "2026-09-09", "content": "bbbb", "mood": "calm"},
                {"id": 3, "user": 9, "createddate": "2026-09-10", "content": "ccccc", "mood": "busy"},
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
