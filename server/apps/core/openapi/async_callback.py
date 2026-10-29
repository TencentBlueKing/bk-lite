"""网关异步回调的 HTTP 投递。作业平台与编排中心共用，失败不得回写业务终态。"""

import os
from urllib.parse import urlparse, urlunparse

import requests

from apps.core.utils.ssrf_validator import SSRFValidator


class AsyncCallbackRetry(Exception):
    """调用方明确要求稍后重试（如 ITSM ticket_schedule）。"""


def _running_in_kubernetes() -> bool:
    return bool(os.getenv("KUBERNETES_SERVICE_HOST"))


def _origin_host_key(url: str):
    """比较回调 URL 与公网入口是否同一主机；忽略 http/https 和 80/443 默认端口。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    port = parsed.port
    if port in (80, 443):
        port = None
    return host, port


def _looks_like_compose_traefik(host: str) -> bool:
    if not host:
        return False
    name = host.lower()
    if name == "traefik":
        return True
    return name.endswith("-traefik") or "-traefik-" in name


def _normalize_internal_base(internal: str) -> str:
    """Compose Traefik 只有 websecure（TLS）。显式写成 http://traefik 时改成 https。"""
    internal = (internal or "").rstrip("/")
    parsed = urlparse(internal)
    host = parsed.hostname or ""
    if parsed.scheme == "http" and _looks_like_compose_traefik(host) and not _running_in_kubernetes():
        port = parsed.port
        if port in (None, 443):
            return f"https://{host}"
        return f"https://{host}:{port}"
    return internal


def default_public_origin() -> str:
    """公网入口。未配 OPENAPI_PUBLIC_ORIGIN 时用平台已有的对外地址。"""
    explicit = (os.getenv("OPENAPI_PUBLIC_ORIGIN") or "").strip()
    if explicit:
        parsed = urlparse(explicit)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return explicit.rstrip("/")
    for key in ("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "NEXTAUTH_URL"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return ""


def default_callback_internal_base() -> str:
    """集群内回环到网关。未配 OPENAPI_CALLBACK_INTERNAL_BASE 时，Compose 用 https://traefik。"""
    explicit = (os.getenv("OPENAPI_CALLBACK_INTERNAL_BASE") or "").strip()
    if explicit:
        return _normalize_internal_base(explicit)
    if _running_in_kubernetes():
        return ""
    port = (os.getenv("TRAEFIK_WEB_PORT") or "443").strip() or "443"
    if port == "443":
        return "https://traefik"
    return f"https://traefik:{port}"


def rewrite_gateway_callback_url(url: str) -> str:
    public = default_public_origin()
    internal = default_callback_internal_base()
    if not public or not internal:
        return url
    if _origin_host_key(url) != _origin_host_key(public):
        return url
    parsed = urlparse(url)
    path = urlunparse(("", "", parsed.path, parsed.params, parsed.query, parsed.fragment))
    if not path.startswith("/"):
        path = "/" + path
    return internal.rstrip("/") + path


def callback_tls_verify(url: str):
    """传给 requests 的 verify。默认校验证书；Compose Traefik 自签回环除外。

    OPENAPI_CALLBACK_SSL_VERIFY：
      - 未配置：仅 Compose 内部 traefik 主机关闭校验，其余 True
      - true/1/yes → True
      - false/0/no → False
      - 其它非空 → 视为 CA 文件/目录路径
    """
    raw = (os.getenv("OPENAPI_CALLBACK_SSL_VERIFY") or "").strip()
    if raw:
        lowered = raw.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        return raw
    host = urlparse(url).hostname or ""
    if not _running_in_kubernetes() and _looks_like_compose_traefik(host):
        return False
    return True


def callback_result_data(parsed) -> dict:
    """ITSM CustomRenderer 会包一层 data；部分网关/中间件可能再包一层。"""
    data = parsed if isinstance(parsed, dict) else {}
    for _ in range(4):
        if not isinstance(data, dict):
            return {}
        if "success" in data or "ticket_schedule" in data:
            return data
        inner = data.get("data")
        if not isinstance(inner, dict):
            return data
        data = inner
    return data if isinstance(data, dict) else {}


def deliver_gateway_callback(payload: dict) -> None:
    url = rewrite_gateway_callback_url(payload["url"])
    body = payload.get("request_body") or {}
    identity = payload.get("identity") or {}
    headers = {"Content-Type": "application/json"}
    user = identity.get("user") or ""
    domain = identity.get("domain") or ""
    if user and domain:
        headers["X-Bklite-Acting-User"] = f"{user}@{domain}"
    elif user:
        headers["X-Bklite-Acting-User"] = user
    if identity.get("team_id"):
        headers["X-Bklite-Acting-Team"] = str(identity["team_id"])
    SSRFValidator.validate_callback(url)
    # 网关内部回环走 Docker / 集群 DNS（含 172.16/12），不能用 safe_post 的严格 SSRF。
    response = requests.post(
        url,
        json=body,
        headers=headers,
        allow_redirects=False,
        timeout=30,
        verify=callback_tls_verify(url),
    )
    if not 200 <= response.status_code < 300:
        if response.status_code in (401, 403, 404):
            raise RuntimeError(f"CALLBACK_REJECTED status_code={response.status_code}")
        raise RuntimeError(f"回调返回非 2xx: status_code={response.status_code}")
    try:
        parsed = response.json()
    except Exception as exc:
        raise RuntimeError("回调响应不是 JSON") from exc
    data = callback_result_data(parsed)
    if not isinstance(data, dict) or not data:
        raise RuntimeError("回调响应缺少 data")
    if data.get("ticket_schedule") is True:
        raise AsyncCallbackRetry("ticket_schedule")
    if data.get("success") is not True:
        raise RuntimeError(f"回调未成功: error={data.get('error') or ''}")
