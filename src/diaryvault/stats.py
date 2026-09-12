from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .index import DEFAULT_DB_NAME
from .markdown import normalize_content
from .vault import init_vault, write_json, write_text


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def stats_vault(
    vault: str | Path,
    *,
    db_path: str | Path | None = None,
    write_report: bool = False,
) -> dict[str, Any]:
    root = init_vault(vault)
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME
    if not target.exists():
        raise NiderijiError(f"database not found: {target}; run diaryvault index first")

    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT diary_id, createddate, createdtime, title, content, weather, mood, space
            FROM diaries
            ORDER BY createddate ASC, createdtime ASC, diary_id ASC
            """
        ).fetchall()
    finally:
        con.close()

    report = _build_stats(root, target, rows)
    if write_report:
        reports_dir = root / "reports"
        write_json(reports_dir / "stats.json", report)
        write_text(reports_dir / "stats.md", stats_markdown(report))
        report["written_reports"] = [str(reports_dir / "stats.json"), str(reports_dir / "stats.md")]
    return report


def stats_markdown(report: dict[str, Any]) -> str:
    overview = report["overview"]
    lines = [
        "# DiaryVault stats",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Overview",
        "",
        f"- Diaries: {overview['diary_count']}",
        f"- Active days: {overview['active_day_count']}",
        f"- Date range: {overview['first_date']} to {overview['last_date']}",
        f"- Total characters: {overview['total_character_count']}",
        f"- Average characters per diary: {overview['average_characters_per_diary']}",
        f"- Current streak: {overview['current_streak_days']} days",
        f"- Longest streak: {overview['longest_streak_days']} days",
        "",
    ]
    lines.extend(_table("By year", ("Year", "Count"), report["by_year"].items()))
    lines.extend(_table("By month", ("Month", "Count"), report["by_month"].items()))
    lines.extend(_table("By weekday", ("Weekday", "Count"), report["by_weekday"].items()))
    lines.extend(_table("Top moods", ("Mood", "Count"), report["top_moods"]))
    lines.extend(_table("Top weather", ("Weather", "Count"), report["top_weather"]))
    lines.extend(_table("Top spaces", ("Space", "Count"), report["top_spaces"]))
    return "\n".join(lines).rstrip() + "\n"


def _build_stats(root: Path, target: Path, rows: list[sqlite3.Row]) -> dict[str, Any]:
    dates: list[date] = []
    by_year: Counter[str] = Counter()
    by_month: Counter[str] = Counter()
    by_weekday: Counter[str] = Counter()
    moods: Counter[str] = Counter()
    weather: Counter[str] = Counter()
    spaces: Counter[str] = Counter()
    character_count = 0
    titled_count = 0

    for row in rows:
        parsed = _parse_date(row["createddate"])
        if parsed:
            dates.append(parsed)
            by_year[str(parsed.year)] += 1
            by_month[f"{parsed.year:04d}-{parsed.month:02d}"] += 1
            by_weekday[WEEKDAYS[parsed.weekday()]] += 1
        character_count += len(normalize_content(row["content"]))
        if str(row["title"] or "").strip():
            titled_count += 1
        _add_count(moods, row["mood"])
        _add_count(weather, row["weather"])
        _add_count(spaces, row["space"])

    unique_dates = sorted(set(dates))
    overview = {
        "diary_count": len(rows),
        "active_day_count": len(unique_dates),
        "first_date": unique_dates[0].isoformat() if unique_dates else None,
        "last_date": unique_dates[-1].isoformat() if unique_dates else None,
        "total_character_count": character_count,
        "average_characters_per_diary": round(character_count / len(rows), 1) if rows else 0,
        "titled_diary_count": titled_count,
        "current_streak_days": _current_streak(unique_dates),
        "longest_streak_days": _longest_streak(unique_dates),
    }
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(root),
        "db_path": str(target),
        "overview": overview,
        "by_year": dict(sorted(by_year.items())),
        "by_month": dict(sorted(by_month.items())),
        "by_weekday": {name: by_weekday.get(name, 0) for name in WEEKDAYS},
        "top_moods": moods.most_common(20),
        "top_weather": weather.most_common(20),
        "top_spaces": spaces.most_common(20),
    }


def _current_streak(values: list[date]) -> int:
    if not values:
        return 0
    value_set = set(values)
    current = values[-1]
    count = 0
    while current in value_set:
        count += 1
        current -= timedelta(days=1)
    return count


def _longest_streak(values: list[date]) -> int:
    if not values:
        return 0
    longest = current = 1
    for previous, item in zip(values, values[1:]):
        if item == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def _add_count(counter: Counter[str], value: Any) -> None:
    text = str(value or "").strip()
    if text:
        counter[text] += 1


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _table(title: str, headers: tuple[str, str], rows: Any) -> list[str]:
    materialized = list(rows)
    if not materialized:
        return []
    lines = [f"## {title}", "", f"| {headers[0]} | {headers[1]} |", "| --- | ---: |"]
    for key, count in materialized:
        lines.append(f"| {key} | {count} |")
    lines.append("")
    return lines
