from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from .markdown import extract_image_ids, normalize_content
from .privacy import decrypt_privacy_markers


API_ORIGIN = "https://nideriji.cn"
FILE_ORIGIN = "https://f.nideriji.cn"
USER_AGENT = "OhApp/3.6.12 Platform/Android"


class NiderijiError(RuntimeError):
    pass


class NiderijiApiError(NiderijiError):
    pass


class NiderijiHttpError(NiderijiError):
    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class ImageUnavailable(NiderijiError):
    def __init__(self, image_id: int, *, status: int | None = None, size: int = 0):
        super().__init__(f"image {image_id} is unavailable")
        self.image_id = image_id
        self.status = status
        self.size = size


@dataclass
class ImageBlob:
    image_id: int
    data: bytes
    content_type: str
    ext: str


class NiderijiClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        user_id: int | None = None,
        timeout: int = 30,
        retries: int = 3,
    ) -> None:
        self.token = token
        self.user_id = user_id
        self.timeout = timeout
        self.retries = retries

    def login(self, email: str, password: str) -> None:
        payload = self._post_json(
            f"{API_ORIGIN}/api/login/",
            {"email": email, "password": password},
            auth=False,
            context="login",
        )
        self._raise_for_api_error(payload, "login")
        token = payload.get("token")
        user_id = payload.get("userid") or payload.get("user_id")
        if not token or not user_id:
            raise NiderijiApiError("login succeeded but token/user id was missing")
        self.token = str(token)
        self.user_id = int(user_id)

    def sync(self) -> dict[str, Any]:
        payload = self._post_json(
            f"{API_ORIGIN}/api/v2/sync/",
            {
                "user_config_ts": "0",
                "diaries_ts": "0",
                "readmark_ts": "0",
                "images_ts": "0",
            },
            auth=True,
            context="sync",
        )
        self._raise_for_api_error(payload, "sync")
        return payload

    def fetch_full_diaries(
        self,
        diary_refs: Iterable[dict[str, Any]],
        *,
        fallback_user_id: int,
        batch_size: int = 50,
        decrypt_privacy: bool = True,
    ) -> list[dict[str, Any]]:
        groups: dict[int, list[int]] = {}
        for diary in diary_refs:
            diary_id = _as_int(diary.get("id"))
            if not diary_id:
                continue
            owner_id = _as_int(diary.get("user") or diary.get("user_id") or fallback_user_id)
            groups.setdefault(owner_id, []).append(diary_id)

        full: list[dict[str, Any]] = []
        for owner_id, ids in groups.items():
            for batch in _chunks(ids, batch_size):
                payload = self._post_json(
                    f"{API_ORIGIN}/api/diary/all_by_ids/{owner_id}/",
                    {"diary_ids": ",".join(str(item) for item in batch)},
                    auth=True,
                    context=f"full diaries for user {owner_id}",
                )
                self._raise_for_api_error(payload, f"full diaries for user {owner_id}")
                for item in payload.get("diaries") or []:
                    full.append(self._normalize_diary(item, owner_id, decrypt_privacy))
        return full

    def fetch_image(self, image_id: int, owner_id: int) -> ImageBlob:
        url = f"{FILE_ORIGIN}/api/image/{owner_id}/{image_id}/"
        body, content_type, status = self._get_bytes(url, auth=True, context=f"image {image_id}")
        if status in (404, 410) or len(body) < 1000:
            raise ImageUnavailable(image_id, status=status, size=len(body))
        ext = detect_image_extension(body, content_type)
        return ImageBlob(image_id=image_id, data=body, content_type=content_type, ext=ext)

    def _normalize_diary(
        self,
        diary: dict[str, Any],
        owner_id: int,
        decrypt_privacy: bool,
    ) -> dict[str, Any]:
        out = dict(diary)
        content = normalize_content(out.get("content"))
        if decrypt_privacy:
            privacy = decrypt_privacy_markers(content, owner_id)
            content = privacy.content
            out["_privacy"] = privacy.as_dict()
        out["content"] = content
        out["image_ids"] = extract_image_ids(content)
        return out

    def _post_json(
        self,
        url: str,
        form: dict[str, str],
        *,
        auth: bool,
        context: str,
    ) -> dict[str, Any]:
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers = self._headers(auth=auth)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        data = self._open_with_retries(request, context=context).decode("utf-8")
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise NiderijiApiError(f"{context}: response was not JSON") from exc
        if not isinstance(payload, dict):
            raise NiderijiApiError(f"{context}: response JSON was not an object")
        return payload

    def _get_bytes(self, url: str, *, auth: bool, context: str) -> tuple[bytes, str, int]:
        request = urllib.request.Request(url, headers=self._headers(auth=auth), method="GET")
        return self._open_with_retries(request, context=context, return_meta=True)

    def _open_with_retries(
        self,
        request: urllib.request.Request,
        *,
        context: str,
        return_meta: bool = False,
    ):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    content_type = response.headers.get("content-type", "")
                    status = response.status
                    if return_meta:
                        return body, content_type, status
                    return body
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if return_meta and exc.code in (404, 410):
                    return body.encode("utf-8"), exc.headers.get("content-type", ""), exc.code
                last_error = NiderijiHttpError(
                    f"{context}: HTTP {exc.code}",
                    status=exc.code,
                    body=body,
                )
                if not _retryable_http(exc.code) or attempt >= self.retries:
                    raise last_error
            except urllib.error.URLError as exc:
                last_error = NiderijiHttpError(f"{context}: network error {exc.reason}")
                if attempt >= self.retries:
                    raise last_error

            time.sleep(min(6.0, 0.4 * (2**attempt)))

        raise last_error or NiderijiHttpError(f"{context}: request failed")

    def _headers(self, *, auth: bool) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT}
        if auth:
            if not self.token:
                raise NiderijiApiError("missing Nideriji token")
            headers["auth"] = f"token {self.token}"
        return headers

    @staticmethod
    def _raise_for_api_error(payload: dict[str, Any], context: str) -> None:
        if payload.get("error") not in (None, 0):
            raise NiderijiApiError(f"{context}: API returned error {payload.get('error')}: {payload}")


def detect_image_extension(data: bytes, content_type: str = "") -> str:
    content_type = (content_type or "").lower()
    if "png" in content_type or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if "webp" in content_type or (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        return "webp"
    if "gif" in content_type or data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return "jpg"


def _retryable_http(status: int) -> bool:
    return status == 429 or status >= 500


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

