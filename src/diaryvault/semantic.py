from __future__ import annotations

import json
import math
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .vectors import encode_vector, text_hash


DEFAULT_DB_NAME = "diaryvault.sqlite"
DEFAULT_SEMANTIC_PROVIDER = "ollama"
DEFAULT_SEMANTIC_MODEL = "bge-m3"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class SemanticEmbeddingError(NiderijiError):
    pass


def ensure_semantic_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS chunk_semantic_vectors (
          chunk_id INTEGER NOT NULL,
          provider TEXT NOT NULL,
          model TEXT NOT NULL,
          dim INTEGER NOT NULL,
          vector BLOB NOT NULL,
          text_hash TEXT NOT NULL,
          embedded_at TEXT NOT NULL,
          PRIMARY KEY (chunk_id, provider, model),
          FOREIGN KEY (chunk_id) REFERENCES diary_chunks(chunk_id)
        );

        CREATE INDEX IF NOT EXISTS idx_chunk_semantic_vectors_model
          ON chunk_semantic_vectors(provider, model);
        """
    )


def semantic_vector_counts(con: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(con, "chunk_semantic_vectors"):
        return []
    rows = con.execute(
        """
        SELECT provider, model, dim, COUNT(*) AS count
        FROM chunk_semantic_vectors
        GROUP BY provider, model, dim
        ORDER BY provider, model, dim
        """
    ).fetchall()
    return [
        {
            "provider": row[0],
            "model": row[1],
            "dim": int(row[2]),
            "count": int(row[3]),
        }
        for row in rows
    ]


def index_semantic_vectors(
    vault: str | Path,
    *,
    db_path: str | Path | None = None,
    provider: str = DEFAULT_SEMANTIC_PROVIDER,
    model: str = DEFAULT_SEMANTIC_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    batch_size: int = 16,
    limit: int | None = None,
    force: bool = False,
    timeout: int = 120,
) -> dict[str, Any]:
    if provider != "ollama":
        raise NiderijiError("semantic provider must be ollama")
    if not model.strip():
        raise NiderijiError("semantic model is required")
    if batch_size <= 0:
        raise NiderijiError("batch_size must be greater than zero")
    if limit is not None and limit <= 0:
        raise NiderijiError("limit must be greater than zero")

    root = Path(vault).expanduser().resolve()
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON")
        ensure_semantic_schema(con)
        rows = _semantic_candidates(con, provider=provider, model=model, force=force)
        if limit is not None:
            rows = rows[:limit]

        embedded = 0
        dim: int | None = None
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            texts = [row["text"] for row in batch]
            vectors = embed_texts(
                texts,
                provider=provider,
                model=model,
                base_url=base_url,
                timeout=timeout,
            )
            now = datetime.now(timezone.utc).isoformat()
            payload = []
            for row, vector in zip(batch, vectors, strict=True):
                normalized = normalize_vector(vector)
                if not normalized:
                    raise NiderijiError("embedding provider returned an empty vector")
                dim = len(normalized)
                payload.append(
                    (
                        row["chunk_id"],
                        provider,
                        model,
                        dim,
                        encode_vector(normalized),
                        text_hash(row["text"]),
                        now,
                    )
                )
            con.executemany(
                """
                INSERT INTO chunk_semantic_vectors(chunk_id, provider, model, dim, vector, text_hash, embedded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, provider, model) DO UPDATE SET
                  dim = excluded.dim,
                  vector = excluded.vector,
                  text_hash = excluded.text_hash,
                  embedded_at = excluded.embedded_at
                """,
                payload,
            )
            con.commit()
            embedded += len(payload)

        total_chunks = int(con.execute("SELECT COUNT(*) FROM diary_chunks").fetchone()[0])
        semantic_count = _semantic_count(con, provider, model)
    finally:
        con.close()

    return {
        "ok": True,
        "db_path": str(target),
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "total_chunks": total_chunks,
        "pending_before": len(rows),
        "embedded": embedded,
        "semantic_vectors": semantic_count,
        "semantic_dim": dim,
        "force": force,
    }


def embed_texts(
    texts: list[str],
    *,
    provider: str = DEFAULT_SEMANTIC_PROVIDER,
    model: str = DEFAULT_SEMANTIC_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    timeout: int = 120,
) -> list[list[float]]:
    if provider != "ollama":
        raise NiderijiError("semantic provider must be ollama")
    if not texts:
        return []
    return _embed_ollama(texts, model=model, base_url=base_url, timeout=timeout)


def normalize_vector(values: list[float]) -> list[float]:
    parsed = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in parsed))
    if not norm:
        return []
    return [value / norm for value in parsed]


def _semantic_candidates(
    con: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    force: bool,
) -> list[sqlite3.Row]:
    rows = con.execute(
        """
        SELECT c.chunk_id, c.text, v.text_hash
        FROM diary_chunks c
        LEFT JOIN chunk_semantic_vectors v
          ON v.chunk_id = c.chunk_id AND v.provider = ? AND v.model = ?
        ORDER BY c.chunk_id
        """,
        (provider, model),
    ).fetchall()
    if force:
        return rows
    return [row for row in rows if row["text_hash"] != text_hash(row["text"])]


def _semantic_count(con: sqlite3.Connection, provider: str, model: str) -> int:
    return int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM chunk_semantic_vectors
            WHERE provider = ? AND model = ?
            """,
            (provider, model),
        ).fetchone()[0]
    )


def _embed_ollama(
    texts: list[str],
    *,
    model: str,
    base_url: str,
    timeout: int,
) -> list[list[float]]:
    url = base_url.rstrip("/") + "/api/embed"
    request = urllib.request.Request(
        url,
        data=json.dumps({"model": model, "input": texts}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace").strip()
        raise SemanticEmbeddingError(f"Ollama embedding request failed: HTTP {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise SemanticEmbeddingError(f"Ollama is not reachable at {base_url}") from exc

    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list):
        raise SemanticEmbeddingError("Ollama embedding response does not contain embeddings")
    if len(embeddings) != len(texts):
        raise SemanticEmbeddingError("Ollama embedding response count does not match input count")

    out: list[list[float]] = []
    for embedding in embeddings:
        if not isinstance(embedding, list):
            raise SemanticEmbeddingError("Ollama embedding item is not a vector")
        out.append([float(value) for value in embedding])
    return out


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'virtual table')",
            (name,),
        ).fetchone()
    )
