from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .markdown import extract_image_ids, normalize_content


def select_raw(raw: dict[str, Any], mode: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if mode == "mine":
        return list(raw.get("diaries") or []), list(raw.get("images") or [])
    if mode == "partner":
        return list(raw.get("diaries_paired") or []), list(raw.get("images_paired") or [])
    return (
        list(raw.get("diaries") or []) + list(raw.get("diaries_paired") or []),
        list(raw.get("images") or []) + list(raw.get("images_paired") or []),
    )


def infer_user_id(raw: dict[str, Any]) -> int | None:
    candidates = [
        raw.get("user"),
        raw.get("me"),
        raw.get("profile"),
        raw.get("user_config"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("id", "userid", "user_id", "uid", "user"):
            value = candidate.get(key)
            try:
                if value:
                    return int(value)
            except (TypeError, ValueError):
                continue
    return None


def choose_diaries(
    diaries: list[dict[str, Any]],
    *,
    limit: int | None = None,
    order: str = "newest",
) -> list[dict[str, Any]]:
    ordered = sorted(diaries, key=_diary_sort_key, reverse=(order == "newest"))
    if limit and limit > 0:
        ordered = ordered[:limit]
    return sorted(ordered, key=_diary_sort_key)


def choose_recent_diaries(
    diaries: list[dict[str, Any]],
    *,
    days: int,
    today: date | None = None,
) -> list[dict[str, Any]]:
    if days <= 0:
        raise ValueError("days must be greater than zero")
    today = today or date.today()
    cutoff = today - timedelta(days=days - 1)
    chosen = []
    for diary in diaries:
        created = _parse_date(diary.get("createddate"))
        if created and created >= cutoff:
            chosen.append(diary)
    return sorted(chosen, key=_diary_sort_key)


def merge_diaries(
    existing: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[int, int], dict[str, Any]] = {}
    for diary in existing:
        key = _diary_key(diary)
        if key != (0, 0):
            merged[key] = diary
    for diary in updates:
        key = _diary_key(diary)
        if key != (0, 0):
            merged[key] = diary
    return sorted(merged.values(), key=_diary_sort_key)


def build_image_plan(
    diaries: list[dict[str, Any]],
    images: list[dict[str, Any]],
    fallback_user_id: int,
) -> dict[str, Any]:
    content_ids: set[int] = set()
    owner_by_id: dict[int, int] = {}

    for diary in diaries:
        owner_id = _as_int(diary.get("user") or diary.get("user_id") or fallback_user_id)
        for image_id in extract_image_ids(normalize_content(diary.get("content"))):
            content_ids.add(image_id)
            owner_by_id[image_id] = owner_id

    indexed_ids: set[int] = set()
    for image in images:
        image_id = _as_int(image.get("image_id") or image.get("id"))
        if not image_id:
            continue
        indexed_ids.add(image_id)
        owner_by_id.setdefault(
            image_id,
            _as_int(image.get("user") or image.get("user_id") or image.get("owner") or fallback_user_id),
        )

    downloadable = sorted(content_ids & indexed_ids)
    return {
        "content_image_ids": sorted(content_ids),
        "indexed_image_ids": sorted(indexed_ids),
        "image_ids": downloadable,
        "referenced_not_indexed": sorted(content_ids - indexed_ids),
        "indexed_not_referenced": sorted(indexed_ids - content_ids),
        "owner_by_id": owner_by_id,
    }


def build_archive(
    *,
    raw: dict[str, Any],
    mode: str,
    user_id: int,
    diaries: list[dict[str, Any]],
    selected_images: list[dict[str, Any]],
    image_plan: dict[str, Any],
    image_results: dict[str, Any],
    limit: int | None,
) -> dict[str, Any]:
    dates = [str(item.get("createddate")) for item in diaries if item.get("createddate")]
    meta = {
        "app": "Nideriji",
        "exporter": "DiaryVault",
        "schema_version": 1,
        "export_mode": mode,
        "export_time": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "limit": limit,
        "diary_count": len(diaries),
        "raw_own_diary_count": len(raw.get("diaries") or []),
        "raw_paired_diary_count": len(raw.get("diaries_paired") or []),
        "raw_own_image_count": len(raw.get("images") or []),
        "raw_paired_image_count": len(raw.get("images_paired") or []),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }
    validation = {
        "status": _validation_status(image_results),
        "content_image_count": len(image_plan["content_image_ids"]),
        "indexed_image_count": len(image_plan["indexed_image_ids"]),
        "archive_image_count": len(image_plan["image_ids"]),
        "downloaded_image_count": len(image_results.get("downloaded_images") or []),
        "unavailable_image_count": len(image_results.get("unavailable_images") or []),
        "failed_image_count": len(image_results.get("failed_images") or []),
        "referenced_not_indexed": image_plan["referenced_not_indexed"],
        "indexed_not_referenced": image_plan["indexed_not_referenced"],
        "unavailable_images": image_results.get("unavailable_images") or [],
        "failed_images": image_results.get("failed_images") or [],
    }
    return {
        "meta": meta,
        "diaries": diaries,
        "images": selected_images,
        "image_ids": image_plan["image_ids"],
        "content_image_ids": image_plan["content_image_ids"],
        "indexed_image_ids": image_plan["indexed_image_ids"],
        "image_exts": image_results.get("image_exts") or {},
        "validation": validation,
    }


def _diary_sort_key(diary: dict[str, Any]) -> tuple[str, int, int]:
    createddate = str(diary.get("createddate") or "")
    createdtime = _as_int(diary.get("createdtime") or diary.get("ts"))
    diary_id = _as_int(diary.get("id"))
    return createddate, createdtime, diary_id


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _diary_key(diary: dict[str, Any]) -> tuple[int, int]:
    return _as_int(diary.get("user") or diary.get("user_id")), _as_int(diary.get("id"))


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _validation_status(image_results: dict[str, Any]) -> str:
    if not image_results.get("images_requested"):
        return "metadata-only"
    return "incomplete" if image_results.get("failed_images") else "ok"
