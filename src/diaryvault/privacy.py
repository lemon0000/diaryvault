from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

try:
    from Crypto.Cipher import AES
except Exception:  # pragma: no cover - depends on optional dependency
    AES = None


PRIVACY_START = "[以下是隐私区域密文，请不要做任何编辑，否则可能导致解密失败]"
PRIVACY_END = "[以上是隐私日记，请不要编辑密文]"
PRIVACY_PATTERN = re.compile(
    re.escape(PRIVACY_START) + r"(.*?)" + re.escape(PRIVACY_END),
    re.DOTALL,
)


@dataclass
class PrivacyResult:
    content: str
    found_count: int = 0
    decrypted_count: int = 0
    failed_count: int = 0
    crypto_available: bool = AES is not None
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "found_count": self.found_count,
            "decrypted_count": self.decrypted_count,
            "failed_count": self.failed_count,
            "crypto_available": self.crypto_available,
            "failures": self.failures,
        }


def decrypt_privacy_markers(content: str, user_id: int | str | None) -> PrivacyResult:
    matches = list(PRIVACY_PATTERN.finditer(content or ""))
    if not matches:
        return PrivacyResult(content=content or "")

    result = PrivacyResult(content=content or "", found_count=len(matches))
    if AES is None:
        result.failed_count = len(matches)
        result.failures.append("pycryptodome is not installed")
        return result

    def replace(match: re.Match[str]) -> str:
        cipher_text = match.group(1).strip()
        try:
            decrypted = decrypt_payload(cipher_text, user_id)
        except Exception as exc:  # keep ciphertext visible instead of dropping text
            result.failed_count += 1
            result.failures.append(str(exc))
            return match.group(0)
        result.decrypted_count += 1
        return f"[隐私内容开始]\n{decrypted}\n[隐私内容结束]"

    result.content = PRIVACY_PATTERN.sub(replace, result.content)
    return result


def decrypt_payload(cipher_text: str, user_id: int | str | None) -> str:
    if not user_id:
        raise ValueError("missing user_id for privacy decryption")
    if AES is None:
        raise RuntimeError("pycryptodome is not installed")

    payload = _decode_cipher_text(cipher_text)
    if len(payload) % 16 != 0:
        raise ValueError("cipher payload length is not a multiple of 16")

    cipher = AES.new(_aes_key(user_id), AES.MODE_ECB)
    plain = cipher.decrypt(payload)
    plain = _strip_pkcs7_padding(plain)
    return plain.decode("utf-8", errors="strict").strip()


def _aes_key(user_id: int | str) -> bytes:
    key = str(user_id).encode("utf-8")
    if len(key) < 16:
        return key + (b"\0" * (16 - len(key)))
    return key[:16]


def _decode_cipher_text(cipher_text: str) -> bytes:
    compact = "".join((cipher_text or "").split())
    try:
        return base64.b64decode(compact, validate=True)
    except Exception:
        try:
            return bytes.fromhex(compact)
        except Exception as exc:
            raise ValueError("cipher text is neither valid base64 nor hex") from exc


def _strip_pkcs7_padding(value: bytes) -> bytes:
    if not value:
        return value
    pad = value[-1]
    if 1 <= pad <= 16 and value.endswith(bytes([pad]) * pad):
        return value[:-pad]
    return value

