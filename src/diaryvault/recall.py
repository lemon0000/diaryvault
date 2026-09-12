from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .index import DEFAULT_DB_NAME
from .markdown import diary_entry_name, normalize_content
from .semantic import DEFAULT_OLLAMA_BASE_URL, DEFAULT_SEMANTIC_MODEL, DEFAULT_SEMANTIC_PROVIDER, embed_texts, normalize_vector
from .vectors import cosine, decode_vector, text_features, text_hash, text_vector


def recall_vault(
    vault: str | Path,
    query: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 12,
    db_path: str | Path | None = None,
    semantic: str = "auto",
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
    semantic_base_url: str | None = None,
    semantic_min_score: float | None = None,
    group_by: str | None = None,
) -> dict[str, Any]:
    if not query.strip():
        raise NiderijiError("recall query is required")
    if limit <= 0:
        raise NiderijiError("limit must be greater than zero")
    if semantic not in {"auto", "off", "required"}:
        raise NiderijiError("semantic must be auto, off or required")
    group_by = _normalize_group_by(group_by)
    _validate_date("from", date_from)
    _validate_date("to", date_to)

    root = Path(vault).expanduser().resolve()
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    query_text = query.strip()
    query_vector = text_vector(query_text)
    provider = semantic_provider or os.environ.get("DIARYVAULT_SEMANTIC_PROVIDER") or DEFAULT_SEMANTIC_PROVIDER
    model = semantic_model or os.environ.get("DIARYVAULT_SEMANTIC_MODEL") or DEFAULT_SEMANTIC_MODEL
    base_url = semantic_base_url or os.environ.get("DIARYVAULT_OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL
    min_semantic = semantic_min_score if semantic_min_score is not None else _env_float("DIARYVAULT_SEMANTIC_MIN_SCORE", 0.2)

    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        _ensure_vector_tables(con)
        has_semantic_table = _has_semantic_table(con)
        semantic_vector_count = _semantic_vector_count(con, provider, model) if has_semantic_table else 0
        rows = _candidate_rows(
            con,
            date_from,
            date_to,
            semantic_provider=provider if has_semantic_table else None,
            semantic_model=model if has_semantic_table else None,
        )
    finally:
        con.close()

    semantic_error: str | None = None
    query_semantic_vector: list[float] | None = None
    if semantic != "off" and semantic_vector_count:
        try:
            query_semantic_vector = normalize_vector(
                embed_texts([query_text], provider=provider, model=model, base_url=base_url)[0]
            )
        except NiderijiError as exc:
            if semantic == "required":
                raise
            semantic_error = str(exc)
    elif semantic == "required":
        raise NiderijiError(f"semantic vectors not found for {provider}/{model}; run diaryvault semantic-index first")

    lexical_scored: list[tuple[float, sqlite3.Row]] = []
    semantic_scored: list[tuple[float, sqlite3.Row]] = []
    query_features = set(text_features(query_text))
    for row in rows:
        row_text = normalize_content(row["text"])
        title = str(row["title"] or "")
        exact_text = query_text.casefold() in row_text.casefold()
        exact_title = query_text.casefold() in title.casefold()
        shared_features = query_features & set(text_features(f"{title}\n{row_text}"))
        haystack = f"{title}\n{row_text}".casefold()
        if _passes_feature_filter(query_text, query_features, shared_features, exact_text, exact_title, haystack):
            score = cosine(query_vector, decode_vector(row["lexical_vector"]))
            score += min(len(shared_features), 30) * 0.004
            if exact_text:
                score += 0.15
            if exact_title:
                score += 0.05
            if score > 0:
                lexical_scored.append((score, row))

        if query_semantic_vector is not None and _has_current_semantic_vector(row):
            score = cosine(query_semantic_vector, decode_vector(row["semantic_vector"]))
            if score >= min_semantic:
                semantic_scored.append((score, row))

    if semantic_scored:
        results = _fused_results(root, lexical_scored, semantic_scored, limit, query_text)
        method = "hybrid-vector"
    else:
        lexical_scored.sort(key=_score_sort_key, reverse=True)
        results = [_format_result(root, row, score, query_text) for score, row in lexical_scored[:limit]]
        method = "local-vector"

    report: dict[str, Any] = {
        "ok": True,
        "db_path": str(target),
        "query": query_text,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "method": method,
        "count": len(results),
        "semantic": {
            "mode": semantic,
            "provider": provider,
            "model": model,
            "available_vectors": semantic_vector_count,
            "used": bool(semantic_scored),
            "min_score": min_semantic,
            "error": semantic_error,
        },
        "results": results,
    }
    if group_by:
        report["group_by"] = group_by
        report["groups"] = _group_results(results, group_by)
    return report


def _candidate_rows(
    con: sqlite3.Connection,
    date_from: str | None,
    date_to: str | None,
    *,
    semantic_provider: str | None = None,
    semantic_model: str | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if date_from:
        clauses.append("c.createddate >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("c.createddate <= ?")
        params.append(date_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    if semantic_provider and semantic_model:
        return con.execute(
            f"""
            SELECT c.chunk_id, c.user_id, c.diary_id, c.chunk_index, c.createddate,
                   c.title, c.text, v.vector AS lexical_vector,
                   sv.vector AS semantic_vector, sv.text_hash AS semantic_text_hash
            FROM diary_chunks c
            JOIN chunk_vectors v ON v.chunk_id = c.chunk_id
            LEFT JOIN chunk_semantic_vectors sv
              ON sv.chunk_id = c.chunk_id AND sv.provider = ? AND sv.model = ?
            {where}
            """,
            [semantic_provider, semantic_model, *params],
        ).fetchall()

    return con.execute(
        f"""
        SELECT c.chunk_id, c.user_id, c.diary_id, c.chunk_index, c.createddate,
               c.title, c.text, v.vector AS lexical_vector,
               NULL AS semantic_vector, NULL AS semantic_text_hash
        FROM diary_chunks c
        JOIN chunk_vectors v ON v.chunk_id = c.chunk_id
        {where}
        """,
        params,
    ).fetchall()


def _ensure_vector_tables(con: sqlite3.Connection) -> None:
    row = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'").fetchone()
    if not row:
        raise NiderijiError("vector index not found; rerun diaryvault index")


def _has_semantic_table(con: sqlite3.Connection) -> bool:
    row = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_semantic_vectors'").fetchone()
    return bool(row)


def _semantic_vector_count(con: sqlite3.Connection, provider: str, model: str) -> int:
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


def _format_result(root: Path, row: sqlite3.Row, score: float, query: str) -> dict[str, Any]:
    year, filename = diary_entry_name({"id": row["diary_id"], "createddate": row["createddate"]})
    text = normalize_content(row["text"]).strip()
    return {
        "score": round(score, 4),
        "chunk_id": row["chunk_id"],
        "user_id": row["user_id"],
        "diary_id": row["diary_id"],
        "chunk_index": row["chunk_index"],
        "createddate": row["createddate"],
        "title": row["title"],
        "text": _excerpt(text, query),
        "entry_path": str(root / "entries" / year / filename),
    }


def _excerpt(text: str, query: str, *, max_chars: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    index = compact.casefold().find(query.casefold())
    if index < 0:
        return _trim(compact, max_chars)
    start = max(0, index - 60)
    end = min(len(compact), index + len(query) + 140)
    return ("..." if start else "") + compact[start:end] + ("..." if end < len(compact) else "")


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _group_results(results: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        key = _group_key(str(item.get("createddate") or ""), group_by)
        buckets.setdefault(key, []).append(item)

    groups = []
    for key in sorted(buckets, key=_group_sort_key):
        items = buckets[key]
        dates = [str(item.get("createddate") or "") for item in items if item.get("createddate")]
        scores = [float(item["score"]) for item in items if isinstance(item.get("score"), (int, float))]
        groups.append(
            {
                "key": key,
                "label": key if key != "unknown" else "unknown date",
                "count": len(items),
                "date_from": min(dates) if dates else None,
                "date_to": max(dates) if dates else None,
                "top_score": max(scores) if scores else None,
                "results": items,
            }
        )
    return groups


def _group_key(date: str, group_by: str) -> str:
    if group_by == "year" and re.match(r"^\d{4}", date):
        return date[:4]
    return "unknown"


def _group_sort_key(key: str) -> tuple[int, str]:
    return (1, key) if key == "unknown" else (0, key)


def _passes_feature_filter(
    query: str,
    query_features: set[str],
    shared_features: set[str],
    exact_text: bool,
    exact_title: bool,
    haystack: str,
) -> bool:
    if exact_text or exact_title:
        return True
    if not query_features or not shared_features:
        return False

    coverage = len(shared_features) / len(query_features)
    if re.search(r"[\u4e00-\u9fff]", query):
        return coverage >= 0.04

    words = re.findall(r"[a-z0-9]{4,}", query.casefold())
    if not words:
        return False
    return any(word in haystack for word in words)


def _has_current_semantic_vector(row: sqlite3.Row) -> bool:
    return bool(row["semantic_vector"]) and row["semantic_text_hash"] == text_hash(row["text"])


def _fused_results(
    root: Path,
    lexical_scored: list[tuple[float, sqlite3.Row]],
    semantic_scored: list[tuple[float, sqlite3.Row]],
    limit: int,
    query: str,
) -> list[dict[str, Any]]:
    lexical_scored.sort(key=_score_sort_key, reverse=True)
    semantic_scored.sort(key=_score_sort_key, reverse=True)
    window = max(30, limit * 3)
    rows: dict[int, sqlite3.Row] = {}
    fused: dict[int, float] = {}
    details: dict[int, dict[str, float]] = {}

    for rank, (score, row) in enumerate(lexical_scored[:window], start=1):
        chunk_id = int(row["chunk_id"])
        rows[chunk_id] = row
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank)
        details.setdefault(chunk_id, {})["lexical_score"] = round(score, 4)

    for rank, (score, row) in enumerate(semantic_scored[:window], start=1):
        chunk_id = int(row["chunk_id"])
        rows[chunk_id] = row
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank)
        details.setdefault(chunk_id, {})["semantic_score"] = round(score, 4)

    ranked = sorted(
        fused.items(),
        key=lambda item: (
            item[1],
            rows[item[0]]["createddate"] or "",
            rows[item[0]]["diary_id"],
        ),
        reverse=True,
    )
    out = []
    for chunk_id, score in ranked[:limit]:
        item = _format_result(root, rows[chunk_id], score * 100, query)
        item.update(details.get(chunk_id) or {})
        out.append(item)
    return out


def _score_sort_key(item: tuple[float, sqlite3.Row]) -> tuple[float, str, int]:
    score, row = item
    return score, row["createddate"] or "", int(row["diary_id"])


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise NiderijiError(f"{name} must be a number") from exc


def _validate_date(name: str, value: str | None) -> None:
    if value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise NiderijiError(f"{name} date must use YYYY-MM-DD")


def _normalize_group_by(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized != "year":
        raise NiderijiError("group_by must be year")
    return normalized
