from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .context import build_context_pack
from .index import DEFAULT_DB_NAME
from .markdown import diary_entry_name, normalize_content
from .recall import recall_vault
from .search import search_vault
from .semantic import semantic_vector_counts
from .stats import stats_vault


DEFAULT_DIARY_MAX_CHARS = 5000
MAX_DIARY_CHARS = 10000


def resolve_vault(vault: str | Path = "DiaryVault") -> Path:
    return Path(vault).expanduser().resolve()


def resolve_db_path(vault: str | Path = "DiaryVault", db_path: str | Path | None = None) -> Path:
    root = resolve_vault(vault)
    return Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME


def get_stats(vault: str | Path = "DiaryVault", *, db_path: str | Path | None = None) -> dict[str, Any]:
    root = resolve_vault(vault)
    target = resolve_db_path(root, db_path)
    stats = stats_vault(root, db_path=target)
    health = get_index_health(root, db_path=target)
    return {
        "ok": True,
        "diaries": health["diaries"],
        "chunks": health["chunks"],
        "vectors": health["vectors"],
        "unembedded_chunks": health["unembedded_chunks"],
        "vector_dim": health["vector_dim"],
        "semantic_vectors": health["semantic_vectors"],
        "semantic_models": health["semantic_models"],
        "stats": stats,
    }


