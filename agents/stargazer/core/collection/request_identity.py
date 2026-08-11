"""从规范化 HTTP 请求指纹派生薄租约 task_id。"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode

# 噪声 / 逐跳头：不参与租约身份（小写比较；前缀匹配见 _is_ignored_header）
_IGNORED_HEADER_EXACT = frozenset(
    {
        "host",
        "connection",
        "keep-alive",
        "proxy-connection",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "content-length",
        "content-type",
        "accept",
        "accept-encoding",
        "user-agent",
        "cookie",
        "x-real-ip",
        "x-request-id",
        "x-task-id",
        "task_id",
    }
)
_IGNORED_HEADER_PREFIXES = ("x-forwarded-",)


def _is_ignored_header(name: str) -> bool:
    lowered = name.lower().strip()
    if lowered in _IGNORED_HEADER_EXACT:
        return True
    return any(lowered.startswith(prefix) for prefix in _IGNORED_HEADER_PREFIXES)


def canonicalize_headers(headers: Mapping[str, Any] | None) -> str:
    """name 小写、按 name 排序；同名多值按出现顺序用 ``\\x1f`` 拼接。"""
    if not headers:
        return ""

    grouped: dict[str, list[str]] = {}
    items: Iterable[tuple[Any, Any]]
    getall = getattr(headers, "getall", None)
    if callable(getall):
        # Sanic Header / multidict：按 unique name 取全部值
        names = sorted({str(name).lower().strip() for name in headers.keys()})
        for name in names:
            if _is_ignored_header(name):
                continue
            values = getall(name, [])
            if not values:
                # 某些实现键大小写与 getall 不一致，回退单值
                raw = headers.get(name)
                if raw is None:
                    continue
                values = [raw]
            grouped[name] = [str(v) for v in values]
    else:
        for raw_name, raw_value in headers.items():
            name = str(raw_name).lower().strip()
            if _is_ignored_header(name):
                continue
            if isinstance(raw_value, (list, tuple)):
                grouped.setdefault(name, []).extend(str(v) for v in raw_value)
            else:
                grouped.setdefault(name, []).append(str(raw_value))

    lines = []
    for name in sorted(grouped):
        lines.append(f"{name}:{chr(0x1F).join(grouped[name])}")
    return "\n".join(lines)


def canonicalize_query(query: str | Mapping[str, Any] | None) -> str:
    """按 key 排序；同 key 多值按值排序后稳定编码。"""
    if query is None:
        return ""

    pairs: list[tuple[str, str]] = []
    if isinstance(query, Mapping):
        getlist = getattr(query, "getlist", None)
        if callable(getlist):
            for key in query.keys():
                values = getlist(key)
                for value in values:
                    pairs.append((str(key), str(value)))
        else:
            for key, value in query.items():
                if isinstance(value, (list, tuple)):
                    for item in value:
                        pairs.append((str(key), str(item)))
                else:
                    pairs.append((str(key), str(value)))
    else:
        query_str = str(query).lstrip("?")
        if not query_str:
            return ""
        pairs = [(k, v) for k, v in parse_qsl(query_str, keep_blank_values=True)]

    pairs.sort(key=lambda item: (item[0], item[1]))
    return urlencode(pairs, doseq=True)


def build_request_task_id(
    method: str,
    path: str,
    query: str | Mapping[str, Any] | None = None,
    headers: Mapping[str, Any] | None = None,
) -> str:
    """METHOD + path + canonical query + canonical headers → ``req_<sha256>``。"""
    material = "\n".join(
        [
            str(method or "GET").upper().strip(),
            str(path or "").strip() or "/",
            canonicalize_query(query),
            canonicalize_headers(headers),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"req_{digest}"


def build_request_task_id_from_request(request: Any) -> str:
    """从 Sanic Request（或同形状对象）派生租约 ID。"""
    query = getattr(request, "query_string", None)
    if query is None:
        query = getattr(request, "args", None)
    return build_request_task_id(
        method=getattr(request, "method", "GET") or "GET",
        path=getattr(request, "path", None)
        or getattr(request, "path_qs", None)
        or "/",
        query=query,
        headers=getattr(request, "headers", None) or {},
    )
