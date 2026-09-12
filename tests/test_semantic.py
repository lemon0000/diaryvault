from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.client import NiderijiError
from diaryvault.core import get_index_health
from diaryvault.index import index_vault
from diaryvault.recall import recall_vault
from diaryvault.semantic import SemanticEmbeddingError, index_semantic_vectors
from diaryvault.vault import init_vault, write_json


class SemanticTests(unittest.TestCase):
    def test_semantic_index_writes_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            with patch("diaryvault.semantic.embed_texts", side_effect=_fake_embeddings):
                report = index_semantic_vectors(root, model="test-model", batch_size=2)

            self.assertEqual(report["pending_before"], 2)
            self.assertEqual(report["embedded"], 2)
            self.assertEqual(report["semantic_vectors"], 2)
            self.assertEqual(report["semantic_dim"], 3)

            health = get_index_health(root)
            self.assertEqual(health["semantic_vectors"], 2)
            self.assertEqual(health["semantic_models"][0]["model"], "test-model")

    def test_index_rebuild_preserves_current_semantic_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with patch("diaryvault.semantic.embed_texts", side_effect=_fake_embeddings):
                index_semantic_vectors(root, model="test-model")

            report = index_vault(root)

            self.assertEqual(report["semantic_vectors_restored"], 2)
            self.assertEqual(get_index_health(root)["semantic_vectors"], 2)

    def test_recall_uses_hybrid_when_semantic_vectors_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with patch("diaryvault.semantic.embed_texts", side_effect=_fake_embeddings):
                index_semantic_vectors(root, model="test-model")

            with patch("diaryvault.recall.embed_texts", side_effect=_fake_embeddings):
                report = recall_vault(
                    root,
                    "future path confusion",
                    limit=2,
                    semantic_model="test-model",
                    semantic_min_score=0.5,
                )

            self.assertEqual(report["method"], "hybrid-vector")
            self.assertTrue(report["semantic"]["used"])
            self.assertEqual(report["results"][0]["diary_id"], 2)
            self.assertIn("semantic_score", report["results"][0])

    def test_recall_falls_back_when_semantic_provider_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with patch("diaryvault.semantic.embed_texts", side_effect=_fake_embeddings):
                index_semantic_vectors(root, model="test-model")

            with patch("diaryvault.recall.embed_texts", side_effect=SemanticEmbeddingError("offline")):
                report = recall_vault(root, "work pressure", semantic_model="test-model")

            self.assertEqual(report["method"], "local-vector")
            self.assertEqual(report["semantic"]["error"], "offline")
            self.assertGreaterEqual(report["count"], 1)
            self.assertEqual(report["results"][0]["diary_id"], 2)

    def test_recall_required_semantic_raises_when_vectors_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)

            with self.assertRaises(NiderijiError):
                recall_vault(root, "future path confusion", semantic="required", semantic_model="missing")


def _fake_embeddings(texts, **kwargs):
    out = []
    for text in texts:
        lowered = text.casefold()
        if any(word in lowered for word in ("future", "path", "confusion", "graduate", "product", "job", "career", "work", "pressure")):
            out.append([1.0, 0.0, 0.0])
        elif any(word in lowered for word in ("cooking", "dinner")):
            out.append([0.0, 1.0, 0.0])
        else:
            out.append([0.0, 0.0, 1.0])
    return out


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
                    "title": "cooking",
                    "content": "made dinner at home",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "work",
                    "content": "job stress and graduate school uncertainty",
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
