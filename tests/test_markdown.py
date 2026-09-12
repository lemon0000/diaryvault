from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.markdown import diary_entry_name, extract_image_ids, markdown_for_diary


class MarkdownTests(unittest.TestCase):
    def test_extract_image_ids_sorts_and_deduplicates(self):
        self.assertEqual(extract_image_ids("a[图20]b[图3][图20]"), [3, 20])

    def test_markdown_has_frontmatter_and_image_refs(self):
        text = markdown_for_diary(
            {
                "id": 123,
                "user": 9,
                "createddate": "2026-09-10",
                "title": "Today",
                "content": "hello\n[图42]",
                "weather": "晴",
                "mood": "平静",
            },
            image_exts={42: "png"},
        )
        self.assertIn("id: 123", text)
        self.assertIn("# Today", text)
        self.assertIn("![图42](../../images/42.png)", text)

    def test_entry_name_uses_date_and_id(self):
        self.assertEqual(diary_entry_name({"id": 5, "createddate": "2026-09-10"}), ("2026", "2026-09-10-5.md"))


if __name__ == "__main__":
    unittest.main()

