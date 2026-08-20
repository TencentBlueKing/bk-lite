"""本包厂商请求层：tenant token、代理与通讯录分页 HTTP。能力模块不要再抄一份。"""

import time
from threading import Lock
from urllib.parse import urlsplit

import requests

from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_TIMEOUT = 10
FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_AUTH_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_AUTH_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_CONTACT_SCOPES_URL = "https://open.feishu.cn/open-apis/contact/v3/scopes"
FEISHU_DEPARTMENTS_BATCH_URL = "https://open.feishu.cn/open-apis/contact/v3/departments/batch"
FEISHU_DEPARTMENT_CHILDREN_URL = "https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
FEISHU_USERS_BY_DEPARTMENT_URL = "https://open.feishu.cn/open-apis/contact/v3/users/find_by_department"
FEISHU_SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_CREATE_CHAT_URL = "https://open.feishu.cn/open-apis/im/v1/chats"
FEISHU_CHAT_URL = "https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}"
FEISHU_CHAT_MEMBERS_URL = "https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members"
FEISHU_APPLICATION_INFO_URL = "https://open.feishu.cn/open-apis/application/v6/applications/me"
FEISHU_BOT_INFO_URL = "https://open.feishu.cn/open-apis/bot/v3/info"
FEISHU_TOKEN_REFRESH_WINDOW = 300
FEISHU_DEPARTMENT_CHILDREN_MAX_WORKERS = 5
_FEISHU_TENANT_TOKEN_CACHE = {}
_FEISHU_TENANT_TOKEN_CACHE_LOCK = Lock()
def _get_config_value(config: dict, key: str, default: str):
    return (config or {}).get(key) or default


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _get_feishu_department_identifier(item: dict, department_id_type: str | None):
    if department_id_type == "open_department_id":
        return item.get("open_department_id") or item.get("department_id")
    return item.get("department_id") or item.get("open_department_id")


def _mask_app_id(app_id: str) -> str:
    if not app_id:
        return ""
    if len(app_id) <= 6:
        return "******"
    return f"{app_id[:3]}***{app_id[-3:]}"


