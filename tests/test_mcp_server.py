from pathlib import Path
from threading import Thread
import socket
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

try:
    import anyio
    import httpx2
    import uvicorn
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
except ImportError:
    anyio = None
    httpx2 = None
    uvicorn = None
    Client = None
    streamable_http_client = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.client import NiderijiError
from diaryvault.index import index_vault
from diaryvault.mcp_server import create_server, create_streamable_http_app
from diaryvault.vault import init_vault, write_json


@unittest.skipIf(Client is None, "mcp optional dependency is not installed")
class McpServerTests(unittest.TestCase):
    def test_mcp_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            assert anyio is not None
            anyio.run(_exercise_server, root)

    def test_streamable_http_mcp_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            assert anyio is not None
            with _http_server(root) as url:
                anyio.run(_exercise_http_server, url, None)

    def test_streamable_http_token_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            assert anyio is not None
            with _http_server(root, api_token="secret") as url:
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(url, timeout=5)
                self.assertEqual(ctx.exception.code, 401)
                ctx.exception.close()

                anyio.run(_exercise_http_server, url, "secret")

    def test_non_local_http_requires_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with self.assertRaises(NiderijiError):
                create_streamable_http_app(root, host="0.0.0.0", port=8766)


async def _exercise_server(root: Path) -> None:
    server = create_server(root)
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "get_stats",
            "search_diaries",
            "recall_memories",
            "get_diary",
            "get_recent_diaries",
        }

        stats = await client.call_tool("get_stats", {})
        assert stats.structured_content["diaries"] == 2
        assert stats.structured_content["unembedded_chunks"] == 0

        search = await client.call_tool("search_diaries", {"query": "work", "top_k": 5})
        assert search.structured_content["results"][0]["diary_id"] == 2

        recall = await client.call_tool("recall_memories", {"query": "work pressure", "top_k": 5, "group_by": "year"})
        assert recall.structured_content["results"][0]["diary_id"] == 2
        assert recall.structured_content["groups"][0]["key"] == "2026"

        diary = await client.call_tool("get_diary", {"diary_id": 2, "max_chars": 10})
        assert diary.structured_content["truncated"] is True

        recent = await client.call_tool("get_recent_diaries", {"days": 1})
        assert [item["diary_id"] for item in recent.structured_content["results"]] == [2]


async def _exercise_http_server(url: str, token: str | None) -> None:
    if token:
        assert httpx2 is not None
        assert streamable_http_client is not None
        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
            async with Client(streamable_http_client(url, http_client=http_client)) as client:
                await _exercise_connected_client(client)
    else:
        async with Client(url) as client:
            await _exercise_connected_client(client)


async def _exercise_connected_client(client: Client) -> None:
    tools = await client.list_tools()
    assert {tool.name for tool in tools.tools} == {
        "get_stats",
        "search_diaries",
        "recall_memories",
        "get_diary",
        "get_recent_diaries",
    }
    stats = await client.call_tool("get_stats", {})
    assert stats.structured_content["diaries"] == 2


class _http_server:
    def __init__(self, root: Path, *, api_token: str | None = None):
        self.root = root
        self.api_token = api_token
        self.port = _free_port()
        self.server = None
        self.thread: Thread | None = None

    def __enter__(self) -> str:
        assert uvicorn is not None
        app = create_streamable_http_app(self.root, host="127.0.0.1", port=self.port, api_token=self.api_token)
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = Thread(target=self.server.run, daemon=True)
        self.thread.start()
        _wait_port("127.0.0.1", self.port)
        return f"http://127.0.0.1:{self.port}/mcp"

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.server is not None
        self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(host: str, port: int) -> None:
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise


def _indexed_fixture(tmp: str) -> Path:
    root = init_vault(tmp)
    write_json(
        root / "raw" / "archive.json",
        {
            "meta": {"user_id": 9, "diary_count": 2},
            "diaries": [
                {
                    "id": 1,
                    "user": 9,
                    "createddate": "2026-09-09",
                    "title": "walk",
                    "content": "sunny walk outside",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "work",
                    "content": "today I recorded work pressure and uncertainty about direction",
                },
            ],
            "images": [],
            "image_ids": [],
            "content_image_ids": [],
            "image_exts": {},
        },
    )
    index_vault(root)
    return root


if __name__ == "__main__":
    unittest.main()
