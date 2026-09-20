from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import quote, urlparse

OUTCOME_RESOLVED = "resolved"
OUTCOME_MISSING_RELEASE = "missing_release"
OUTCOME_MISSING_ARTIFACT = "missing_artifact"
OUTCOME_INVALID = "invalid_map"
OUTCOME_UNMAPPED = "unmapped_position"

_MAX_EXPANDED = 32 << 20
_MAX_UPLOAD = 8 << 20
_BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_ASSET_DOMAIN = "weops-rum-asset-v1"
_TOKEN_DOMAIN = b"weops-rum-sourcemap-token-v1\x00"


def asset_fingerprint(raw: str) -> str:
    trimmed = (raw or "").strip()
    if not trimmed or any(ch in trimmed for ch in ("\x00", "\r", "\n", "\\")):
        return ""
    try:
        parsed = urlparse(trimmed)
    except ValueError:
        return ""
    if parsed.username or parsed.password:
        return ""
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return ""
    for segment in parsed.path.split("/"):
        if segment in {".", ".."}:
            return ""
    path = quote(parsed.path, safe="/%")
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    if path == "/" or path.endswith("/"):
        return ""
    digest = hashlib.sha256(f"{_ASSET_DOMAIN}\x00{path}".encode("utf-8")).digest()
    return "asset:" + digest[:16].hex()


def new_sourcemap_token() -> tuple[str, str]:
    raw = secrets.token_bytes(32)
    token = "rumsm_" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return token, sourcemap_token_digest(token)


def sourcemap_token_digest(token: str) -> str:
    digest = hashlib.sha256(_TOKEN_DOMAIN + token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_sourcemap_token(token: str, digest: str) -> bool:
    if not token or not digest:
        return False
    return hmac.compare_digest(sourcemap_token_digest(token), digest)


def decode_sourcemap(content: bytes) -> bytes:
    if not content:
        raise ValueError("empty sourcemap")
    if len(content) >= 2 and content[0] == 0x1F and content[1] == 0x8B:
        with gzip.GzipFile(fileobj=__import__("io").BytesIO(content)) as reader:
            expanded = reader.read(_MAX_EXPANDED + 1)
        if len(expanded) > _MAX_EXPANDED:
            raise ValueError("sourcemap exceeds expanded size limit")
        return expanded
    if len(content) > _MAX_EXPANDED:
        raise ValueError("sourcemap exceeds expanded size limit")
    return content


def validate_sourcemap(content: bytes) -> bytes:
    decoded = decode_sourcemap(content)
    try:
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid sourcemap") from exc
    if not isinstance(payload, dict) or "mappings" not in payload:
        raise ValueError("invalid sourcemap")
    return decoded


def parse_frames(raw: Any) -> list[dict]:
    if isinstance(raw, (bytes, bytearray)):
        raw = json.loads(raw.decode("utf-8"))
    elif isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("frames must be an array")
    frames: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid frame")
        file_name = (item.get("file") or item.get("filename") or "").strip()
        function_name = (item.get("functionName") or item.get("function") or "").strip()
        frames.append(
            {
                "file": file_name,
                "functionName": function_name,
                "line": int(item.get("line") or 0),
                "column": int(item.get("column") or 0),
                "resolved": False,
            }
        )
    return frames


def _vlq_decode(segment: str) -> list[int]:
    values: list[int] = []
    value = 0
    shift = 0
    for ch in segment:
        digit = _BASE64.find(ch)
        if digit < 0:
            raise ValueError("invalid VLQ")
        has_continuation = digit & 32
        digit &= 31
        value += digit << shift
        if has_continuation:
            shift += 5
            continue
        negate = value & 1
        value >>= 1
        values.append(-value if negate else value)
        value = 0
        shift = 0
    return values


def _lookup(consumer: dict, line: int, column: int) -> tuple[str, str, int, int] | None:
    column0 = column - 1
    mappings = consumer.get("mappings") or ""
    sources = consumer.get("sources") or []
    names = consumer.get("names") or []
    gen_line = 1
    gen_col = 0
    src_index = 0
    src_line = 0
    src_col = 0
    name_index = 0
    best = None
    for line_map in mappings.split(";"):
        gen_col = 0
        if not line_map:
            gen_line += 1
            continue
        for segment in line_map.split(","):
            if not segment:
                continue
            vals = _vlq_decode(segment)
            if not vals:
                continue
            gen_col += vals[0]
            if len(vals) > 1:
                src_index += vals[1]
                src_line += vals[2]
                src_col += vals[3]
                if len(vals) > 4:
                    name_index += vals[4]
            if gen_line == line and gen_col <= column0:
                source = sources[src_index] if 0 <= src_index < len(sources) else ""
                name = names[name_index] if 0 <= name_index < len(names) and len(vals) > 4 else ""
                best = (source, name, src_line + 1, src_col)
            if gen_line == line and gen_col > column0:
                return best
        if gen_line == line:
            return best
        gen_line += 1
    return best if gen_line - 1 == line else None


def restore_frames(frames_raw: Any, content: bytes, sourcemap_id: str = "") -> dict:
    frames = parse_frames(frames_raw)
    result = {
        "frames": frames,
        "anyResolved": False,
        "outcome": OUTCOME_UNMAPPED,
        "sourcemapId": sourcemap_id or None,
    }
    try:
        decoded = decode_sourcemap(content)
        consumer = json.loads(decoded.decode("utf-8"))
        if not isinstance(consumer, dict) or "mappings" not in consumer:
            raise ValueError("invalid map")
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        result["outcome"] = OUTCOME_INVALID
        if not sourcemap_id:
            result.pop("sourcemapId", None)
        return result

    for index, frame in enumerate(frames):
        if frame["line"] <= 0 or frame["column"] <= 0:
            continue
        hit = _lookup(consumer, frame["line"], frame["column"])
        if not hit:
            continue
        source, name, line, column = hit
        frames[index] = {
            "file": source or frame["file"],
            "functionName": name or frame["functionName"],
            "line": line,
            "column": column,
            "resolved": True,
        }
        result["anyResolved"] = True
    if result["anyResolved"]:
        result["outcome"] = OUTCOME_RESOLVED
    if not sourcemap_id:
        result.pop("sourcemapId", None)
    return result
