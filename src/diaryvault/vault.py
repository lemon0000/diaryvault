from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .markdown import diary_entry_name, markdown_for_diary


VAULT_DIRS = ("raw", "entries", "images", "db", "logs", "reports", "backup")
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif")


def init_vault(vault: str | Path) -> Path:
    root = Path(vault).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in VAULT_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_text(path: str | Path, value: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    os.replace(tmp, target)


def write_entries(
    vault: str | Path,
    diaries: list[dict[str, Any]],
    *,
    image_exts: dict[int, str] | None = None,
) -> list[str]:
    root = Path(vault)
    written: list[str] = []
    for diary in diaries:
        year, filename = diary_entry_name(diary)
        path = root / "entries" / year / filename
        write_text(path, markdown_for_diary(diary, image_exts=image_exts))
        written.append(str(path))
    return written


def write_image(vault: str | Path, image_id: int, ext: str, data: bytes) -> Path:
    target = Path(vault) / "images" / f"{image_id}.{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target


def find_image_ext(vault: str | Path, image_id: int) -> str | None:
    root = Path(vault)
    for ext in IMAGE_EXTS:
        if (root / "images" / f"{image_id}.{ext}").exists():
            return ext
    return None
