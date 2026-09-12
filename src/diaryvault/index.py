from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .markdown import extract_image_ids, normalize_content
from .semantic import ensure_semantic_schema
from .vectors import DEFAULT_VECTOR_DIM, chunk_diary_text, encode_vector, text_hash, text_vector
from .vault import find_image_ext, init_vault, read_json, write_json


DEFAULT_DB_NAME = "diaryvault.sqlite"
SCHEMA_VERSION = 2


def index_vault(vault: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    root = init_vault(vault)
    archive_path = root / "raw" / "archive.json"
    if not archive_path.exists():
        raise NiderijiError(f"archive not found: {archive_path}")

    archive = read_json(archive_path)
    if not isinstance(archive, dict):
        raise NiderijiError("raw/archive.json is not a JSON object")
    diaries = archive.get("diaries")
    if not isinstance(diaries, list):
        raise NiderijiError("raw/archive.json does not contain a diaries list")

    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    semantic_snapshot = _semantic_snapshot(target)

    report: dict[str, Any] = {}
    con = sqlite3.connect(tmp)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        fts_tokenizer = _create_schema(con)
        report = _insert_archive(con, root, archive, diaries, fts_tokenizer)
        report["semantic_vectors_restored"] = _restore_semantic_vectors(con, semantic_snapshot)
        con.commit()
    except Exception:
        con.close()
        if tmp.exists():
            tmp.unlink()
        raise
    else:
        con.close()
        os.replace(tmp, target)

    report["db_path"] = str(target)
    report["archive_path"] = str(archive_path)
    write_json(root / "db" / "index-report.json", report)
    return report


def _create_schema(con: sqlite3.Connection) -> str | None:
    con.executescript(
        """
        CREATE TABLE archive_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE diaries (
          user_id INTEGER NOT NULL,
          diary_id INTEGER NOT NULL,
          createddate TEXT,
          createdtime INTEGER,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          weather TEXT NOT NULL,
          mood TEXT NOT NULL,
          space TEXT NOT NULL,
          image_ids_json TEXT NOT NULL,
          raw_json TEXT NOT NULL,
          PRIMARY KEY (user_id, diary_id)
        );

        CREATE INDEX idx_diaries_createddate ON diaries(createddate, createdtime);
        CREATE INDEX idx_diaries_title ON diaries(title);

        CREATE TABLE images (
          image_id INTEGER PRIMARY KEY,
          ext TEXT,
          has_file INTEGER NOT NULL,
          is_referenced INTEGER NOT NULL,
          raw_json TEXT NOT NULL
        );

        CREATE TABLE diary_images (
          user_id INTEGER NOT NULL,
          diary_id INTEGER NOT NULL,
          image_id INTEGER NOT NULL,
          PRIMARY KEY (user_id, diary_id, image_id),
          FOREIGN KEY (user_id, diary_id) REFERENCES diaries(user_id, diary_id)
        );

        CREATE INDEX idx_diary_images_image_id ON diary_images(image_id);

        CREATE TABLE diary_chunks (
          chunk_id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          diary_id INTEGER NOT NULL,
          chunk_index INTEGER NOT NULL,
          createddate TEXT,
          title TEXT NOT NULL,
          text TEXT NOT NULL,
          FOREIGN KEY (user_id, diary_id) REFERENCES diaries(user_id, diary_id)
        );

        CREATE INDEX idx_diary_chunks_diary ON diary_chunks(user_id, diary_id);
        CREATE INDEX idx_diary_chunks_createddate ON diary_chunks(createddate);

        CREATE TABLE chunk_vectors (
          chunk_id INTEGER PRIMARY KEY,
          dim INTEGER NOT NULL,
          vector BLOB NOT NULL,
          FOREIGN KEY (chunk_id) REFERENCES diary_chunks(chunk_id)
        );
        """
    )
    ensure_semantic_schema(con)
    return _create_fts(con)


def _semantic_snapshot(target: Path) -> list[dict[str, Any]]:
    if not target.exists():
        return []
    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        table = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_semantic_vectors'").fetchone()
        if not table:
            return []
        rows = con.execute(
            """
            SELECT c.user_id, c.diary_id, c.chunk_index,
                   v.provider, v.model, v.dim, v.vector, v.text_hash, v.embedded_at
            FROM chunk_semantic_vectors v
            JOIN diary_chunks c ON c.chunk_id = v.chunk_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def _restore_semantic_vectors(con: sqlite3.Connection, snapshot: list[dict[str, Any]]) -> int:
    if not snapshot:
        return 0

    chunk_rows = con.execute(
        "SELECT chunk_id, user_id, diary_id, chunk_index, text FROM diary_chunks"
    ).fetchall()
    chunk_by_key = {
        (row[1], row[2], row[3], text_hash(row[4])): row[0]
        for row in chunk_rows
    }

    payload = []
    for item in snapshot:
        key = (item["user_id"], item["diary_id"], item["chunk_index"], item["text_hash"])
        chunk_id = chunk_by_key.get(key)
        if not chunk_id:
            continue
        payload.append(
            (
                chunk_id,
                item["provider"],
                item["model"],
                item["dim"],
                item["vector"],
                item["text_hash"],
                item["embedded_at"],
            )
        )

    if not payload:
        return 0
    con.executemany(
        """
        INSERT OR IGNORE INTO chunk_semantic_vectors(chunk_id, provider, model, dim, vector, text_hash, embedded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    return len(payload)


def _create_fts(con: sqlite3.Connection) -> str | None:
    for tokenizer in ("trigram", "unicode61"):
        try:
            con.execute(
                f"""
                CREATE VIRTUAL TABLE diary_fts USING fts5(
                  user_id UNINDEXED,
                  diary_id UNINDEXED,
                  createddate UNINDEXED,
                  title,
                  content,
                  weather,
                  mood,
                  space,
                  tokenize = '{tokenizer}'
                )
                """
            )
            return tokenizer
        except sqlite3.OperationalError:
            continue
    return None


def _insert_archive(
    con: sqlite3.Connection,
    root: Path,
    archive: dict[str, Any],
    diaries: list[dict[str, Any]],
    fts_tokenizer: str | None,
) -> dict[str, Any]:
    meta = archive.get("meta") if isinstance(archive.get("meta"), dict) else {}
    fallback_user_id = _as_int(meta.get("user_id"))
    image_exts = _image_exts(archive)

    con.executemany(
        "INSERT INTO archive_meta(key, value) VALUES (?, ?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("indexed_at", datetime.now(timezone.utc).isoformat()),
            ("archive_meta", json.dumps(meta, ensure_ascii=False, sort_keys=True)),
        ],
    )

    diary_rows = []
    fts_rows = []
    diary_image_rows = []
    chunk_rows = []
    vector_rows = []
    referenced_image_ids: set[int] = set()
    skipped_diary_count = 0
    chunk_id = 1

    for diary in diaries:
        user_id = _as_int(diary.get("user") or diary.get("user_id")) or fallback_user_id
        diary_id = _as_int(diary.get("id"))
        if not user_id or not diary_id:
            skipped_diary_count += 1
            continue

        title = _text(diary.get("title"))
        content = normalize_content(diary.get("content"))
        weather = _text(diary.get("weather"))
        mood = _text(diary.get("mood"))
        space = _text(diary.get("space"))
        createddate = _text(diary.get("createddate")) or None
        createdtime = _as_int(diary.get("createdtime") or diary.get("ts")) or None
        image_ids = _diary_image_ids(diary)
        referenced_image_ids.update(image_ids)

        diary_rows.append(
            (
                user_id,
                diary_id,
                createddate,
                createdtime,
                title,
                content,
                weather,
                mood,
                space,
                json.dumps(image_ids, ensure_ascii=False),
                json.dumps(diary, ensure_ascii=False, sort_keys=True),
            )
        )
        fts_rows.append((user_id, diary_id, createddate, title, content, weather, mood, space))
        diary_image_rows.extend((user_id, diary_id, image_id) for image_id in image_ids)
        for chunk_index, chunk_text in enumerate(chunk_diary_text(title, content)):
            chunk_rows.append((chunk_id, user_id, diary_id, chunk_index, createddate, title, chunk_text))
            vector_rows.append((chunk_id, DEFAULT_VECTOR_DIM, encode_vector(text_vector(chunk_text))))
            chunk_id += 1

    con.executemany(
        """
        INSERT INTO diaries(
          user_id, diary_id, createddate, createdtime, title, content, weather, mood, space, image_ids_json, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        diary_rows,
    )
    con.executemany(
        "INSERT INTO diary_images(user_id, diary_id, image_id) VALUES (?, ?, ?)",
        diary_image_rows,
    )
    con.executemany(
        """
        INSERT INTO diary_chunks(chunk_id, user_id, diary_id, chunk_index, createddate, title, text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        chunk_rows,
    )
    con.executemany(
        "INSERT INTO chunk_vectors(chunk_id, dim, vector) VALUES (?, ?, ?)",
        vector_rows,
    )
    if fts_tokenizer:
        con.executemany(
            """
            INSERT INTO diary_fts(user_id, diary_id, createddate, title, content, weather, mood, space)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            fts_rows,
        )

    image_rows = _image_rows(root, archive, image_exts, referenced_image_ids)
    con.executemany(
        "INSERT INTO images(image_id, ext, has_file, is_referenced, raw_json) VALUES (?, ?, ?, ?, ?)",
        image_rows,
    )

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "diary_count": len(diary_rows),
        "skipped_diary_count": skipped_diary_count,
        "diary_image_count": len(diary_image_rows),
        "chunk_count": len(chunk_rows),
        "vector_dim": DEFAULT_VECTOR_DIM,
        "image_row_count": len(image_rows),
        "referenced_image_count": len(referenced_image_ids),
        "image_file_count": sum(row[2] for row in image_rows),
        "fts_enabled": bool(fts_tokenizer),
        "fts_tokenizer": fts_tokenizer,
    }


def _image_rows(
    root: Path,
    archive: dict[str, Any],
    image_exts: dict[int, str],
    referenced_image_ids: set[int],
) -> list[tuple[int, str | None, int, int, str]]:
    indexed: dict[int, dict[str, Any]] = {}
    for image in archive.get("images") or []:
        if not isinstance(image, dict):
            continue
        image_id = _as_int(image.get("image_id") or image.get("id"))
        if image_id:
            indexed[image_id] = image

    all_ids = set(indexed)
    all_ids.update(_int_values(archive.get("image_ids") or []))
    all_ids.update(_int_values(archive.get("content_image_ids") or []))
    all_ids.update(referenced_image_ids)

    rows = []
    for image_id in sorted(all_ids):
        ext = image_exts.get(image_id) or find_image_ext(root, image_id)
        rows.append(
            (
                image_id,
                ext,
                int(bool(find_image_ext(root, image_id))),
                int(image_id in referenced_image_ids),
                json.dumps(indexed.get(image_id) or {}, ensure_ascii=False, sort_keys=True),
            )
        )
    return rows


def _diary_image_ids(diary: dict[str, Any]) -> list[int]:
    image_ids = set(_int_values(diary.get("image_ids") or []))
    image_ids.update(extract_image_ids(normalize_content(diary.get("content"))))
    return sorted(image_ids)


def _image_exts(archive: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for key, value in dict(archive.get("image_exts") or {}).items():
        image_id = _as_int(key)
        ext = str(value or "").lower().lstrip(".")
        if image_id and ext:
            out[image_id] = ext
    return out


def _int_values(values: Any) -> set[int]:
    out: set[int] = set()
    if not isinstance(values, list):
        return out
    for value in values:
        item = _as_int(value)
        if item:
            out.add(item)
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()
