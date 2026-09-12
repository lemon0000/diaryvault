from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

from .client import NiderijiError
from .vault import init_vault, write_entries, write_image, write_json


def import_archive_zip(zip_path: str | Path, vault: str | Path, *, replace: bool = False) -> dict[str, Any]:
    source = Path(zip_path).expanduser().resolve()
    if not source.exists():
        raise NiderijiError(f"zip file not found: {source}")

    root = init_vault(vault)
    archive_target = root / "raw" / "archive.json"
    if archive_target.exists() and not replace:
        raise NiderijiError(f"{archive_target} already exists; rerun with --replace to overwrite archive files")

    try:
        with ZipFile(source) as zf:
            archive_member = find_archive_json(zf.namelist())
            if not archive_member:
                raise NiderijiError("zip does not contain archive.json")
            archive = json.loads(zf.read(archive_member).decode("utf-8-sig"))
            if not isinstance(archive, dict):
                raise NiderijiError("archive.json is not a JSON object")
            diaries = archive.get("diaries")
            if not isinstance(diaries, list):
                raise NiderijiError("archive.json does not contain a diaries list")

            image_exts = dict(archive.get("image_exts") or {})
            image_count = 0
            for name in zf.namelist():
                image_id, ext = parse_image_member(name)
                if image_id is None:
                    continue
                write_image(root, image_id, ext, zf.read(name))
                image_exts[str(image_id)] = ext
                image_count += 1
    except BadZipFile as exc:
        raise NiderijiError(f"invalid zip file: {source}") from exc
    except json.JSONDecodeError as exc:
        raise NiderijiError("archive.json is not valid JSON") from exc

    archive["image_exts"] = image_exts
    write_json(archive_target, archive)
    written_entries = write_entries(root, diaries, image_exts=_int_image_exts(image_exts))

    report = {
        "source_zip": str(source),
        "archive_member": archive_member,
        "diary_count": len(diaries),
        "image_count": image_count,
        "written_entry_count": len(written_entries),
        "archive_target": str(archive_target),
        "replace": replace,
    }
    write_json(root / "raw" / "import-report.json", report)
    return report


def find_archive_json(names: list[str]) -> str | None:
    if "archive.json" in names:
        return "archive.json"
    for name in names:
        if PurePosixPath(name).name == "archive.json":
            return name
    return None


def parse_image_member(name: str) -> tuple[int | None, str]:
    path = PurePosixPath(name)
    parts = path.parts
    if len(parts) != 2 or parts[0] != "Images":
        return None, ""
    stem = path.stem
    if not stem.isdigit():
        return None, ""
    ext = path.suffix.lower().lstrip(".") or "jpg"
    return int(stem), ext


def _int_image_exts(image_exts: dict[str, str]) -> dict[int, str]:
    return {int(k): str(v).lower().lstrip(".") for k, v in image_exts.items() if str(k).isdigit()}

