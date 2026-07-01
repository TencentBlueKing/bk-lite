import json
import time
from threading import Lock
import requests
from urllib.parse import urlencode

from apps.core.logger import logger

from .base import BaseIMNotificationAdapter, BaseLoginAuthAdapter, BaseUserSyncAdapter
from ..runtime import CapabilityExecutionResult

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_TIMEOUT = 10
FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_AUTH_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_AUTH_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_DEPARTMENT_CHILDREN_URL = "https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
FEISHU_USERS_BY_DEPARTMENT_URL = "https://open.feishu.cn/open-apis/contact/v3/users/find_by_department"
FEISHU_SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_TOKEN_REFRESH_WINDOW = 300
_FEISHU_TENANT_TOKEN_CACHE = {}
_FEISHU_TENANT_TOKEN_CACHE_LOCK = Lock()


def _get_config_value(config: dict, key: str, default: str):
    return (config or {}).get(key) or default


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


def _request_tenant_access_token(config: dict, capability_key: str):
    app_id = (config or {}).get("app_id", "")
    app_secret = (config or {}).get("app_secret", "")
    if not app_id or not app_secret:
        missing_field = "app_id" if not app_id else "app_secret"
        logger.warning(
            f"Feishu connection test cannot start for capability '{capability_key}': "
            f"missing required field '{missing_field}', app_id={_mask_app_id(app_id)}"
        )
        return CapabilityExecutionResult.failed_result(
            "Feishu app_id or app_secret is missing",
            code="provider.invalid_config",
            field="app_id" if not app_id else "app_secret",
        )

    logger.info(f"Testing Feishu connection for capability '{capability_key}', app_id={_mask_app_id(app_id)}")
    token_url = _get_config_value(config, "tenant_access_token_url", FEISHU_TOKEN_URL)
    try:
        response = requests.post(
            token_url,
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=FEISHU_TIMEOUT,
        )
    except requests.Timeout:
        logger.warning(f"Feishu connection test timed out for capability '{capability_key}'")
        return CapabilityExecutionResult.failed_result(
            "Feishu connection test timed out",
            code="provider.timeout",
            retryable=True,
        )
    except requests.RequestException as error:
        logger.exception(
            f"Feishu connection test request failed for capability '{capability_key}': {error}"
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
        logger.exception(
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
        logger.warning(
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
    current_time = time.time()
    with _FEISHU_TENANT_TOKEN_CACHE_LOCK:
        cache_entry = _FEISHU_TENANT_TOKEN_CACHE.get(cache_key)
        if cache_entry and not force_refresh and not _is_token_expiring(cache_entry, current_time):
            logger.info(f"Using cached Feishu access token for app_id={_mask_app_id(app_id)}")
            return cache_entry["token"], None

        if cache_entry and (force_refresh or _is_token_expiring(cache_entry, current_time)):
            logger.info(
                f"Refreshing Feishu access token for app_id={_mask_app_id(app_id)}, "
                f"reason={'forced' if force_refresh else 'expiring_soon'}"
            )

        try:
            token_url = _get_config_value(config, "tenant_access_token_url", FEISHU_TOKEN_URL)
            response = requests.post(
                token_url,
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=FEISHU_TIMEOUT,
            )
            data = response.json()
        except requests.Timeout:
            return None, CapabilityExecutionResult.failed_result("Feishu access token request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.error(f"Feishu access token request failed: {error}")
            return None, CapabilityExecutionResult.failed_result("Feishu access token request failed", code="provider.request_failed", retryable=True)

        request_id = response.headers.get("X-Tt-Logid", "")
        logged_data = dict(data or {})
        if "tenant_access_token" in logged_data:
            logged_data["tenant_access_token"] = "***"
        if "app_access_token" in logged_data:
            logged_data["app_access_token"] = "***"
        logger.info(
            f"Feishu access token response: url={token_url}, status={response.status_code}, "
            f"request_id={request_id}, app_id={_mask_app_id(app_id)}, data={logged_data}"
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


def _feishu_get_paginated(url: str, token: str, *, params: dict | None = None, config: dict | None = None):
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
            logger.error(f"Feishu contact request failed: {error}")
            return None, CapabilityExecutionResult.failed_result("Feishu contact request failed", code="provider.request_failed", retryable=True)

        last_request_id = response.headers.get("X-Tt-Logid", "")
        logger.info(
            f"Feishu contact response: url={url}, status={response.status_code}, "
            f"request_id={last_request_id}, params={merged_params}, data={data}"
        )
        if response.status_code != 200 or data.get("code") not in (0, None):
            if config and not retried_with_refreshed_token and _should_retry_with_refreshed_token(response.status_code, data):
                logger.warning(
                    f"Feishu contact request auth failed, refreshing token and retrying once: "
                    f"url={url}, request_id={last_request_id}"
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

        page_data = data.get("data") or {}
        items.extend(page_data.get("items") or page_data.get("user_list") or [])
        if not page_data.get("has_more"):
            return {"items": items, "request_id": last_request_id}, None
        page_token = page_data.get("page_token") or ""
        if not page_token:
            return {"items": items, "request_id": last_request_id}, None


class FeishuLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def build_login_url(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        app_id = (config or {}).get("app_id", "")
        redirect_uri = kwargs.get("redirect_uri", "")
        state = kwargs.get("state", "")
        if not app_id or not redirect_uri:
            return CapabilityExecutionResult.failed_result(
                "Feishu login redirect configuration is incomplete",
                code="provider.invalid_config",
                field="app_id" if not app_id else "redirect_uri",
            )

        authorize_url = _get_config_value(config, "login_auth_authorize_url", FEISHU_AUTHORIZE_URL)
        authorize_url = f"{authorize_url}?{urlencode({'app_id': app_id, 'redirect_uri': redirect_uri, 'state': state})}"
        return CapabilityExecutionResult.success_result(
            "Feishu login URL generated",
            payload={"authorize_url": authorize_url},
        )

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        auth_code = kwargs.get("auth_code", "")
        binding = kwargs.get("binding")
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        if not auth_code:
            return CapabilityExecutionResult.failed_result(
                "Feishu login request is missing required parameters",
                code="provider.invalid_config",
                field="auth_code",
            )

        try:
            access_token_url = _get_config_value(config, "login_auth_access_token_url", FEISHU_AUTH_ACCESS_TOKEN_URL)
            token_response = requests.post(
                access_token_url,
                json={"grant_type": "authorization_code", "code": auth_code},
                headers={"Authorization": f"Bearer {tenant_access_token}"},
                timeout=FEISHU_TIMEOUT,
            )
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("Feishu login request timed out", code="provider.timeout", retryable=True)
        except requests.RequestException as error:
            logger.error(f"Feishu login request failed: {error}")
            return CapabilityExecutionResult.failed_result("Feishu login request failed", code="provider.request_failed", retryable=True)

        try:
            token_data = token_response.json()
        except ValueError:
            return CapabilityExecutionResult.failed_result("Feishu login response is invalid", code="provider.invalid_response")

        if token_response.status_code != 200 or token_data.get("code") not in (0, None):
            return CapabilityExecutionResult.failed_result(
                token_data.get("msg") or "Feishu login failed",
                code="provider.auth_failed",
                external_code=str(token_data.get("code") or token_response.status_code),
            )

        access_token = token_data.get("data", {}).get("access_token") or token_data.get("access_token", "")
        if not access_token:
            return CapabilityExecutionResult.failed_result("Feishu login token is missing", code="provider.invalid_response")

        try:
            user_info_url = _get_config_value(config, "login_auth_user_info_url", FEISHU_AUTH_USER_INFO_URL)
            user_response = requests.get(
                user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=FEISHU_TIMEOUT,
            )
            user_data = user_response.json()
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result("Feishu user info request timed out", code="provider.timeout", retryable=True)
        except (requests.RequestException, ValueError) as error:
            logger.error(f"Feishu user info request failed: {error}")
            return CapabilityExecutionResult.failed_result("Feishu user info request failed", code="provider.request_failed", retryable=True)

        if user_response.status_code != 200 or user_data.get("code") not in (0, None):
            return CapabilityExecutionResult.failed_result(
                user_data.get("msg") or "Feishu user info fetch failed",
                code="provider.auth_failed",
                external_code=str(user_data.get("code") or user_response.status_code),
            )

        data = user_data.get("data") or {}
        return CapabilityExecutionResult.success_result(
            f"Feishu login authenticated for binding '{getattr(binding, 'name', '')}'",
            payload={
                "external_user": {
                    "user_id": data.get("user_id", ""),
                    "open_id": data.get("open_id", ""),
                    "union_id": data.get("union_id", ""),
                    "name": data.get("name", ""),
                    "email": data.get("email", ""),
                    "mobile": data.get("mobile", ""),
                    "avatar_url": data.get("avatar_url", ""),
                    "tenant_key": data.get("tenant_key", ""),
                }
            },
        )


class FeishuUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def list_departments(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        from apps.system_mgmt.services.user_sync_service import ALL_DEPARTMENT_SELECTION_ID

        source = kwargs.get("source")
        business_config = kwargs.get("business_config") or {}
        source_business_config = getattr(source, "business_config", None) or {}
        merged_business_config = {**source_business_config, **business_config}

        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        department_id_type = merged_business_config.get("department_id_type")
        root_department_id = str(merged_business_config.get("root_department_id") or "0")

        department_params: dict = {
            "page_size": 50,
            "fetch_child": "true",
        }
        if department_id_type:
            department_params["department_id_type"] = department_id_type

        department_payload, error = _feishu_get_paginated(
            _get_config_value(config, "user_sync_departments_url", FEISHU_DEPARTMENT_CHILDREN_URL).format(department_id="0"),
            tenant_access_token,
            params=department_params,
            config=config,
        )
        if error:
            return error

        all_department_id = "0"
        department_items = []
        children_map: dict[str, list[dict]] = {}
        for item in department_payload["items"]:
            department_id = _get_feishu_department_identifier(item, department_id_type)
            if not department_id:
                continue
            department_id = str(department_id)
            parent_department_id = str(item.get("parent_department_id") or all_department_id)
            department_node = {
                "id": department_id,
                "name": item.get("name") or department_id,
                "parent_id": ALL_DEPARTMENT_SELECTION_ID if parent_department_id == all_department_id else parent_department_id,
                "children": [],
                "selectable": True,
                "is_all": False,
            }
            department_items.append(department_node)
            children_map.setdefault(department_node["parent_id"], []).append(department_node)

        def build_department_tree(parent_id: str):
            tree_nodes = []
            for node in children_map.get(parent_id, []):
                tree_nodes.append({**node, "children": build_department_tree(node["id"])})
            return tree_nodes

        items = [
            {
                "id": ALL_DEPARTMENT_SELECTION_ID,
                "name": "全部部门",
                "parent_id": None,
                "children": build_department_tree(ALL_DEPARTMENT_SELECTION_ID),
                "selectable": True,
                "is_all": True,
            }
        ]

        if root_department_id == all_department_id:
            selected_id = ALL_DEPARTMENT_SELECTION_ID
            selection_missing = False
        else:
            department_ids = {item["id"] for item in department_items}
            selected_id = root_department_id if root_department_id in department_ids else ""
            selection_missing = bool(root_department_id and not selected_id)

        return CapabilityExecutionResult.success_result(
            "Feishu department options loaded",
            payload={
                "items": items,
                "all_department_id": all_department_id,
                "selected_id": selected_id,
                "selection_missing": selection_missing,
            },
        )

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        # Local import avoids circular dependency: adapters -> service -> providers -> adapters
        from apps.system_mgmt.services.user_sync_service import get_user_sync_business_value

        source = kwargs.get("source")
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        root_department_id = get_user_sync_business_value(source, "root_department_id", "0") or "0"
        department_id_type = get_user_sync_business_value(source, "department_id_type", None)
        user_id_type = get_user_sync_business_value(source, "user_id_type", None)

        dept_params: dict = {"page_size": 50, "fetch_child": "true"}
        if department_id_type:
            dept_params["department_id_type"] = department_id_type

        department_payload, error = _feishu_get_paginated(
            _get_config_value(config, "user_sync_departments_url", FEISHU_DEPARTMENT_CHILDREN_URL).format(department_id=root_department_id),
            tenant_access_token,
            params=dept_params,
            config=config,
        )
        if error:
            return error

        user_params: dict = {
            "department_id": root_department_id,
            "fetch_child": "true",
            "page_size": 50,
            "fields": "department_ids,user_id,open_id,name,email,mobile",
        }
        if user_id_type:
            user_params["user_id_type"] = user_id_type
        if department_id_type:
            user_params["department_id_type"] = department_id_type

        user_payload, error = _feishu_get_paginated(
            _get_config_value(config, "user_sync_users_url", FEISHU_USERS_BY_DEPARTMENT_URL),
            tenant_access_token,
            params=user_params,
            config=config,
        )
        if error:
            return error

        group_list = []
        for item in department_payload["items"]:
            department_id = _get_feishu_department_identifier(item, department_id_type)
            if not department_id:
                continue
            group_list.append(
                {
                    "id": str(department_id),
                    "parent_id": str(item.get("parent_department_id") or root_department_id),
                    "name": item.get("name") or str(department_id),
                }
            )

        user_list = []
        for item in user_payload["items"]:
            user_id = item.get("user_id") or item.get("open_id")
            if not user_id:
                continue
            user_list.append(
                {
                    "user_id": item.get("user_id", ""),
                    "open_id": item.get("open_id", ""),
                    "name": item.get("name", ""),
                    "email": item.get("email", ""),
                    "mobile": item.get("mobile", ""),
                    "department_ids": [str(value) for value in item.get("department_ids") or []],
                }
            )

        return CapabilityExecutionResult.success_result(
            f"Feishu user sync payload fetched for source '{getattr(source, 'name', '')}'",
            payload={
                "group_list": group_list,
                "user_list": user_list,
                "external_request_id": user_payload.get("request_id") or department_payload.get("request_id") or "",
            },
        )


class FeishuIMNotificationAdapter(BaseIMNotificationAdapter):
    capability_key = "im_notification"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def list_external_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        user_payload, error = _feishu_get_paginated(
            _get_config_value(config, "im_notification_users_url", FEISHU_USERS_BY_DEPARTMENT_URL),
            tenant_access_token,
            params={
                "department_id": "0",
                "fetch_child": "true",
                "page_size": 50,
                "fields": "user_id,open_id,name,email,mobile",
            },
            config=config,
        )
        if error:
            return error

        external_users = []
        for item in user_payload["items"]:
            external_users.append(
                {
                    "user_id": item.get("user_id", ""),
                    "open_id": item.get("open_id", ""),
                    "name": item.get("name", ""),
                    "email": item.get("email", ""),
                    "mobile": item.get("mobile", ""),
                }
            )

        return CapabilityExecutionResult.success_result(
            "Feishu IM users fetched",
            payload={"external_users": external_users, "external_request_id": user_payload.get("request_id", "")},
        )

    @classmethod
    def send_message(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        receive_ids = kwargs.get("receive_ids") or []
        receive_id_type = kwargs.get("receive_id_type") or "user_id"
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        if not receive_ids:
            return CapabilityExecutionResult.failed_result("No IM receivers provided", code="provider.invalid_config", field="receive_ids")

        failures = []
        sent_count = 0
        send_message_url = _get_config_value(config, "im_notification_send_message_url", FEISHU_SEND_MESSAGE_URL)
        for receive_id in receive_ids:
            message_text = f"{title}\n{content}".strip()
            payload = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": message_text}, ensure_ascii=False),
            }
            try:
                response = requests.post(
                    f"{send_message_url}?receive_id_type={receive_id_type}",
                    headers={
                        "Authorization": f"Bearer {tenant_access_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                    timeout=FEISHU_TIMEOUT,
                )
                data = response.json()
            except requests.Timeout:
                failures.append({"receive_id": receive_id, "message": "Feishu message request timed out"})
                continue
            except (requests.RequestException, ValueError) as request_error:
                failures.append({"receive_id": receive_id, "message": str(request_error)})
                continue

            if response.status_code != 200 or data.get("code") not in (0, None):
                failures.append({"receive_id": receive_id, "message": data.get("msg") or "Feishu message send failed"})
                continue
            sent_count += 1

        if failures:
            return CapabilityExecutionResult(
                success=sent_count > 0,
                summary=f"Feishu IM message sent to {sent_count} users, {len(failures)} failed",
                partial_success=sent_count > 0,
                retryable=True,
                payload={"sent_count": sent_count, "failures": failures},
            )
        return CapabilityExecutionResult.success_result("Feishu IM message sent", payload={"sent_count": sent_count})
