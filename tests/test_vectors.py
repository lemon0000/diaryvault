from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.vectors import chunk_diary_text, cosine, decode_vector, encode_vector, text_vector


class VectorTests(unittest.TestCase):
    def test_vector_round_trip(self):
        vector = text_vector("工作压力")

        decoded = decode_vector(encode_vector(vector))

        self.assertEqual(len(decoded), len(vector))
        self.assertAlmostEqual(cosine(vector, decoded), 1.0, places=5)

    def test_related_text_scores_higher_than_unrelated_text(self):
        query = text_vector("工作压力")
        related = text_vector("今天记录工作压力和后续计划")
        unrelated = text_vector("天气晴朗出去散步")

        self.assertGreater(cosine(query, related), cosine(query, unrelated))

    def test_chunk_diary_text_splits_long_text(self):
        chunks = chunk_diary_text("title", "x" * 1500, max_chars=700, overlap=80)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0].startswith("title"))


if __name__ == "__main__":
    unittest.main()
