from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.context import context_vault
from diaryvault.index import index_vault
from diaryvault.vault import init_vault, write_json


class ContextTests(unittest.TestCase):
    def test_context_vault_writes_markdown_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = context_vault(root, "工作", limit=5)

            output = Path(report["output_path"])
            self.assertTrue(output.exists())
            text = output.read_text(encoding="utf-8")
            self.assertIn("DiaryVault context pack", text)
            self.assertIn("工作", text)
            self.assertEqual(report["count"], 1)

    def test_context_vault_can_include_trimmed_full_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            report = context_vault(root, "工作", full=True, max_chars=8)

            self.assertTrue(report["results"][0]["text"].endswith("..."))


def _indexed_fixture(tmp: str) -> Path:
    root = init_vault(tmp)
    write_json(
        root / "raw" / "archive.json",
        {
            "meta": {"user_id": 9, "diary_count": 2},
            "diaries": [
                {"id": 1, "user": 9, "createddate": "2026-09-09", "title": "A", "content": "alpha"},
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "B",
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


if __name__ == "__main__":
    unittest.main()
