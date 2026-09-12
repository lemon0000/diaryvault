from __future__ import annotations

import hashlib
import math
import re
from array import array

from .markdown import normalize_content


DEFAULT_VECTOR_DIM = 512


def text_hash(text: str) -> str:
    normalized = normalize_content(text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def chunk_diary_text(title: str, content: str, *, max_chars: int = 700, overlap: int = 80) -> list[str]:
    parts = []
    clean_title = str(title or "").strip()
    if clean_title:
        parts.append(clean_title)
    parts.extend(line.strip() for line in normalize_content(content).splitlines() if line.strip())
    text = "\n".join(parts).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def text_vector(text: str, *, dim: int = DEFAULT_VECTOR_DIM) -> list[float]:
    values = [0.0] * dim
    features = text_features(text)
    if not features:
        return values

    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little", signed=False)
        index = value % dim
        sign = 1.0 if value & (1 << 63) else -1.0
        values[index] += sign

    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        return values
    return [value / norm for value in values]


def encode_vector(values: list[float]) -> bytes:
    return array("f", values).tobytes()


def decode_vector(blob: bytes) -> list[float]:
    values = array("f")
    values.frombytes(blob)
    return list(values)


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def text_features(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", normalize_content(text).casefold())
    if not compact:
        return []

    out: list[str] = []
    for size in (2, 3, 4):
        if len(compact) >= size:
            out.extend(compact[index : index + size] for index in range(0, len(compact) - size + 1))
    if not out:
        out.append(compact)
    out.extend(re.findall(r"[a-z0-9_]{2,}", compact))
    return out
