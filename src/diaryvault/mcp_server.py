from __future__ import annotations

import os
import hmac
from pathlib import Path
from typing import Any

from .client import NiderijiError
from .core import (
    get_diary as core_get_diary,
    get_recent_diaries as core_get_recent_diaries,
    get_stats as core_get_stats,
    recall_memories as core_recall_memories,
    search_diaries as core_search_diaries,
)


DEFAULT_MCP_HTTP_HOST = "127.0.0.1"
DEFAULT_MCP_HTTP_PORT = 8766
DEFAULT_MCP_HTTP_PATH = "/mcp"

INSTRUCTIONS = (
    "DiaryVault is a private, read-only personal diary memory server. "
    "Use recall_memories for broad memory questions, search_diaries for exact keywords, "
    "get_recent_diaries for recent state, and get_diary only when excerpts are insufficient. "
    "Never claim diary evidence without using a DiaryVault tool result."
)


def create_server(
    vault: str | Path | None = None,
    *,
    db_path: str | Path | None = None,
    log_level: str = "WARNING",
):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("MCP support is not installed. Run: pip install -e .[mcp]") from exc

    root = Path(vault or os.environ.get("DIARYVAULT_VAULT") or "DiaryVault").expanduser().resolve()
    target = Path(db_path or os.environ.get("DIARYVAULT_DB_PATH") or root / "db" / "diaryvault.sqlite").expanduser().resolve()
    mcp = MCPServer(
        "DiaryVault",
        version="0.1.0",
        instructions=INSTRUCTIONS,
        log_level=_mcp_log_level(log_level),
    )

    @mcp.tool()
    def get_stats() -> dict[str, Any]:
        """Return diary archive and vector-index health counts."""
        return core_get_stats(root, db_path=target)

    @mcp.tool()
    def search_diaries(
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Search diary entries by exact keyword or date range."""
        return core_search_diaries(
            query,
            vault=root,
            start_date=start_date,
            end_date=end_date,
            top_k=top_k,
            db_path=target,
        )

    @mcp.tool()
    def recall_memories(
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        top_k: int = 10,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve diary memory excerpts related to a question. Set group_by='year' for time-aware recall."""
        return core_recall_memories(
            query,
            vault=root,
            start_date=start_date,
            end_date=end_date,
            top_k=top_k,
            group_by=group_by,
            db_path=target,
        )

    @mcp.tool()
    def get_diary(diary_id: int, max_chars: int = 5000) -> dict[str, Any]:
        """Read one diary by id with a bounded character limit."""
        return core_get_diary(diary_id, vault=root, max_chars=max_chars, db_path=target)

    @mcp.tool()
    def get_recent_diaries(days: int = 7) -> dict[str, Any]:
        """Return recent diary entries, anchored to the latest diary date in the archive."""
        return core_get_recent_diaries(vault=root, days=days, db_path=target)

    return mcp


def create_streamable_http_app(
    vault: str | Path | None = None,
    *,
    db_path: str | Path | None = None,
    host: str = DEFAULT_MCP_HTTP_HOST,
    port: int = DEFAULT_MCP_HTTP_PORT,
    path: str = DEFAULT_MCP_HTTP_PATH,
    api_token: str | None = None,
    allow_hosts: list[str] | None = None,
    allow_origins: list[str] | None = None,
    log_level: str = "WARNING",
):
    if not _is_local_host(host) and not api_token:
        raise NiderijiError("binding MCP HTTP outside localhost requires --api-token or --api-token-file")

    try:
        from mcp.server.streamable_http import TransportSecuritySettings
    except ImportError as exc:
        raise RuntimeError("MCP support is not installed. Run: pip install -e .[mcp]") from exc

    server = create_server(vault, db_path=db_path, log_level=log_level)
    app = server.streamable_http_app(
        streamable_http_path=path,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(host, port, allow_hosts),
            allowed_origins=_allowed_origins(host, port, allow_origins),
        ),
        host=host,
    )
    if api_token:
        app = BearerAuthMiddleware(app, api_token.strip())
    return app


def run_streamable_http(
    vault: str | Path | None = None,
    *,
    db_path: str | Path | None = None,
    host: str = DEFAULT_MCP_HTTP_HOST,
    port: int = DEFAULT_MCP_HTTP_PORT,
    path: str = DEFAULT_MCP_HTTP_PATH,
    api_token: str | None = None,
    allow_hosts: list[str] | None = None,
    allow_origins: list[str] | None = None,
    log_level: str = "info",
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("MCP HTTP support is not installed. Run: pip install -e .[mcp]") from exc

    app = create_streamable_http_app(
        vault,
        db_path=db_path,
        host=host,
        port=port,
        path=path,
        api_token=api_token,
        allow_hosts=allow_hosts,
        allow_origins=allow_origins,
        log_level=log_level,
    )
    uvicorn.run(app, host=host, port=port, log_level=log_level)


class BearerAuthMiddleware:
    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await _send_plain(send, 204, "")
            return

        authorization = _header(scope, b"authorization")
        expected = f"Bearer {self.token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            await _send_plain(send, 401, "unauthorized", [(b"www-authenticate", b"Bearer")])
            return

        await self.app(scope, receive, send)


def main() -> None:
    create_server().run()


def _is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _mcp_log_level(value: str) -> str:
    level = value.upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return "WARNING"
    return level


def _allowed_hosts(host: str, port: int, extra: list[str] | None) -> list[str]:
    hosts = set(extra or [])
    for item in {host, "127.0.0.1", "localhost", "::1"}:
        hosts.add(item)
        hosts.add(f"{item}:{port}")
    return sorted(hosts)


def _allowed_origins(host: str, port: int, extra: list[str] | None) -> list[str]:
    origins = set(extra or [])
    for item in {host, "127.0.0.1", "localhost"}:
        origins.add(f"http://{item}:{port}")
        origins.add(f"https://{item}:{port}")
    return sorted(origins)


def _header(scope: dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin1")
    return ""


async def _send_plain(send: Any, status: int, text: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = text.encode("utf-8")
    response_headers = [
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    response_headers.extend(headers or [])
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    main()
