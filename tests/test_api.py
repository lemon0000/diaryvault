from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diaryvault.api import make_handler
from diaryvault.index import index_vault
from diaryvault.vault import init_vault, write_json


class ApiTests(unittest.TestCase):
    def test_api_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with _server(root) as base:
                health = _get_json(f"{base}/health")
                self.assertTrue(health["ok"])
                self.assertEqual(health["diary_count"], 2)

                spec = _get_json(f"{base}/openapi.json")
                self.assertEqual(spec["openapi"], "3.1.0")
                self.assertIn("/context", spec["paths"])

                search = _get_json(f"{base}/search?q={urllib.parse.quote('工作')}&limit=5")
                self.assertEqual(search["count"], 1)
                self.assertEqual(search["results"][0]["diary_id"], 2)

                recall = _get_json(f"{base}/recall?q={urllib.parse.quote('工作压力')}&limit=5")
                self.assertGreaterEqual(recall["count"], 1)
                self.assertEqual(recall["results"][0]["diary_id"], 2)

                grouped = _get_json(f"{base}/recall?q={urllib.parse.quote('工作压力')}&limit=5&group_by=year")
                self.assertEqual(grouped["group_by"], "year")
                self.assertEqual(grouped["groups"][0]["key"], "2026")

                context = _get_json(f"{base}/context?q={urllib.parse.quote('工作压力')}&limit=5")
                self.assertTrue(context["ok"])
                self.assertIn("DiaryVault context pack", context["text"])

                diary = _get_json(f"{base}/diaries/2")
                self.assertEqual(diary["content"], "今天记录工作压力。")

    def test_api_token_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _indexed_fixture(tmp)
            with _server(root, api_token="secret") as base:
                spec = _get_json(f"{base}/openapi.json", headers={"X-Forwarded-Proto": "https"})
                self.assertEqual(spec["servers"][0]["url"], base.replace("http://", "https://"))
                self.assertIn("bearerAuth", spec["components"]["securitySchemes"])

                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    _get_json(f"{base}/health")
                self.assertEqual(ctx.exception.code, 401)
                ctx.exception.close()

                health = _get_json(f"{base}/health", token="secret")
                self.assertTrue(health["ok"])


class _server:
    def __init__(self, root: Path, *, api_token: str | None = None):
        self.root = root
        self.api_token = api_token
        self.server: ThreadingHTTPServer | None = None
        self.thread: Thread | None = None

    def __enter__(self) -> str:
        handler = make_handler(self.root, api_token=self.api_token)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)


def _get_json(url: str, *, token: str | None = None, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
                    "title": "散步",
                    "content": "天气晴朗，出去散步。",
                },
                {
                    "id": 2,
                    "user": 9,
                    "createddate": "2026-09-10",
                    "title": "工作",
                    "content": "今天记录工作压力。",
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
