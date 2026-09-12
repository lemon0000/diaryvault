from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .client import NiderijiError
from .core import build_memory_context, get_diary, get_index_health, get_stats, recall_memories, search_diaries
from .index import DEFAULT_DB_NAME


DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8765


def serve_api(
    vault: str | Path,
    *,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    db_path: str | Path | None = None,
    api_token: str | None = None,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not api_token:
        raise NiderijiError("binding outside localhost requires --api-token or DIARYVAULT_API_TOKEN")
    handler = make_handler(vault, db_path=db_path, api_token=api_token)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        print(f"DiaryVault API listening on http://{host}:{port}")
        server.serve_forever()
    finally:
        server.server_close()


def make_handler(
    vault: str | Path,
    *,
    db_path: str | Path | None = None,
    api_token: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    root = Path(vault).expanduser().resolve()
    target = Path(db_path).expanduser().resolve() if db_path else root / "db" / DEFAULT_DB_NAME

    class DiaryVaultHandler(BaseHTTPRequestHandler):
        server_version = "DiaryVaultAPI/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query, keep_blank_values=True)

            if parsed.path == "/openapi.json":
                self._json(
                    _openapi_spec(
                        self.headers.get("Host") or f"127.0.0.1:{DEFAULT_API_PORT}",
                        scheme=_request_scheme(self.headers.get("X-Forwarded-Proto")),
                        requires_auth=bool(api_token),
                    )
                )
                return

            if not _authorized(self.headers.get("Authorization"), api_token):
                self._json({"ok": False, "error": "unauthorized"}, status=401)
                return

            try:
                if parsed.path == "/health":
                    self._json(_health(target))
                    return
                if parsed.path == "/stats":
                    self._json(get_stats(root, db_path=target))
                    return
                if parsed.path == "/search":
                    self._json(
                        search_diaries(
                            _param(params, "q"),
                            vault=root,
                            start_date=_param(params, "from") or None,
                            end_date=_param(params, "to") or None,
                            top_k=_int_param(params, "limit", 20),
                            order=_param(params, "order") or "newest",
                            db_path=target,
                        )
                    )
                    return
                if parsed.path == "/recall":
                    self._json(
                        recall_memories(
                            _required_param(params, "q"),
                            vault=root,
                            start_date=_param(params, "from") or None,
                            end_date=_param(params, "to") or None,
                            top_k=_int_param(params, "limit", 12),
                            group_by=_param(params, "group_by") or None,
                            db_path=target,
                        )
                    )
                    return
                if parsed.path == "/context":
                    self._json(
                        build_memory_context(
                            _required_param(params, "q"),
                            vault=root,
                            start_date=_param(params, "from") or None,
                            end_date=_param(params, "to") or None,
                            top_k=_int_param(params, "limit", 12),
                            full=_bool_param(params, "full", False),
                            max_chars=_int_param(params, "max_chars", 1200),
                            method=_param(params, "method") or "recall",
                            db_path=target,
                        )
                    )
                    return
                if parsed.path.startswith("/diaries/"):
                    diary_id = _path_int(parsed.path.removeprefix("/diaries/"))
                    self._json(
                        get_diary(
                            diary_id,
                            vault=root,
                            user_id=_optional_int_param(params, "user_id"),
                            max_chars=_int_param(params, "max_chars", 5000),
                            db_path=target,
                        )
                    )
                    return
                self._json({"ok": False, "error": "not found"}, status=404)
            except NiderijiError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, value: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DiaryVaultHandler


def _health(db_path: Path) -> dict[str, Any]:
    try:
        health = get_index_health(db_path.parent.parent, db_path=db_path)
    except NiderijiError as exc:
        return {"ok": False, "db_path": str(db_path), "error": str(exc)}
    return {
        "ok": True,
        "db_path": str(db_path),
        "diary_count": health["diaries"],
        "chunk_count": health["chunks"],
        "vector_count": health["vectors"],
        "unembedded_chunks": health["unembedded_chunks"],
    }


def _openapi_spec(host: str, *, scheme: str = "http", requires_auth: bool = False) -> dict[str, Any]:
    server_url = f"{scheme}://{host}"
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "DiaryVault Memory API",
            "version": "0.1.0",
            "description": "Private local memory API for searching and retrieving DiaryVault entries.",
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/health": {
                "get": {
                    "operationId": "health",
                    "summary": "Check DiaryVault API health and index counts.",
                    "responses": {"200": {"description": "Health status"}},
                }
            },
            "/stats": {
                "get": {
                    "operationId": "getStats",
                    "summary": "Get writing statistics for the diary archive.",
                    "responses": {"200": {"description": "Diary statistics"}},
                }
            },
            "/search": {
                "get": {
                    "operationId": "searchDiaries",
                    "summary": "Search diary entries by exact keyword or date range.",
                    "parameters": [
                        _query_param("q", "Keyword or phrase. Leave empty to list by date.", required=False),
                        _query_param("from", "Start date in YYYY-MM-DD.", required=False),
                        _query_param("to", "End date in YYYY-MM-DD.", required=False),
                        _query_param("limit", "Maximum result count.", schema_type="integer", required=False),
                        _query_param("order", "newest or oldest.", required=False),
                    ],
                    "responses": {"200": {"description": "Search results"}},
                }
            },
            "/recall": {
                "get": {
                    "operationId": "recallDiaryChunks",
                    "summary": "Retrieve similar diary chunks with the local vector index.",
                    "parameters": [
                        _query_param("q", "Question or phrase to recall related diary chunks.", required=True),
                        _query_param("from", "Start date in YYYY-MM-DD.", required=False),
                        _query_param("to", "End date in YYYY-MM-DD.", required=False),
                        _query_param("limit", "Maximum result count.", schema_type="integer", required=False),
                        _query_param("group_by", "Optional result grouping. Currently supports year.", required=False),
                    ],
                    "responses": {"200": {"description": "Recall results"}},
                }
            },
            "/context": {
                "get": {
                    "operationId": "buildContext",
                    "summary": "Build a model-readable context pack from diary search or recall results.",
                    "parameters": [
                        _query_param("q", "Question or phrase for context retrieval.", required=True),
                        _query_param("from", "Start date in YYYY-MM-DD.", required=False),
                        _query_param("to", "End date in YYYY-MM-DD.", required=False),
                        _query_param("limit", "Maximum result count.", schema_type="integer", required=False),
                        _query_param("full", "Whether to include longer entry text.", schema_type="boolean", required=False),
                        _query_param("max_chars", "Maximum characters per full entry.", schema_type="integer", required=False),
                        _query_param("method", "recall or search.", required=False),
                    ],
                    "responses": {"200": {"description": "Context pack"}},
                }
            },
            "/diaries/{diary_id}": {
                "get": {
                    "operationId": "getDiary",
                    "summary": "Get one full diary entry by diary id.",
                    "parameters": [
                        {
                            "name": "diary_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Diary id.",
                        },
                        _query_param("user_id", "Optional user id when ids may overlap.", schema_type="integer", required=False),
                    ],
                    "responses": {"200": {"description": "Full diary entry"}},
                }
            },
        },
    }
    if requires_auth:
        spec["components"] = {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            }
        }
        spec["security"] = [{"bearerAuth": []}]
    return spec


def _query_param(name: str, description: str, *, schema_type: str = "string", required: bool) -> dict[str, Any]:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "schema": {"type": schema_type},
        "description": description,
    }


def _authorized(header: str | None, token: str | None) -> bool:
    if not token:
        return True
    return header == f"Bearer {token}"


def _request_scheme(forwarded_proto: str | None) -> str:
    if not forwarded_proto:
        return "http"
    scheme = forwarded_proto.split(",", 1)[0].strip().lower()
    if scheme in {"http", "https"}:
        return scheme
    return "http"


def _param(params: dict[str, list[str]], name: str) -> str:
    values = params.get(name) or []
    return values[0].strip() if values else ""


def _required_param(params: dict[str, list[str]], name: str) -> str:
    value = _param(params, name)
    if not value:
        raise ValueError(f"missing required query parameter: {name}")
    return value


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _param(params, name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_int_param(params: dict[str, list[str]], name: str) -> int | None:
    value = _param(params, name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _bool_param(params: dict[str, list[str]], name: str, default: bool) -> bool:
    value = _param(params, name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _path_int(value: str) -> int:
    if not value.isdigit():
        raise ValueError("diary id must be an integer")
    return int(value)
