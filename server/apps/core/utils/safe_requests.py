"""
安全 HTTP 请求封装

特性：
1. 自动 SSRF 校验
2. 重定向目标校验
3. 请求日志记录

使用方式：
    from apps.core.utils.safe_requests import safe_get, safe_post

    response = safe_get("https://example.com/api")
    response = safe_post("https://example.com/api", json={"key": "value"})
"""

from collections.abc import Iterable, Mapping
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from requests import Response
from requests.exceptions import UnrewindableBodyError

from apps.core.logger import logger
from apps.core.utils.egress_gateway import get_egress_gateway
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator, ValidatedTarget


class SafeRequestsError(Exception):
    """安全请求错误"""

    pass


def _should_strip_credentials(current_url: str, redirect_url: str) -> bool:
    """Match requests' auth boundary, including its compatible HTTP-to-HTTPS upgrade."""
    current = urlparse(current_url)
    redirect = urlparse(redirect_url)
    if current.hostname != redirect.hostname:
        return True
    if (
        current.scheme == "http"
        and current.port in (80, None)
        and redirect.scheme == "https"
        and redirect.port in (443, None)
    ):
        return False

    changed_port = current.port != redirect.port
    changed_scheme = current.scheme != redirect.scheme
    default_port = ({"http": 80, "https": 443}.get(current.scheme), None)
    if not changed_scheme and current.port in default_port and redirect.port in default_port:
        return False
    return changed_port or changed_scheme


def _without_headers(headers: dict[str, Any], names: set[str]) -> dict[str, Any]:
    blocked = {name.lower() for name in names}
    return {name: value for name, value in headers.items() if name.lower() not in blocked}


def _iter_request_body_streams(kwargs: dict[str, Any]):
    data = kwargs.get("data")
    if hasattr(data, "read") or (
        isinstance(data, Iterable) and not isinstance(data, (str, bytes, list, tuple, Mapping))
    ):
        yield data

    files = kwargs.get("files")
    if not files:
        return
    file_values = files.values() if isinstance(files, Mapping) else (value for _, value in files)
    for file_value in file_values:
        payload = file_value[1] if isinstance(file_value, (tuple, list)) and len(file_value) > 1 else file_value
        if hasattr(payload, "read"):
            yield payload


def _capture_request_body_positions(kwargs: dict[str, Any]) -> list[tuple[Any, int | None]]:
    positions = []
    seen = set()
    for stream in _iter_request_body_streams(kwargs):
        if id(stream) in seen:
            continue
        seen.add(id(stream))
        try:
            position = stream.tell() if callable(getattr(stream, "tell", None)) else None
        except (OSError, ValueError):
            position = None
        if not callable(getattr(stream, "seek", None)):
            position = None
        positions.append((stream, position))
    return positions


def _rewind_request_body(
    kwargs: dict[str, Any],
    positions: list[tuple[Any, int | None]],
) -> None:
    if not any(key in kwargs for key in ("data", "files")):
        return
    for stream, position in positions:
        if position is None:
            raise UnrewindableBodyError("重定向请求体不可回卷")
        try:
            stream.seek(position)
        except (OSError, ValueError) as exc:
            raise UnrewindableBodyError("重定向请求体回卷失败") from exc


