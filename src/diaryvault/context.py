from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .index import DEFAULT_DB_NAME
from .markdown import normalize_content
from .recall import recall_vault
from .search import search_vault
from .vault import init_vault, write_text


def context_vault(
    vault: str | Path,
    query: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 12,
    order: str = "newest",
    full: bool = False,
    max_chars: int = 1200,
    method: str = "recall",
    output: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not query.strip():
        raise NiderijiError("context query is required")
    if max_chars <= 0:
        raise NiderijiError("max-chars must be greater than zero")
    if method not in {"recall", "search"}:
        raise NiderijiError("method must be recall or search")

    root = init_vault(vault)
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    pack = build_context_pack(
        root,
        query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        order=order,
        full=full,
        max_chars=max_chars,
        method=method,
        db_path=target,
    )
    text = pack["text"]

    if output:
        output_path = Path(output).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = root / "reports" / f"context-{stamp}.md"
    write_text(output_path, text)

    return {
        "ok": True,
        "query": query.strip(),
        "db_path": str(target),
        "output_path": str(output_path),
        "count": pack["count"],
        "search_method": pack["search_method"],
        "full": full,
        "max_chars": max_chars,
        "results": pack["results"],
    }


def build_context_pack(
    vault: str | Path,
    query: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 12,
    order: str = "newest",
    full: bool = False,
    max_chars: int = 1200,
    method: str = "recall",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not query.strip():
        raise NiderijiError("context query is required")
    if max_chars <= 0:
        raise NiderijiError("max-chars must be greater than zero")
    if method not in {"recall", "search"}:
        raise NiderijiError("method must be recall or search")

    root = Path(vault).expanduser().resolve()
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    search = _retrieve(root, target, query, date_from, date_to, limit, order, method)
    items = _load_context_items(target, search["results"], full=full, max_chars=max_chars)
    text = context_markdown(query, search, items, full=full)
    return {
        "ok": True,
        "query": query.strip(),
        "db_path": str(target),
        "count": len(items),
        "search_method": search["method"],
        "full": full,
        "max_chars": max_chars,
        "results": items,
        "text": text,
    }


def _retrieve(
    root: Path,
    db_path: Path,
    query: str,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    order: str,
    method: str,
) -> dict[str, Any]:
    if method == "search":
        return search_vault(
            root,
            query,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            order=order,
            db_path=db_path,
        )
    return recall_vault(
        root,
        query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        db_path=db_path,
    )


def context_markdown(query: str, search: dict[str, Any], items: list[dict[str, Any]], *, full: bool) -> str:
    lines = [
        "# DiaryVault context pack",
        "",
        f"Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"Query: `{query.strip()}`",
        f"Search method: `{search['method']}`",
        f"Date range: `{search['date_from'] or '*'}` to `{search['date_to'] or '*'}`",
        f"Entries: {len(items)}",
        f"Mode: {'full' if full else 'excerpt'}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        title = item["title"] or "(untitled)"
        lines.extend(
            [
                f"## {index}. {item['createddate']} #{item['diary_id']} {title}",
                "",
                f"- Path: `{item['entry_path']}`",
                f"- Weather/Mood/Space: `{_join_tags(item)}`",
                "",
                item["text"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_context_items(
    db_path: Path,
    results: list[dict[str, Any]],
    *,
    full: bool,
    max_chars: int,
) -> list[dict[str, Any]]:
    if not results:
        return []

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        out = []
        for item in results:
            text = item.get("text") or item.get("excerpt") or ""
            if full:
                row = con.execute(
                    "SELECT content FROM diaries WHERE user_id = ? AND diary_id = ?",
                    (item["user_id"], item["diary_id"]),
                ).fetchone()
                if row:
                    text = _trim(normalize_content(row["content"]).strip(), max_chars)
            out.append({**item, "text": text})
        return out
    finally:
        con.close()


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _join_tags(item: dict[str, Any]) -> str:
    tags = [str(item.get(key) or "").strip() for key in ("weather", "mood", "space")]
    return " | ".join(tag for tag in tags if tag) or "-"
