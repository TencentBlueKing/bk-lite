from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from apps.core.utils.safe_requests import safe_request
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.workflow_orchestration.atom_packages.runtime import trusted_organization_id

MAX_BODY_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_URL_LENGTH = 2000
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _bounded_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 20:
        raise ValueError("headers 必须是最多 20 项的对象")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 100 or not isinstance(item, str) or len(item) > 4000:
            raise ValueError("HTTP Header 必须是有界字符串键值")
        if key.casefold() == "host":
            raise ValueError("HTTP 请求不允许覆盖 Host")
        result[key] = item
    return result


def _normalized_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_URL_LENGTH:
        raise ValueError("HTTP URL 必填且最长 2000 字符")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("HTTP URL 必须是 http(s) 绝对地址")
    if parsed.username or parsed.password:
        raise ValueError("HTTP URL 不得包含用户信息")
    try:
        return SSRFValidator.validate(raw)
    except SSRFError as error:
        raise ValueError(str(error)) from error


def _allowed_success_codes(value: Any) -> set[int]:
    if value is None:
        return set()
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("额外成功状态码必须是最多 20 项的数组")
    result: set[int] = set()
    for item in value:
        if isinstance(item, bool):
            raise ValueError("成功状态码必须在 100 到 599 之间")
        try:
            code = int(item)
        except (TypeError, ValueError) as error:
            raise ValueError("成功状态码必须在 100 到 599 之间") from error
        if not 100 <= code <= 599:
            raise ValueError("成功状态码必须在 100 到 599 之间")
        result.add(code)
    return result


def execute_http(
    inputs: dict[str, Any],
    *,
    fixed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call an absolute URL with request-level SSRF and size guards."""
    configured = fixed or {}
    trusted_organization_id(inputs)
    url = _normalized_url(configured.get("url") or inputs.get("url"))
    method = str(configured.get("method") or inputs.get("method") or "GET").upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError("不支持的 HTTP 方法")
    timeout = inputs.get("timeout", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 60:
        raise ValueError("HTTP 超时必须在 1 到 60 秒之间")
    headers = _bounded_headers(inputs.get("headers"))
    query = inputs.get("query")
    if query is not None and (not isinstance(query, dict) or len(query) > 50):
        raise ValueError("query 必须是最多 50 项的对象")
    request_kwargs: dict[str, Any] = {
        "headers": headers,
        "params": query,
        "timeout": timeout,
        "allow_redirects": False,
        "max_redirects": 0,
        "stream": True,
    }
    if "body" in inputs:
        body = inputs["body"]
        if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_BODY_BYTES:
            raise ValueError("HTTP 请求体超过 256 KiB 限额")
        request_kwargs["json"] = body
    response = safe_request(method, url, **request_kwargs)
    try:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_RESPONSE_BYTES:
            raise ValueError("HTTP 响应超过 1 MiB 限额")
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("HTTP 响应超过 1 MiB 限额")
            chunks.append(chunk)
        content = b"".join(chunks)
    finally:
        response.close()
    status_code = int(response.status_code)
    success_status_codes = _allowed_success_codes(inputs.get("success_status_codes"))
    if not 200 <= status_code <= 299 and status_code not in success_status_codes:
        raise ValueError(f"HTTP 响应状态码 {status_code} 不在成功范围内")
    content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
    response_format = str(inputs.get("response_format") or "AUTO").upper()
    if response_format not in {"AUTO", "JSON", "TEXT"}:
        raise ValueError("HTTP 响应格式非法")
    parse_json = response_format == "JSON" or (response_format == "AUTO" and content_type == "application/json")
    if parse_json and content:
        try:
            body = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("HTTP 响应声明为 JSON 但内容无效") from error
    else:
        body = content.decode("utf-8", errors="replace")
    return {
        "status_code": status_code,
        "content_type": content_type,
        "body": body,
        "size": len(content),
    }


# Backward-compatible alias for in-flight imports during rollout.
execute_controlled_http = execute_http
