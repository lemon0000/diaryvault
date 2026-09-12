from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .client import NiderijiError
from .vault import init_vault, read_json, write_json


def bundle_vault(
    vault: str | Path,
    *,
    output: str | Path | None = None,
    include_images: bool = True,
    include_db: bool = True,
    replace: bool = False,
) -> dict[str, Any]:
    root = init_vault(vault)
    archive_path = root / "raw" / "archive.json"
    if not archive_path.exists():
        raise NiderijiError(f"archive not found: {archive_path}")

    target = _target_path(root, output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not replace:
        raise NiderijiError(f"backup already exists: {target}; rerun with --replace to overwrite")

    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()

    archive = read_json(archive_path)
    diaries = archive.get("diaries") if isinstance(archive, dict) else []
    files = list(_iter_bundle_files(root, include_images=include_images, include_db=include_db))
    manifest = {
        "app": "DiaryVault",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(root),
        "diary_count": len(diaries) if isinstance(diaries, list) else None,
        "include_images": include_images,
        "include_db": include_db,
        "file_count": len(files),
    }

    try:
        with ZipFile(tmp, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", _json_bytes(manifest))
            for path in files:
                zf.write(path, path.relative_to(root).as_posix())
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise

    manifest["output_path"] = str(target)
    manifest["size_bytes"] = target.stat().st_size
    write_json(root / "backup" / "latest-export-report.json", manifest)
    return manifest


def _iter_bundle_files(root: Path, *, include_images: bool, include_db: bool) -> list[Path]:
    files: list[Path] = []
    for directory in ("raw", "entries", "reports"):
        files.extend(_files_under(root / directory))
    if include_images:
        files.extend(_files_under(root / "images"))
    if include_db:
        files.extend(_files_under(root / "db"))
    return sorted(path for path in files if path.is_file())


def _files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [item for item in path.rglob("*") if item.is_file()]


def _target_path(root: Path, output: str | Path | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / "backup" / f"DiaryVault-export-{stamp}.zip"


def _json_bytes(value: dict[str, Any]) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
