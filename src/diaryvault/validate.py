from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .markdown import diary_entry_name, extract_image_ids, normalize_content


SUPPORTED_IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif")


def validate_vault(vault: str | Path) -> dict[str, Any]:
    root = Path(vault).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {"vault": str(root)}

    archive_path = root / "raw" / "archive.json"
    archive = load_archive(archive_path, errors)
    if not archive:
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats}

    diaries = archive.get("diaries")
    if not isinstance(diaries, list):
        errors.append("raw/archive.json: diaries is missing or not a list")
        diaries = []

    meta = archive.get("meta") if isinstance(archive.get("meta"), dict) else {}
    expected_count = meta.get("diary_count")
    if isinstance(expected_count, int) and expected_count != len(diaries):
        errors.append(f"meta.diary_count is {expected_count}, but archive has {len(diaries)} diaries")

    stats["diary_count"] = len(diaries)
    stats["first_date"] = meta.get("first_date")
    stats["last_date"] = meta.get("last_date")

    content_image_ids = sorted({image_id for diary in diaries for image_id in extract_image_ids(normalize_content(diary.get("content")))})
    archived_content_ids = sorted(_int_set(archive.get("content_image_ids") or []))
    if archived_content_ids and archived_content_ids != content_image_ids:
        errors.append("archive content_image_ids does not match image references in diary content")

    archive_image_ids = sorted(_int_set(archive.get("image_ids") or content_image_ids))
    referenced_not_archived = sorted(set(content_image_ids) - set(archive_image_ids))
    if referenced_not_archived:
        warnings.append(f"content references images not present in archive image set: {referenced_not_archived[:20]}")
    image_exts = {
        int(k): str(v).lower().lstrip(".")
        for k, v in dict(archive.get("image_exts") or {}).items()
        if str(k).isdigit()
    }

    missing_entries = []
    for diary in diaries:
        year, filename = diary_entry_name(diary)
        if not (root / "entries" / year / filename).exists():
            missing_entries.append(str(Path("entries") / year / filename))
    if missing_entries:
        errors.append(f"missing Markdown entries: {missing_entries[:10]}")
    stats["missing_entry_count"] = len(missing_entries)

    validation = archive.get("validation") if isinstance(archive.get("validation"), dict) else {}
    images_requested = validation.get("status") != "metadata-only"
    missing_images = [image_id for image_id in archive_image_ids if not image_exists(root, image_id, image_exts.get(image_id))]
    if missing_images and images_requested:
        errors.append(f"missing image files: {missing_images[:20]}")
    elif missing_images:
        warnings.append(f"image files not present for metadata-only archive: {missing_images[:20]}")
    stats["content_image_count"] = len(content_image_ids)
    stats["archive_image_count"] = len(archive_image_ids)
    stats["referenced_not_archived_image_count"] = len(referenced_not_archived)
    stats["missing_image_count"] = len(missing_images)

    privacy_cipher_markers = sum("隐私区域密文" in normalize_content(diary.get("content")) for diary in diaries)
    if privacy_cipher_markers:
        warnings.append(f"{privacy_cipher_markers} diaries still contain privacy ciphertext markers")
    stats["privacy_cipher_marker_count"] = privacy_cipher_markers

    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats}


def load_archive(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(f"missing {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        errors.append(f"raw/archive.json is not valid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append("raw/archive.json is not a JSON object")
        return None
    return value


def image_exists(root: Path, image_id: int, ext: str | None) -> bool:
    if ext:
        return (root / "images" / f"{image_id}.{ext}").exists()
    return any((root / "images" / f"{image_id}.{candidate}").exists() for candidate in SUPPORTED_IMAGE_EXTS)


def _int_set(values: list[Any]) -> set[int]:
    out: set[int] = set()
    for value in values:
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return out