def _prepare_redirect_request(
    method: str,
    current_url: str,
    redirect_url: str,
    status_code: int,
    kwargs: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Apply requests-compatible method rules and credential boundaries to one redirect."""
    redirect_method = method
    upper_method = method.upper()
    if status_code == requests.codes.see_other and upper_method != "HEAD":
        redirect_method = "GET"
    elif status_code == requests.codes.found and upper_method != "HEAD":
        redirect_method = "GET"
    elif status_code == requests.codes.moved and upper_method == "POST":
        redirect_method = "GET"

    redirect_kwargs = kwargs.copy()
    # The original query parameters have already been applied to the first URL.
    redirect_kwargs.pop("params", None)

    headers = redirect_kwargs.get("headers")
    if headers is not None:
        headers = dict(headers)
        # Proxy credentials are rebuilt from ``proxies`` by requests and must
        # never be copied as an origin header across redirect hops.
        headers = _without_headers(headers, {"Proxy-Authorization"})

    # requests discards the entity when following 301/302/303 responses. 307/308
    # intentionally preserve both the method and body.
    if status_code not in (requests.codes.temporary_redirect, requests.codes.permanent_redirect):
        for key in ("data", "files", "json"):
            redirect_kwargs.pop(key, None)
        if headers is not None:
            headers = _without_headers(headers, {"Content-Length", "Content-Type", "Transfer-Encoding"})

    if _should_strip_credentials(current_url, redirect_url):
        redirect_kwargs.pop("auth", None)
        redirect_kwargs.pop("cookies", None)
        if headers is not None:
            headers = _without_headers(headers, {"Authorization", "Cookie", "Host", "Proxy-Authorization"})

    if headers is not None:
        redirect_kwargs["headers"] = headers

    return redirect_method, redirect_kwargs


def _dispatch_validated_request(
    method: str,
    url: str,
    validate_target,
    *,
    allow_redirects: bool,
    timeout: int,
    max_redirects: int,
    log_tag: str,
    **kwargs: Any,
) -> Response:
    target = validate_target(url)
    kwargs["allow_redirects"] = False
    kwargs["timeout"] = timeout
    body_positions = _capture_request_body_positions(kwargs)
    gateway = get_egress_gateway()

    try:
        response = gateway.send(method, target, **kwargs)
        current_url = target.url
        redirect_count = 0

        while response.is_redirect and redirect_count < max_redirects:
            if not allow_redirects:
                logger.warning(
                    "[%s] 禁止重定向: url=%s, location=%s",
                    log_tag,
                    url,
                    response.headers.get("Location"),
                )
                response.close()
                raise SSRFError("不允许重定向")

            redirect_url = response.headers.get("Location")
            if not redirect_url:
                break

            redirect_url = urljoin(current_url, redirect_url)
            try:
                next_target = validate_target(redirect_url)
                logger.info("[%s] 重定向: %s -> %s", log_tag, current_url, next_target.url)
                method, kwargs = _prepare_redirect_request(
                    method, current_url, next_target.url, response.status_code, kwargs
                )
                if response.status_code in (requests.codes.temporary_redirect, requests.codes.permanent_redirect):
                    _rewind_request_body(kwargs, body_positions)
            finally:
                response.close()
            response = gateway.send(method, next_target, **kwargs)
            current_url = next_target.url
            redirect_count += 1

        return response

    except UnrewindableBodyError as e:
        raise SafeRequestsError(str(e)) from e
    except requests.RequestException as e:
        raise SafeRequestsError(f"HTTP 请求失败: {e}")


def safe_request(
    method: str,
    url: str,
    *,
    allow_redirects: bool = False,
    allowlist: Optional[set[str]] = None,
    timeout: int = 30,
    max_redirects: int = 5,
    **kwargs: Any,
) -> Response:
    """
    发起安全的 HTTP 请求

    Args:
        method: HTTP 方法
        url: 请求 URL
        allow_redirects: 是否允许重定向（默认禁止）
        allowlist: 域名白名单
        timeout: 超时时间
        max_redirects: 最大重定向次数
        **kwargs: 传递给 requests 的其他参数

    Returns:
        Response 对象

    Raises:
        SafeRequestsError: 请求失败
        SSRFError: SSRF 校验失败
    """
    def _validate(candidate: str) -> ValidatedTarget:
        return SSRFValidator.validate_target(candidate, allowlist=allowlist)

    return _dispatch_validated_request(
        method,
        url,
        _validate,
        allow_redirects=allow_redirects,
        timeout=timeout,
        max_redirects=max_redirects,
        log_tag="SafeRequests",
        **kwargs,
    )


def safe_get(url: str, **kwargs: Any) -> Response:
    """安全的 GET 请求"""
    return safe_request("GET", url, **kwargs)


def safe_post(url: str, **kwargs: Any) -> Response:
    """安全的 POST 请求"""
    return safe_request("POST", url, **kwargs)


def safe_put(url: str, **kwargs: Any) -> Response:
    """安全的 PUT 请求"""
    return safe_request("PUT", url, **kwargs)


def safe_delete(url: str, **kwargs: Any) -> Response:
    """安全的 DELETE 请求"""
    return safe_request("DELETE", url, **kwargs)


def safe_patch(url: str, **kwargs: Any) -> Response:
    """安全的 PATCH 请求"""
    return safe_request("PATCH", url, **kwargs)


def safe_request_llm_endpoint(
    method: str,
    url: str,
    *,
    allow_redirects: bool = False,
    timeout: int = 30,
    max_redirects: int = 5,
    **kwargs: Any,
) -> Response:
    """
    发起安全的 HTTP 请求（LLM/Rerank 端点宽松模式）

    与 safe_request 的区别：
    - 使用 validate_llm_endpoint() 而非 validate()
    - 允许私网地址（10.x, 172.16.x, 192.168.x）和 localhost
    - 仅阻断云元数据地址（169.254.169.254 等）

    适用场景：
    - LLM API 端点（vLLM, Ollama, LocalAI 等内网部署）
    - Rerank 模型端点
    - Embedding 模型端点

    Args:
        method: HTTP 方法
        url: 请求 URL
        allow_redirects: 是否允许重定向（默认禁止）
        timeout: 超时时间
        max_redirects: 最大重定向次数
        **kwargs: 传递给 requests 的其他参数

    Returns:
        Response 对象

    Raises:
        SafeRequestsError: 请求失败
        SSRFError: SSRF 校验失败（云元数据地址）
    """
    return _dispatch_validated_request(
        method,
        url,
        SSRFValidator.validate_llm_endpoint_target,
        allow_redirects=allow_redirects,
        timeout=timeout,
        max_redirects=max_redirects,
        log_tag="SafeRequests-LLM",
        **kwargs,
    )


def safe_get_llm_endpoint(url: str, **kwargs: Any) -> Response:
    """安全的 GET 请求（LLM/Rerank 端点宽松模式）

    允许私网地址和 localhost，仅阻断云元数据地址。
    适用于内网部署的 LLM/Rerank/Embedding 端点（vLLM, Ollama, LocalAI 等）。
    """
    return safe_request_llm_endpoint("GET", url, **kwargs)


def safe_post_llm_endpoint(url: str, **kwargs: Any) -> Response:
    """安全的 POST 请求（LLM/Rerank 端点宽松模式）

    允许私网地址和 localhost，仅阻断云元数据地址。
    适用于内网部署的 LLM/Rerank/Embedding 服务。
    """
    return safe_request_llm_endpoint("POST", url, **kwargs)
