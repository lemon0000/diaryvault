from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.cli import main
from diaryvault.index import index_vault
from diaryvault.search import search_vault
from diaryvault.vault import init_vault, write_json


class SearchTests(unittest.TestCase):
    def test_search_finds_short_chinese_query_with_like(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = search_vault(root, "工作")

            self.assertEqual(report["method"], "like")
            self.assertEqual(report["count"], 1)
            self.assertEqual(report["results"][0]["diary_id"], 2)

    def test_search_applies_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = search_vault(root, "", date_from="2026-09-10", date_to="2026-09-10")

            self.assertEqual(report["count"], 1)
            self.assertEqual(report["results"][0]["createddate"], "2026-09-10")

    def test_search_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            with patch("sys.stdout") as stdout:
                code = main(["search", "Alpha", "--vault", str(root), "--json"])

            self.assertEqual(code, 0)
            output = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
            report = json.loads(output)
            self.assertEqual(report["count"], 1)
            self.assertEqual(report["results"][0]["diary_id"], 1)


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
                    "createdtime": 100,
                    "title": "Alpha day",
                    "content": "alpha body",
                    "weather": "sunny",
                    "mood": "calm",
                    "space": "home",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "createdtime": 200,
                    "title": "中文日记",
                    "content": "今天记录工作压力。",
                    "weather": "cloudy",
                    "mood": "tired",
                    "space": "office",
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