def _sanitize_url_for_log(url: str) -> str:
    try:
        parsed = urlsplit(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "<invalid-url>"
        hostname = parsed.hostname or ""
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{hostname}{port}"
    except ValueError:
        return "<invalid-url>"


def _get_feishu_token_cache_key(config: dict) -> tuple[str, str]:
    app_id = (config or {}).get("app_id", "")
    token_url = _get_config_value(config, "tenant_access_token_url", FEISHU_TOKEN_URL)
    return token_url, app_id


def _is_token_expiring(cache_entry: dict, current_time: float) -> bool:
    expires_at = float(cache_entry.get("expires_at") or 0)
    return expires_at <= current_time + FEISHU_TOKEN_REFRESH_WINDOW


def _should_retry_with_refreshed_token(response_status_code: int, data: dict) -> bool:
    if response_status_code in (401, 403):
        return True

    message = str((data or {}).get("msg") or "").lower()
    return "token" in message


def _feishu_permission_denied_result(data: dict, request_id: str):
    if str((data or {}).get("code") or "") != "40004":
        return None
    return CapabilityExecutionResult.failed_result(
        "飞书通讯录授权范围不足，请检查应用的通讯录权限范围及应用发布状态",
        code="provider.permission_denied",
        retryable=False,
        external_code="40004",
        external_request_id=request_id,
    )


def _request_tenant_access_token(config: dict, capability_key: str):
    app_id = (config or {}).get("app_id", "")
    app_secret = (config or {}).get("app_secret", "")
    if not app_id or not app_secret:
        return CapabilityExecutionResult.failed_result(
            "Feishu app_id or app_secret is missing",
            code="provider.invalid_config",
            field="app_id" if not app_id else "app_secret",
        )

    logger.debug(f"Testing Feishu connection for capability '{capability_key}', app_id={_mask_app_id(app_id)}")
    token_url = _get_config_value(config, "tenant_access_token_url", FEISHU_TOKEN_URL)
    try:
        response = requests.post(
            token_url,
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=FEISHU_TIMEOUT,
        )
    except requests.Timeout:
        logger.debug(f"Feishu connection test timed out for capability '{capability_key}'")
        return CapabilityExecutionResult.failed_result(
            "Feishu connection test timed out",
            code="provider.timeout",
            retryable=True,
        )
    except requests.RequestException as error:
        logger.debug(
            f"Feishu connection test request failed for capability '{capability_key}': "
            f"error_type={type(error).__name__}"
        )
        return CapabilityExecutionResult.failed_result(
            "Feishu connection request failed",
            code="provider.request_failed",
            retryable=True,
        )

    request_id = response.headers.get("X-Tt-Logid", "")
    try:
        data = response.json()
    except ValueError:
        logger.debug(
            f"Feishu connection test returned invalid JSON for capability '{capability_key}', "
            f"status={response.status_code}, request_id={request_id}"
        )
        return CapabilityExecutionResult.failed_result(
            "Feishu connection returned invalid JSON",
            code="provider.invalid_response",
            external_code=str(response.status_code),
            external_request_id=request_id,
        )

    if response.status_code != 200 or data.get("code") not in (0, None):
        logger.debug(
            f"Feishu connection test failed for capability '{capability_key}': "
            f"status={response.status_code}, code={data.get('code')}, request_id={request_id}"
        )
        return CapabilityExecutionResult.failed_result(
            data.get("msg") or "Feishu authentication failed",
            code="provider.auth_failed",
            external_code=str(data.get("code") or response.status_code),
            external_request_id=request_id,
        )

    return CapabilityExecutionResult.success_result(
        f"Feishu capability '{capability_key}' connection is ready",
        payload={"external_request_id": request_id},
    )

def _fetch_tenant_access_token(config: dict, force_refresh: bool = False):
    app_id = (config or {}).get("app_id", "")
    app_secret = (config or {}).get("app_secret", "")
    if not app_id or not app_secret:
        return None, CapabilityExecutionResult.failed_result(
            "Feishu app_id or app_secret is missing",
            code="provider.invalid_config",
            field="app_id" if not app_id else "app_secret",
        )

    cache_key = _get_feishu_token_cache_key(config)
    token_url = _get_config_value(config, "tenant_access_token_url", FEISHU_TOKEN_URL)
    safe_token_url = _sanitize_url_for_log(token_url)
    current_time = time.time()
    with _FEISHU_TENANT_TOKEN_CACHE_LOCK:
        cache_entry = _FEISHU_TENANT_TOKEN_CACHE.get(cache_key)
        if cache_entry and not force_refresh and not _is_token_expiring(cache_entry, current_time):
            logger.debug(f"Using cached Feishu access token for app_id={_mask_app_id(app_id)}")
            return cache_entry["token"], None

        if cache_entry and (force_refresh or _is_token_expiring(cache_entry, current_time)):
            logger.debug(
                f"Refreshing Feishu access token for app_id={_mask_app_id(app_id)}, "
                f"reason={'forced' if force_refresh else 'expiring_soon'}, endpoint={safe_token_url}"
            )

        try:
            response = requests.post(
                token_url,
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=FEISHU_TIMEOUT,
            )
            data = response.json()
        except requests.Timeout:
            return None, CapabilityExecutionResult.failed_result("Feishu access token request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.debug(
                f"Feishu access token request failed: endpoint={safe_token_url}, "
                f"error_type={type(error).__name__}"
            )
            return None, CapabilityExecutionResult.failed_result("Feishu access token request failed", code="provider.request_failed", retryable=True)

        request_id = response.headers.get("X-Tt-Logid", "")
        logger.debug(
            f"Feishu access token response: endpoint={safe_token_url}, status={response.status_code}, "
            f"request_id={request_id}, app_id={_mask_app_id(app_id)}, code={data.get('code')}, "
            f"expire={data.get('expire') or data.get('expires_in')}"
        )

        if response.status_code != 200 or data.get("code") not in (0, None):
            return None, CapabilityExecutionResult.failed_result(
                data.get("msg") or "Feishu access token request failed",
                code="provider.auth_failed",
                external_code=str(data.get("code") or response.status_code),
            )

        token = data.get("tenant_access_token") or data.get("app_access_token") or ""
        if not token:
            return None, CapabilityExecutionResult.failed_result("Feishu access token is missing", code="provider.invalid_response")

        expires_in = int(data.get("expire") or data.get("expires_in") or 0)
        _FEISHU_TENANT_TOKEN_CACHE[cache_key] = {
            "token": token,
            "expires_at": current_time + max(expires_in, 0),
        }
        return token, None

def _feishu_get_paginated(
    url: str,
    token: str,
    *,
    params: dict | None = None,
    config: dict | None = None,
    item_key: str = "items",
):
    merged_params = dict(params or {})
    page_token = ""
    items = []
    last_request_id = ""
    retried_with_refreshed_token = False
    while True:
        if page_token:
            merged_params["page_token"] = page_token
        elif "page_token" in merged_params:
            del merged_params["page_token"]

        try:
            request_started_at = time.perf_counter()
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=merged_params,
                timeout=FEISHU_TIMEOUT,
            )
            data = response.json()
        except requests.Timeout:
            return None, CapabilityExecutionResult.failed_result("Feishu contact request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.debug(
                f"Feishu contact request failed: endpoint={_sanitize_url_for_log(url)}, "
                f"error_type={type(error).__name__}"
            )
            return None, CapabilityExecutionResult.failed_result("Feishu contact request failed", code="provider.request_failed", retryable=True)

        last_request_id = response.headers.get("X-Tt-Logid", "")
        page_data = data.get("data") or {}
        page_items = page_data.get(item_key) or ([] if item_key != "items" else page_data.get("user_list") or [])
        duration_ms = int((time.perf_counter() - request_started_at) * 1000)
        logger.debug(
            f"Feishu contact response: endpoint={_sanitize_url_for_log(url)}, status={response.status_code}, "
            f"request_id={last_request_id}, page_token_present={bool(page_token)}, code={data.get('code')}, "
            f"items_count={len(page_items)}, has_more={page_data.get('has_more', False)}, duration_ms={duration_ms}"
        )
        if response.status_code != 200 or data.get("code") not in (0, None):
            permission_denied_error = _feishu_permission_denied_result(data, last_request_id)
            if permission_denied_error:
                return None, permission_denied_error
            if config and not retried_with_refreshed_token and _should_retry_with_refreshed_token(response.status_code, data):
                logger.debug(
                    f"Feishu contact request auth failed, refreshing token and retrying once: "
                    f"endpoint={_sanitize_url_for_log(url)}, request_id={last_request_id}"
                )
                refreshed_token, token_error = _fetch_tenant_access_token(config, force_refresh=True)
                if token_error:
                    return None, token_error
                token = refreshed_token
                retried_with_refreshed_token = True
                continue

            return None, CapabilityExecutionResult.failed_result(
                data.get("msg") or "Feishu contact request failed",
                code="provider.auth_failed",
                external_code=str(data.get("code") or response.status_code),
                external_request_id=last_request_id,
            )

        items.extend(page_items)
        if not page_data.get("has_more"):
            return {"items": items, "request_id": last_request_id}, None
        page_token = page_data.get("page_token") or ""
        if not page_token:
            return {"items": items, "request_id": last_request_id}, None
