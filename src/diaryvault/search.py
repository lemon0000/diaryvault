from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .index import DEFAULT_DB_NAME
from .markdown import diary_entry_name, normalize_content


def search_vault(
    vault: str | Path,
    query: str = "",
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    order: str = "newest",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if limit <= 0:
        raise NiderijiError("limit must be greater than zero")
    if order not in {"newest", "oldest"}:
        raise NiderijiError("order must be newest or oldest")
    _validate_date("from", date_from)
    _validate_date("to", date_to)

    root = Path(vault).expanduser().resolve()
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    stripped_query = query.strip()
    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        if stripped_query:
            rows, method = _search_text(con, stripped_query, date_from, date_to, limit, order)
        else:
            rows = _search_by_date(con, date_from, date_to, limit, order)
            method = "date"
    finally:
        con.close()

    return {
        "ok": True,
        "db_path": str(target),
        "query": stripped_query,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "order": order,
        "method": method,
        "count": len(rows),
        "results": [_format_result(root, row, stripped_query) for row in rows],
    }


def _search_text(
    con: sqlite3.Connection,
    query: str,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    order: str,
) -> tuple[list[sqlite3.Row], str]:
    if _can_use_fts(con, query):
        try:
            rows = _search_fts(con, query, date_from, date_to, limit, order)
        except sqlite3.OperationalError:
            rows = []
        if rows:
            return rows, "fts"

    return _search_like(con, query, date_from, date_to, limit, order), "like"


def _search_fts(
    con: sqlite3.Connection,
    query: str,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    order: str,
) -> list[sqlite3.Row]:
    clauses = ["diary_fts MATCH ?"]
    params: list[Any] = [_fts_phrase(query)]
    _add_date_clauses(clauses, params, date_from, date_to)
    params.append(limit)
    return con.execute(
        f"""
        SELECT d.user_id, d.diary_id, d.createddate, d.createdtime, d.title, d.content,
               d.weather, d.mood, d.space, d.image_ids_json
        FROM diary_fts
        JOIN diaries d
          ON d.user_id = diary_fts.user_id AND d.diary_id = diary_fts.diary_id
        WHERE {' AND '.join(clauses)}
        ORDER BY d.createddate {_sort_direction(order)}, d.createdtime {_sort_direction(order)}, d.diary_id {_sort_direction(order)}
        LIMIT ?
        """,
        params,
    ).fetchall()


def _search_like(
    con: sqlite3.Connection,
    query: str,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    order: str,
) -> list[sqlite3.Row]:
    pattern = f"%{_escape_like(query)}%"
    clauses = [
        "(d.title LIKE ? ESCAPE '\\' OR d.content LIKE ? ESCAPE '\\' OR d.weather LIKE ? ESCAPE '\\' "
        "OR d.mood LIKE ? ESCAPE '\\' OR d.space LIKE ? ESCAPE '\\')"
    ]
    params: list[Any] = [pattern, pattern, pattern, pattern, pattern]
    _add_date_clauses(clauses, params, date_from, date_to)
    params.append(limit)
    return _select_diaries(con, clauses, params, limit, order)


def _search_by_date(
    con: sqlite3.Connection,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    order: str,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    _add_date_clauses(clauses, params, date_from, date_to)
    params.append(limit)
    return _select_diaries(con, clauses, params, limit, order)


def _select_diaries(
    con: sqlite3.Connection,
    clauses: list[str],
    params: list[Any],
    limit: int,
    order: str,
) -> list[sqlite3.Row]:
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return con.execute(
        f"""
        SELECT d.user_id, d.diary_id, d.createddate, d.createdtime, d.title, d.content,
               d.weather, d.mood, d.space, d.image_ids_json
        FROM diaries d
        {where}
        ORDER BY d.createddate {_sort_direction(order)}, d.createdtime {_sort_direction(order)}, d.diary_id {_sort_direction(order)}
        LIMIT ?
        """,
        params,
    ).fetchall()


def _can_use_fts(con: sqlite3.Connection, query: str) -> bool:
    if len(re.sub(r"\s+", "", query)) < 3:
        return False
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'diary_fts' AND type IN ('table', 'virtual table')"
    ).fetchone()
    return bool(row)


def _add_date_clauses(
    clauses: list[str],
    params: list[Any],
    date_from: str | None,
    date_to: str | None,
) -> None:
    if date_from:
        clauses.append("d.createddate >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("d.createddate <= ?")
        params.append(date_to)


def _format_result(root: Path, row: sqlite3.Row, query: str) -> dict[str, Any]:
    image_ids = _json_list(row["image_ids_json"])
    year, filename = diary_entry_name({"id": row["diary_id"], "createddate": row["createddate"]})
    return {
        "user_id": row["user_id"],
        "diary_id": row["diary_id"],
        "createddate": row["createddate"],
        "createdtime": row["createdtime"],
        "title": row["title"],
        "weather": row["weather"],
        "mood": row["mood"],
        "space": row["space"],
        "image_ids": image_ids,
        "excerpt": _excerpt(row["content"], query),
        "entry_path": str(root / "entries" / year / filename),
    }


def _excerpt(content: str, query: str, *, max_chars: int = 120) -> str:
    text = re.sub(r"\s+", " ", normalize_content(content)).strip()
    if not text:
        return ""
    if not query:
        return _trim(text, max_chars)

    index = text.casefold().find(query.casefold())
    if index < 0:
        return _trim(text, max_chars)

    start = max(0, index - 35)
    end = min(len(text), index + len(query) + 80)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _json_list(value: str) -> list[int]:
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


def _fts_phrase(query: str) -> str:
    return '"' + query.replace("\x00", "").replace('"', '""') + '"'


def _escape_like(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sort_direction(order: str) -> str:
    return "ASC" if order == "oldest" else "DESC"


def _validate_date(name: str, value: str | None) -> None:
    if value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise NiderijiError(f"{name} date must use YYYY-MM-DD")