def search_diaries(
    query: str,
    *,
    vault: str | Path = "DiaryVault",
    start_date: str | None = None,
    end_date: str | None = None,
    top_k: int = 10,
    order: str = "newest",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _validate_top_k(top_k)
    report = search_vault(
        resolve_vault(vault),
        query,
        date_from=start_date,
        date_to=end_date,
        limit=top_k,
        order=order,
        db_path=resolve_db_path(vault, db_path),
    )
    return {**report, "results": [_compact_search_result(item) for item in report["results"]]}


def recall_memories(
    query: str,
    *,
    vault: str | Path = "DiaryVault",
    start_date: str | None = None,
    end_date: str | None = None,
    top_k: int = 10,
    group_by: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _validate_top_k(top_k)
    report = recall_vault(
        resolve_vault(vault),
        query,
        date_from=start_date,
        date_to=end_date,
        limit=top_k,
        group_by=group_by,
        db_path=resolve_db_path(vault, db_path),
    )
    out = {**report, "results": [_compact_recall_result(item) for item in report["results"]]}
    if "groups" in report:
        out["groups"] = [_compact_recall_group(item) for item in report["groups"]]
    return out


def build_memory_context(
    query: str,
    *,
    vault: str | Path = "DiaryVault",
    start_date: str | None = None,
    end_date: str | None = None,
    top_k: int = 10,
    full: bool = False,
    max_chars: int = 1200,
    method: str = "recall",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    _validate_top_k(top_k)
    return build_context_pack(
        resolve_vault(vault),
        query,
        date_from=start_date,
        date_to=end_date,
        limit=top_k,
        full=full,
        max_chars=max_chars,
        method=method,
        db_path=resolve_db_path(vault, db_path),
    )


def get_diary(
    diary_id: int,
    *,
    vault: str | Path = "DiaryVault",
    max_chars: int = DEFAULT_DIARY_MAX_CHARS,
    user_id: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    diary_id = _positive_int("diary_id", diary_id)
    max_chars = _bounded_max_chars(max_chars)
    root = resolve_vault(vault)
    target = resolve_db_path(root, db_path)
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        if user_id:
            row = con.execute(
                """
                SELECT user_id, diary_id, createddate, createdtime, title, content, weather, mood, space, image_ids_json
                FROM diaries
                WHERE user_id = ? AND diary_id = ?
                """,
                (user_id, diary_id),
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT user_id, diary_id, createddate, createdtime, title, content, weather, mood, space, image_ids_json
                FROM diaries
                WHERE diary_id = ?
                """,
                (diary_id,),
            ).fetchone()
    finally:
        con.close()
    if not row:
        raise NiderijiError(f"diary not found: {diary_id}")
    return _diary_row(root, row, max_chars=max_chars)


def get_recent_diaries(
    *,
    vault: str | Path = "DiaryVault",
    days: int = 7,
    max_chars: int = 1000,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    days = _positive_int("days", days)
    max_chars = _bounded_max_chars(max_chars)
    root = resolve_vault(vault)
    target = resolve_db_path(root, db_path)
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        latest = con.execute("SELECT MAX(createddate) FROM diaries").fetchone()[0]
        if not latest:
            return {"ok": True, "days": days, "count": 0, "results": []}
        start = (datetime.strptime(latest, "%Y-%m-%d").date() - timedelta(days=days - 1)).isoformat()
        rows = con.execute(
            """
            SELECT user_id, diary_id, createddate, createdtime, title, content, weather, mood, space, image_ids_json
            FROM diaries
            WHERE createddate >= ? AND createddate <= ?
            ORDER BY createddate DESC, createdtime DESC, diary_id DESC
            """,
            (start, latest),
        ).fetchall()
    finally:
        con.close()
    return {
        "ok": True,
        "days": days,
        "start_date": start,
        "end_date": latest,
        "count": len(rows),
        "results": [_diary_row(root, row, max_chars=max_chars) for row in rows],
    }


def get_index_health(vault: str | Path = "DiaryVault", *, db_path: str | Path | None = None) -> dict[str, Any]:
    root = resolve_vault(vault)
    target = resolve_db_path(root, db_path)
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    con = sqlite3.connect(target)
    try:
        diaries = _count(con, "diaries")
        chunks = _count(con, "diary_chunks")
        vectors = _count(con, "chunk_vectors")
        semantic_models = semantic_vector_counts(con)
        semantic_vectors = sum(item["count"] for item in semantic_models)
        row = con.execute(
            """
            SELECT COUNT(*)
            FROM diary_chunks c
            LEFT JOIN chunk_vectors v ON v.chunk_id = c.chunk_id
            WHERE v.chunk_id IS NULL
            """
        ).fetchone()
        dim_row = con.execute("SELECT dim, COUNT(*) FROM chunk_vectors GROUP BY dim ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
    finally:
        con.close()
    return {
        "ok": True,
        "db_path": str(target),
        "diaries": diaries,
        "chunks": chunks,
        "vectors": vectors,
        "unembedded_chunks": int(row[0]),
        "vector_dim": int(dim_row[0]) if dim_row else None,
        "semantic_vectors": semantic_vectors,
        "semantic_models": semantic_models,
    }


def _diary_row(root: Path, row: sqlite3.Row, *, max_chars: int) -> dict[str, Any]:
    content = normalize_content(row["content"]).strip()
    text = _trim(content, max_chars)
    year, filename = diary_entry_name({"id": row["diary_id"], "createddate": row["createddate"]})
    return {
        "ok": True,
        "user_id": row["user_id"],
        "diary_id": row["diary_id"],
        "date": row["createddate"],
        "createddate": row["createddate"],
        "createdtime": row["createdtime"],
        "title": row["title"],
        "content": text,
        "truncated": len(content) > len(text),
        "original_chars": len(content),
        "weather": row["weather"],
        "mood": row["mood"],
        "space": row["space"],
        "image_ids": _json_list(row["image_ids_json"]),
        "entry_path": str(root / "entries" / year / filename),
    }


def _compact_search_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": item["user_id"],
        "diary_id": item["diary_id"],
        "date": item["createddate"],
        "title": item["title"],
        "excerpt": item["excerpt"],
        "score": None,
        "weather": item["weather"],
        "mood": item["mood"],
        "space": item["space"],
        "entry_path": item["entry_path"],
    }


def _compact_recall_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": item["user_id"],
        "diary_id": item["diary_id"],
        "chunk_id": item["chunk_id"],
        "chunk_index": item["chunk_index"],
        "date": item["createddate"],
        "title": item["title"],
        "excerpt": item["text"],
        "score": item["score"],
        "entry_path": item["entry_path"],
    }


def _compact_recall_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": group["key"],
        "label": group["label"],
        "count": group["count"],
        "date_from": group["date_from"],
        "date_to": group["date_to"],
        "top_score": group["top_score"],
        "results": [_compact_recall_result(item) for item in group["results"]],
    }


def _count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _json_list(value: str) -> list[int]:
    import json

    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out = []
    for item in parsed:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _trim(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _validate_top_k(value: int) -> None:
    if value <= 0:
        raise NiderijiError("top_k must be greater than zero")
    if value > 50:
        raise NiderijiError("top_k must be less than or equal to 50")


def _bounded_max_chars(value: int) -> int:
    if value <= 0:
        raise NiderijiError("max_chars must be greater than zero")
    if value > MAX_DIARY_CHARS:
        raise NiderijiError(f"max_chars must be less than or equal to {MAX_DIARY_CHARS}")
    return value


def _positive_int(name: str, value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise NiderijiError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise NiderijiError(f"{name} must be greater than zero")
    return parsed
