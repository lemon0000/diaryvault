from __future__ import annotations

import json
import re
from datetime import date
from typing import Any


IMAGE_REF_PATTERN = re.compile(r"\[图(\d+)\]")


def normalize_content(content: Any) -> str:
    return str(content or "").replace("\r\n", "\n").replace("\r", "\n")


def extract_image_ids(content: str) -> list[int]:
    ids = {int(match.group(1)) for match in IMAGE_REF_PATTERN.finditer(content or "")}
    return sorted(ids)


def markdown_for_diary(
    diary: dict[str, Any],
    *,
    image_exts: dict[int, str] | None = None,
    image_prefix: str = "../../images",
) -> str:
    image_exts = image_exts or {}
    content = normalize_content(diary.get("content"))
    image_ids = extract_image_ids(content)
    body = IMAGE_REF_PATTERN.sub(
        lambda match: _image_markdown(match, image_exts, image_prefix),
        content,
    )

    title = str(diary.get("title") or "").strip()
    createddate = str(diary.get("createddate") or "unknown-date")
    heading = title or createddate

    lines = [
        "---",
        f"id: {_json_value(diary.get('id'))}",
        f"user_id: {_json_value(diary.get('user') or diary.get('user_id'))}",
        f"createddate: {_json_value(createddate)}",
        f"createdtime: {_json_value(diary.get('createdtime'))}",
        f"title: {_json_value(title)}",
        f"weather: {_json_value(diary.get('weather') or '')}",
        f"mood: {_json_value(diary.get('mood') or '')}",
        f"space: {_json_value(diary.get('space') or '')}",
        f"image_ids: {_json_value(image_ids)}",
        "---",
        "",
        f"# {heading}",
        "",
    ]

    tags = []
    if diary.get("weather"):
        tags.append(f"天气: {diary.get('weather')}")
    if diary.get("mood"):
        tags.append(f"心情: {diary.get('mood')}")
    if tags:
        lines.extend([f"**{' | '.join(tags)}**", ""])

    if body.strip():
        lines.append(body.strip())
        lines.append("")

    return "\n".join(lines)


def entry_relative_image_prefix(entry_year: str) -> str:
    if entry_year:
        return "../../images"
    return "../images"


def diary_entry_name(diary: dict[str, Any]) -> tuple[str, str]:
    createddate = str(diary.get("createddate") or "unknown-date")
    year = createddate[:4] if re.match(r"^\d{4}-\d{2}-\d{2}$", createddate) else "unknown"
    diary_id = str(diary.get("id") or "no-id")
    return year, f"{_safe_part(createddate)}-{_safe_part(diary_id)}.md"


def _image_markdown(match: re.Match[str], image_exts: dict[int, str], image_prefix: str) -> str:
    image_id = int(match.group(1))
    ext = image_exts.get(image_id, "jpg")
    return f"![图{image_id}]({image_prefix}/{image_id}.{ext})"


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_part(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-") or "unknown"

