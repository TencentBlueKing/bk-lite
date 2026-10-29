"""网关异步回调的 HTTP 投递。作业平台与编排中心共用，失败不得回写业务终态。"""

import os

import requests

from apps.core.utils.ssrf_validator import SSRFValidator


class AsyncCallbackRetry(Exception):
    """调用方明确要求稍后重试（如 ITSM ticket_schedule）。"""


def rewrite_gateway_callback_url(url: str) -> str:
    public = (os.getenv("OPENAPI_PUBLIC_ORIGIN") or "").rstrip("/")
    internal = (os.getenv("OPENAPI_CALLBACK_INTERNAL_BASE") or "").rstrip("/")
    # Traefik 本环境只监听 443；http://compose-traefik-1 会 connection refused。
    if internal == "http://compose-traefik-1":
        internal = "https://compose-traefik-1"
    if public and internal and url.startswith(public + "/"):
        return internal + url[len(public) :]
    return url


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
    secret = os.getenv("OPENAPI_CALLBACK_SECRET") or ""
    if secret:
        headers["X-Bklite-Callback-Auth"] = secret
    user = identity.get("user") or ""
    domain = identity.get("domain") or ""
    if user and domain:
        headers["X-Bklite-Acting-User"] = f"{user}@{domain}"
    elif user:
        headers["X-Bklite-Acting-User"] = user
    if identity.get("team_id"):
        headers["X-Bklite-Acting-Team"] = str(identity["team_id"])
    SSRFValidator.validate_callback(url)
    # 网关内部回环走 Docker DNS（172.16/12），不能用 safe_post 的严格 SSRF。
    response = requests.post(url, json=body, headers=headers, allow_redirects=False, timeout=30, verify=False)
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
