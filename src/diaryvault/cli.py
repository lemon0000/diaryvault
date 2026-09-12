from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Any

from .api import DEFAULT_API_HOST, DEFAULT_API_PORT, serve_api
from .archive import (
    build_archive,
    build_image_plan,
    choose_diaries,
    choose_recent_diaries,
    infer_user_id,
    merge_diaries,
    select_raw,
)
from .bundle import bundle_vault
from .client import ImageUnavailable, NiderijiClient, NiderijiError
from .context import context_vault
from .index import index_vault
from .import_zip import import_archive_zip
from .mcp_server import DEFAULT_MCP_HTTP_HOST, DEFAULT_MCP_HTTP_PATH, DEFAULT_MCP_HTTP_PORT
from .recall import recall_vault
from .search import search_vault
from .semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_SEMANTIC_MODEL,
    DEFAULT_SEMANTIC_PROVIDER,
    SemanticEmbeddingError,
    index_semantic_vectors,
)
from .stats import stats_vault
from .validate import validate_vault
from .vault import find_image_ext, init_vault, read_json, write_entries, write_image, write_json


DEFAULT_VAULT = "DiaryVault"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            root = init_vault(args.vault)
            print(f"Initialized vault: {root}")
            return 0
        if args.command in {"sample", "sync"}:
            return run_sync(args)
        if args.command == "daily":
            return run_daily(args)
        if args.command == "import-zip":
            return run_import_zip(args)
        if args.command == "index":
            return run_index(args)
        if args.command == "semantic-index":
            return run_semantic_index(args)
        if args.command == "search":
            return run_search(args)
        if args.command == "recall":
            return run_recall(args)
        if args.command == "stats":
            return run_stats(args)
        if args.command == "context":
            return run_context(args)
        if args.command == "export":
            return run_export(args)
        if args.command == "mcp":
            return run_mcp(args)
        if args.command == "mcp-http":
            return run_mcp_http(args)
        if args.command == "serve":
            return run_serve(args)
        if args.command == "validate":
            return run_validate(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except NiderijiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diaryvault")
    sub = parser.add_subparsers(dest="command")

    init_cmd = sub.add_parser("init", help="Create the local vault folder structure.")
    init_cmd.add_argument("--vault", default=DEFAULT_VAULT)

    sample_cmd = sub.add_parser("sample", help="Fetch a small sample for validation.")
    add_sync_args(sample_cmd, default_limit=10)

    sync_cmd = sub.add_parser("sync", help="Fetch all matching diaries unless --limit is set.")
    add_sync_args(sync_cmd, default_limit=0)

    daily_cmd = sub.add_parser("daily", help="Merge recent diary updates into an existing full vault.")
    add_daily_args(daily_cmd)

    import_cmd = sub.add_parser("import-zip", help="Import an archive-studio ZIP into the vault.")
    import_cmd.add_argument("zip_path")
    import_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    import_cmd.add_argument("--replace", action="store_true", help="Overwrite raw/archive.json if it already exists.")

    index_cmd = sub.add_parser("index", help="Build or rebuild the local SQLite index.")
    index_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    index_cmd.add_argument("--db-path", help="Override the SQLite output path.")

    semantic_cmd = sub.add_parser("semantic-index", help="Build semantic embedding vectors for diary chunks.")
    semantic_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    semantic_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    semantic_cmd.add_argument("--provider", default=DEFAULT_SEMANTIC_PROVIDER, choices=("ollama",))
    semantic_cmd.add_argument("--model", default=os.environ.get("DIARYVAULT_SEMANTIC_MODEL") or DEFAULT_SEMANTIC_MODEL)
    semantic_cmd.add_argument("--base-url", default=os.environ.get("DIARYVAULT_OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL)
    semantic_cmd.add_argument("--batch-size", type=int, default=16)
    semantic_cmd.add_argument("--limit", type=int, help="Embed at most this many pending chunks.")
    semantic_cmd.add_argument("--timeout", type=int, default=120)
    semantic_cmd.add_argument("--force", action="store_true", help="Re-embed all chunks for the selected model.")
    semantic_cmd.add_argument("--skip-if-unavailable", action="store_true", help="Exit 0 if the embedding provider is unavailable.")
    semantic_cmd.add_argument("--json", action="store_true", help="Print results as JSON.")

    search_cmd = sub.add_parser("search", help="Search the local SQLite index.")
    search_cmd.add_argument("query", nargs="?", default="", help="Keyword or phrase. Omit to list by date.")
    search_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    search_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    search_cmd.add_argument("--from", dest="date_from", help="Start date, YYYY-MM-DD.")
    search_cmd.add_argument("--to", dest="date_to", help="End date, YYYY-MM-DD.")
    search_cmd.add_argument("--limit", type=int, default=20)
    search_cmd.add_argument("--order", choices=("newest", "oldest"), default="newest")
    search_cmd.add_argument("--json", action="store_true", help="Print results as JSON.")

    recall_cmd = sub.add_parser("recall", help="Retrieve similar local diary chunks with the vector index.")
    recall_cmd.add_argument("query")
    recall_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    recall_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    recall_cmd.add_argument("--from", dest="date_from", help="Start date, YYYY-MM-DD.")
    recall_cmd.add_argument("--to", dest="date_to", help="End date, YYYY-MM-DD.")
    recall_cmd.add_argument("--limit", type=int, default=12)
    recall_cmd.add_argument("--semantic", choices=("auto", "off", "required"), default="auto")
    recall_cmd.add_argument("--semantic-provider", default=None)
    recall_cmd.add_argument("--semantic-model", default=None)
    recall_cmd.add_argument("--semantic-base-url", default=None)
    recall_cmd.add_argument("--semantic-min-score", type=float, default=None)
    recall_cmd.add_argument("--group-by", choices=("year",), help="Group returned recall results by time bucket.")
    recall_cmd.add_argument("--json", action="store_true", help="Print results as JSON.")

    stats_cmd = sub.add_parser("stats", help="Summarize the local SQLite index.")
    stats_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    stats_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    stats_cmd.add_argument("--write-report", action="store_true", help="Write reports/stats.json and reports/stats.md.")
    stats_cmd.add_argument("--json", action="store_true", help="Print results as JSON.")

    context_cmd = sub.add_parser("context", help="Build a local context pack for a question or keyword.")
    context_cmd.add_argument("query")
    context_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    context_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    context_cmd.add_argument("--from", dest="date_from", help="Start date, YYYY-MM-DD.")
    context_cmd.add_argument("--to", dest="date_to", help="End date, YYYY-MM-DD.")
    context_cmd.add_argument("--limit", type=int, default=12)
    context_cmd.add_argument("--order", choices=("newest", "oldest"), default="newest")
    context_cmd.add_argument("--full", action="store_true", help="Include trimmed full entry text instead of excerpts.")
    context_cmd.add_argument("--max-chars", type=int, default=1200)
    context_cmd.add_argument("--method", choices=("recall", "search"), default="recall")
    context_cmd.add_argument("--output", help="Output Markdown path. Defaults to reports/context-*.md.")
    context_cmd.add_argument("--json", action="store_true", help="Print metadata and results as JSON.")

    export_cmd = sub.add_parser("export", help="Create a ZIP backup bundle from the local vault.")
    export_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    export_cmd.add_argument("--output", help="Output ZIP path. Defaults to backup/DiaryVault-export-*.zip.")
    export_cmd.add_argument("--no-images", action="store_true")
    export_cmd.add_argument("--no-db", action="store_true")
    export_cmd.add_argument("--replace", action="store_true", help="Overwrite output ZIP if it already exists.")

    mcp_cmd = sub.add_parser("mcp", help="Run the read-only DiaryVault MCP server over stdio.")
    mcp_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    mcp_cmd.add_argument("--db-path", help="Override the SQLite database path.")

    mcp_http_cmd = sub.add_parser("mcp-http", help="Run the read-only DiaryVault MCP server over streamable HTTP.")
    mcp_http_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    mcp_http_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    mcp_http_cmd.add_argument("--host", default=DEFAULT_MCP_HTTP_HOST)
    mcp_http_cmd.add_argument("--port", type=int, default=DEFAULT_MCP_HTTP_PORT)
    mcp_http_cmd.add_argument("--path", default=DEFAULT_MCP_HTTP_PATH)
    mcp_http_cmd.add_argument("--api-token", help="Require Authorization: Bearer TOKEN.")
    mcp_http_cmd.add_argument("--api-token-file", help="Read API token from a local text file.")
    mcp_http_cmd.add_argument("--allow-host", action="append", default=[], help="Allowed Host header for tunnel domains.")
    mcp_http_cmd.add_argument("--allow-origin", action="append", default=[], help="Allowed Origin header.")
    mcp_http_cmd.add_argument("--log-level", default="info")

    serve_cmd = sub.add_parser("serve", help="Run the local DiaryVault memory HTTP API.")
    serve_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    serve_cmd.add_argument("--db-path", help="Override the SQLite database path.")
    serve_cmd.add_argument("--host", default=DEFAULT_API_HOST)
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    serve_cmd.add_argument("--api-token", help="Require Authorization: Bearer TOKEN.")
    serve_cmd.add_argument("--api-token-file", help="Read API token from a local text file.")

    validate_cmd = sub.add_parser("validate", help="Validate archive, entries and image files in a vault.")
    validate_cmd.add_argument("--vault", default=DEFAULT_VAULT)
    validate_cmd.add_argument("--json", action="store_true", help="Print the full validation report as JSON.")

    return parser


def add_sync_args(parser: argparse.ArgumentParser, *, default_limit: int) -> None:
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--mode", choices=("mine", "partner", "all"), default="mine")
    parser.add_argument("--limit", type=int, default=default_limit, help="0 means no limit.")
    parser.add_argument("--order", choices=("newest", "oldest"), default="newest")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--no-decrypt-privacy", action="store_true")
    parser.add_argument("--email", help="Login email. Password is read interactively or from NIDERIJI_PASSWORD.")
    parser.add_argument("--user-id", type=int, help="User id override. Prefer NIDERIJI_USER_ID with token auth.")
    parser.add_argument("--secrets-file", help="Read local NIDERIJI_* secrets from a key=value file.")


def add_daily_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--mode", choices=("mine", "partner", "all"), default="mine")
    parser.add_argument("--days", type=int, default=14, help="Refresh diaries whose diary date is within this window.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--no-decrypt-privacy", action="store_true")
    parser.add_argument("--email", help="Login email. Password is read interactively or from NIDERIJI_PASSWORD.")
    parser.add_argument("--user-id", type=int, help="User id override. Prefer NIDERIJI_USER_ID with token auth.")
    parser.add_argument("--secrets-file", help="Read local NIDERIJI_* secrets from a key=value file.")


def run_sync(args: argparse.Namespace) -> int:
    vault = init_vault(args.vault)
    client = make_client(args)

    print("Fetching sync metadata...")
    raw = client.sync()
    user_id = client.user_id or args.user_id or _env_int("NIDERIJI_USER_ID") or infer_user_id(raw)
    if not user_id:
        raise NiderijiError("could not infer user id; set --user-id or NIDERIJI_USER_ID")
    client.user_id = user_id

    raw_diaries, raw_images = select_raw(raw, args.mode)
    limit = args.limit if args.limit and args.limit > 0 else None
    selected_diaries = choose_diaries(raw_diaries, limit=limit, order=args.order)
    print(f"Selected {len(selected_diaries)} diaries from {len(raw_diaries)} available.")

    print("Fetching full diary content...")
    full_diaries = client.fetch_full_diaries(
        selected_diaries,
        fallback_user_id=user_id,
        batch_size=max(1, args.batch_size),
        decrypt_privacy=not args.no_decrypt_privacy,
    )
    full_diaries = choose_diaries(full_diaries, limit=None, order="oldest")

    image_plan = build_image_plan(full_diaries, raw_images, user_id)
    image_results = download_images(
        client,
        vault,
        image_plan,
        enabled=not args.no_images,
        fallback_user_id=user_id,
        reuse_existing=False,
    )
    privacy = summarize_privacy(full_diaries)

    image_exts = {int(k): v for k, v in image_results["image_exts"].items()}
    archive = build_archive(
        raw=raw,
        mode=args.mode,
        user_id=user_id,
        diaries=full_diaries,
        selected_images=raw_images,
        image_plan=image_plan,
        image_results=image_results,
        limit=limit,
    )

    report = {
        "vault": str(vault),
        "mode": args.mode,
        "limit": limit,
        "selected_diary_count": len(selected_diaries),
        "written_diary_count": len(full_diaries),
        "privacy": privacy,
        "image_plan": {key: value for key, value in image_plan.items() if key != "owner_by_id"},
        "image_results": image_results,
        "next_check": [
            "Compare written_diary_count with expected sample/full count.",
            "Open entries Markdown files and verify dates, titles, mood, weather and image refs.",
            "Check failed_images before treating this archive as complete.",
            "If privacy regions exist, verify no ciphertext markers remain in entries.",
        ],
    }

    write_json(vault / "raw" / "sync.json", raw)
    write_json(vault / "raw" / "archive.json", archive)
    write_json(vault / "raw" / "sync-report.json", report)
    written = write_entries(vault, full_diaries, image_exts=image_exts)

    print(f"Wrote archive: {vault / 'raw' / 'archive.json'}")
    print(f"Wrote report:  {vault / 'raw' / 'sync-report.json'}")
    print(f"Wrote entries: {len(written)}")
    print(
        "Images: "
        f"{len(image_results['downloaded_images'])} downloaded, "
        f"{len(image_results['unavailable_images'])} unavailable, "
        f"{len(image_results['failed_images'])} failed."
    )
    if privacy["found_count"]:
        print(
            "Privacy regions: "
            f"{privacy['decrypted_count']} decrypted, "
            f"{privacy['failed_count']} failed."
        )
    return 0 if not image_results["failed_images"] else 1


def run_daily(args: argparse.Namespace) -> int:
    vault = init_vault(args.vault)
    archive_path = vault / "raw" / "archive.json"
    if not archive_path.exists():
        raise NiderijiError("daily sync requires an existing raw/archive.json; run sync or import-zip first")

    existing_archive = read_json(archive_path)
    if not isinstance(existing_archive, dict):
        raise NiderijiError("raw/archive.json is not a JSON object")
    existing_meta = existing_archive.get("meta") if isinstance(existing_archive.get("meta"), dict) else {}
    existing_mode = existing_meta.get("export_mode")
    if existing_mode and existing_mode != args.mode:
        raise NiderijiError(f"existing archive mode is {existing_mode}; rerun daily with --mode {existing_mode}")
    existing_diaries = existing_archive.get("diaries")
    if not isinstance(existing_diaries, list):
        raise NiderijiError("raw/archive.json does not contain a diaries list")

    client = make_client(args)
    print("Fetching sync metadata...")
    raw = client.sync()
    user_id = client.user_id or args.user_id or _env_int("NIDERIJI_USER_ID") or infer_user_id(raw)
    if not user_id:
        raise NiderijiError("could not infer user id; set --user-id or NIDERIJI_USER_ID")
    client.user_id = user_id

    raw_diaries, raw_images = select_raw(raw, args.mode)
    recent_diaries = choose_recent_diaries(raw_diaries, days=args.days)
    print(f"Refreshing {len(recent_diaries)} recent diaries from {len(raw_diaries)} available.")

    if recent_diaries:
        print("Fetching recent full diary content...")
        updates = client.fetch_full_diaries(
            recent_diaries,
            fallback_user_id=user_id,
            batch_size=max(1, args.batch_size),
            decrypt_privacy=not args.no_decrypt_privacy,
        )
    else:
        updates = []
    merged_diaries = merge_diaries(existing_diaries, updates)

    image_plan = build_image_plan(merged_diaries, raw_images, user_id)
    image_results = download_images(
        client,
        vault,
        image_plan,
        enabled=not args.no_images,
        fallback_user_id=user_id,
        reuse_existing=True,
    )
    privacy = summarize_privacy(updates)
    image_exts = {int(k): v for k, v in image_results["image_exts"].items()}

    archive = build_archive(
        raw=raw,
        mode=args.mode,
        user_id=user_id,
        diaries=merged_diaries,
        selected_images=raw_images,
        image_plan=image_plan,
        image_results=image_results,
        limit=None,
    )
    report = {
        "vault": str(vault),
        "mode": args.mode,
        "days": args.days,
        "raw_diary_count": len(raw_diaries),
        "existing_diary_count": len(existing_diaries),
        "recent_diary_count": len(recent_diaries),
        "updated_diary_count": len(updates),
        "merged_diary_count": len(merged_diaries),
        "privacy": privacy,
        "image_plan": {key: value for key, value in image_plan.items() if key != "owner_by_id"},
        "image_results": image_results,
    }

    write_json(vault / "raw" / "sync.json", raw)
    write_json(vault / "raw" / "archive.json", archive)
    write_json(vault / "raw" / "daily-report.json", report)
    write_json(vault / "raw" / "sync-report.json", report)
    written = write_entries(vault, merged_diaries, image_exts=image_exts)

    print(f"Wrote archive: {vault / 'raw' / 'archive.json'}")
    print(f"Wrote report:  {vault / 'raw' / 'daily-report.json'}")
    print(f"Wrote entries: {len(written)}")
    print(
        "Images: "
        f"{len(image_results['reused_images'])} reused, "
        f"{len(image_results['downloaded_images'])} downloaded, "
        f"{len(image_results['unavailable_images'])} unavailable, "
        f"{len(image_results['failed_images'])} failed."
    )
    return 0 if not image_results["failed_images"] else 1


def run_import_zip(args: argparse.Namespace) -> int:
    report = import_archive_zip(args.zip_path, args.vault, replace=args.replace)
    print(f"Imported archive: {report['diary_count']} diaries, {report['image_count']} images")
    print(f"Wrote entries:    {report['written_entry_count']}")
    print(f"Wrote archive:    {report['archive_target']}")
    return 0


def run_index(args: argparse.Namespace) -> int:
    report = index_vault(args.vault, db_path=args.db_path)
    print(f"Wrote database: {report['db_path']}")
    print(f"Diaries:        {report['diary_count']}")
    print(f"Images:         {report['image_file_count']} files / {report['image_row_count']} rows")
    print(f"FTS:            {report['fts_tokenizer'] or 'disabled'}")
    print(f"Semantic kept:  {report.get('semantic_vectors_restored', 0)}")
    return 0


def run_semantic_index(args: argparse.Namespace) -> int:
    try:
        report = index_semantic_vectors(
            args.vault,
            db_path=args.db_path,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            batch_size=args.batch_size,
            limit=args.limit,
            force=args.force,
            timeout=args.timeout,
        )
    except SemanticEmbeddingError as exc:
        if args.skip_if_unavailable:
            print(f"WARN: semantic index skipped: {exc}")
            return 0
        raise

    if args.json:
        _print_json(report)
        return 0

    print(f"Semantic provider: {report['provider']}")
    print(f"Semantic model:    {report['model']}")
    print(f"Chunks:            {report['total_chunks']}")
    print(f"Pending before:    {report['pending_before']}")
    print(f"Embedded:          {report['embedded']}")
    print(f"Semantic vectors:  {report['semantic_vectors']}")
    print(f"Semantic dim:      {report['semantic_dim'] or '-'}")
    return 0


def run_search(args: argparse.Namespace) -> int:
    report = search_vault(
        args.vault,
        args.query,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
        order=args.order,
        db_path=args.db_path,
    )
    if args.json:
        _print_json(report)
        return 0

    query_label = f'"{report["query"]}"' if report["query"] else "(date listing)"
    print(f"Search: {query_label}")
    print(f"Results: {report['count']}  Method: {report['method']}")
    for item in report["results"]:
        title = _console_text(item["title"] or "(untitled)")
        print(f"- {item['createddate']} #{item['diary_id']} {title}")
        tags = _console_text(" | ".join(value for value in (item["weather"], item["mood"], item["space"]) if value))
        if tags:
            print(f"  {tags}")
        if item["excerpt"]:
            print(f"  {_console_text(item['excerpt'])}")
        print(f"  {item['entry_path']}")
    return 0


def run_recall(args: argparse.Namespace) -> int:
    report = recall_vault(
        args.vault,
        args.query,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
        db_path=args.db_path,
        semantic=args.semantic,
        semantic_provider=args.semantic_provider,
        semantic_model=args.semantic_model,
        semantic_base_url=args.semantic_base_url,
        semantic_min_score=args.semantic_min_score,
        group_by=args.group_by,
    )
    if args.json:
        _print_json(report)
        return 0

    print(f"Recall: {report['query']}")
    print(f"Results: {report['count']}  Method: {report['method']}")
    if report.get("groups"):
        for group in report["groups"]:
            print(f"\n{group['label']} ({group['count']})")
            for item in group["results"]:
                _print_recall_item(item)
    else:
        for item in report["results"]:
            _print_recall_item(item)
    return 0


def _print_recall_item(item: dict[str, Any]) -> None:
    title = _console_text(item["title"] or "(untitled)")
    print(f"- score={item['score']} {item['createddate']} #{item['diary_id']} chunk={item['chunk_index']} {title}")
    if item["text"]:
        print(f"  {_console_text(item['text'])}")
    print(f"  {item['entry_path']}")


def run_stats(args: argparse.Namespace) -> int:
    report = stats_vault(args.vault, db_path=args.db_path, write_report=args.write_report)
    if args.json:
        _print_json(report)
        return 0

    overview = report["overview"]
    print(f"Diaries:        {overview['diary_count']}")
    print(f"Active days:    {overview['active_day_count']}")
    print(f"Date range:     {overview['first_date']} to {overview['last_date']}")
    print(f"Characters:     {overview['total_character_count']}")
    print(f"Average chars:  {overview['average_characters_per_diary']}")
    print(f"Current streak: {overview['current_streak_days']} days")
    print(f"Longest streak: {overview['longest_streak_days']} days")
    for path in report.get("written_reports") or []:
        print(f"Wrote report:   {path}")
    return 0


def run_context(args: argparse.Namespace) -> int:
    report = context_vault(
        args.vault,
        args.query,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
        order=args.order,
        full=args.full,
        max_chars=args.max_chars,
        method=args.method,
        output=args.output,
        db_path=args.db_path,
    )
    if args.json:
        _print_json(report)
        return 0

    print(f"Wrote context: {report['output_path']}")
    print(f"Entries:       {report['count']}")
    print(f"Method:        {report['search_method']}")
    return 0


def run_export(args: argparse.Namespace) -> int:
    report = bundle_vault(
        args.vault,
        output=args.output,
        include_images=not args.no_images,
        include_db=not args.no_db,
        replace=args.replace,
    )
    print(f"Wrote export: {report['output_path']}")
    print(f"Files:        {report['file_count']}")
    print(f"Size bytes:   {report['size_bytes']}")
    return 0


def run_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import create_server
        server = create_server(args.vault, db_path=args.db_path)
    except RuntimeError as exc:
        raise NiderijiError(str(exc)) from exc

    server.run()
    return 0


def run_mcp_http(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import run_streamable_http
    except RuntimeError as exc:
        raise NiderijiError(str(exc)) from exc

    try:
        run_streamable_http(
            args.vault,
            db_path=args.db_path,
            host=args.host,
            port=args.port,
            path=args.path,
            api_token=_api_token(args.api_token, args.api_token_file),
            allow_hosts=args.allow_host,
            allow_origins=args.allow_origin,
            log_level=args.log_level,
        )
    except RuntimeError as exc:
        raise NiderijiError(str(exc)) from exc
    return 0


def run_serve(args: argparse.Namespace) -> int:
    token = _api_token(args.api_token, args.api_token_file)
    serve_api(args.vault, host=args.host, port=args.port, db_path=args.db_path, api_token=token)
    return 0


def run_validate(args: argparse.Namespace) -> int:
    report = validate_vault(args.vault)
    if args.json:
        _print_json(report)
    else:
        status = "ok" if report["ok"] else "failed"
        print(f"Validation: {status}")
        for key, value in report["stats"].items():
            print(f"{key}: {value}")
        for warning in report["warnings"]:
            print(f"WARN: {warning}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
    return 0 if report["ok"] else 1


def make_client(args: argparse.Namespace) -> NiderijiClient:
    if args.secrets_file:
        load_secrets_file(args.secrets_file)

    token = os.environ.get("NIDERIJI_TOKEN")
    user_id = args.user_id or _env_int("NIDERIJI_USER_ID")
    client = NiderijiClient(token=token, user_id=user_id, timeout=args.timeout)
    if token:
        return client

    email = args.email or os.environ.get("NIDERIJI_EMAIL")
    password = os.environ.get("NIDERIJI_PASSWORD")
    if args.secrets_file and (not email or not password):
        raise NiderijiError(
            "secrets file must provide NIDERIJI_EMAIL and NIDERIJI_PASSWORD, "
            "or provide NIDERIJI_TOKEN"
        )

    email = email or input("Nideriji email: ").strip()
    password = password or getpass.getpass("Nideriji password (not stored): ")
    if not email or not password:
        raise NiderijiError("email/password is required when token is not provided")

    print("Logging in...")
    client.login(email, password)
    return client


def download_images(
    client: NiderijiClient,
    vault: Path,
    image_plan: dict[str, Any],
    *,
    enabled: bool,
    fallback_user_id: int,
    reuse_existing: bool = False,
) -> dict[str, Any]:
    results = {
        "reused_images": [],
        "downloaded_images": [],
        "unavailable_images": [],
        "failed_images": [],
        "image_exts": {},
        "images_requested": enabled,
    }
    if not enabled:
        return results

    owner_by_id = image_plan["owner_by_id"]
    image_ids = image_plan["image_ids"]
    print(f"Downloading {len(image_ids)} referenced images...")
    for index, image_id in enumerate(image_ids, start=1):
        owner_id = owner_by_id.get(image_id) or fallback_user_id
        existing_ext = find_image_ext(vault, image_id) if reuse_existing else None
        if existing_ext:
            results["reused_images"].append({"id": image_id, "owner_id": owner_id, "ext": existing_ext})
            results["image_exts"][str(image_id)] = existing_ext
            print(f"Image {index}/{len(image_ids)} reused: {image_id}.{existing_ext}")
            continue
        try:
            image = client.fetch_image(image_id, owner_id)
        except ImageUnavailable as exc:
            results["unavailable_images"].append(
                {"id": image_id, "owner_id": owner_id, "status": exc.status, "size": exc.size}
            )
            print(f"Image {index}/{len(image_ids)} unavailable: {image_id}")
            continue
        except NiderijiError as exc:
            results["failed_images"].append({"id": image_id, "owner_id": owner_id, "error": str(exc)})
            print(f"Image {index}/{len(image_ids)} failed: {image_id}")
            continue

        write_image(vault, image_id, image.ext, image.data)
        results["downloaded_images"].append({"id": image_id, "owner_id": owner_id, "ext": image.ext})
        results["image_exts"][str(image_id)] = image.ext
        print(f"Image {index}/{len(image_ids)} downloaded: {image_id}.{image.ext}")

    return results


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise NiderijiError(f"{name} must be an integer")


def _api_token(value: str | None, file_path: str | None) -> str | None:
    token = value or os.environ.get("DIARYVAULT_API_TOKEN")
    if file_path:
        token = Path(file_path).expanduser().resolve().read_text(encoding="utf-8-sig").strip()
    return token or None


def load_secrets_file(path: str | Path) -> set[str]:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise NiderijiError(f"secrets file not found: {source}")
    loaded: set[str] = set()
    for line_no, raw_line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise NiderijiError(f"{source}:{line_no}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in {"NIDERIJI_EMAIL", "NIDERIJI_PASSWORD", "NIDERIJI_TOKEN", "NIDERIJI_USER_ID"}:
            raise NiderijiError(f"{source}:{line_no}: unsupported secret key {key}")
        if value and key not in os.environ:
            os.environ[key] = value
            loaded.add(key)
    return loaded


def summarize_privacy(diaries: list[dict[str, Any]]) -> dict[str, int | bool]:
    found = decrypted = failed = 0
    crypto_available = True
    for diary in diaries:
        item = diary.get("_privacy") or {}
        found += int(item.get("found_count") or 0)
        decrypted += int(item.get("decrypted_count") or 0)
        failed += int(item.get("failed_count") or 0)
        crypto_available = crypto_available and bool(item.get("crypto_available", True))
    return {
        "found_count": found,
        "decrypted_count": decrypted,
        "failed_count": failed,
        "crypto_available": crypto_available,
    }


def _console_text(value: Any) -> str:
    raw_encoding = getattr(sys.stdout, "encoding", None)
    encoding = raw_encoding if isinstance(raw_encoding, str) else "utf-8"
    encoding = encoding or "utf-8"
    return str(value).encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_json(value: Any) -> None:
    import json

    print(_console_text(json.dumps(value, ensure_ascii=False, indent=2)))


if __name__ == "__main__":
    raise SystemExit(main())
