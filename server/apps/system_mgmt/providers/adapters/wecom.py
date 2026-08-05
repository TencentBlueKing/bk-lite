from urllib.parse import urlencode, urlparse

import requests

from apps.core.logger import system_mgmt_logger as logger

from .base import BaseIMNotificationAdapter, BaseLoginAuthAdapter, BaseUserSyncAdapter
from ..runtime import CapabilityExecutionResult


# 企业微信官方端点常量,作为配置缺失时的兜底默认值。
WECOM_DEFAULT_ACCESS_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_DEFAULT_LOGIN_AUTH_AUTHORIZE_URL = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
WECOM_DEFAULT_LOGIN_AUTH_USER_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL = "https://qyapi.weixin.qq.com/cgi-bin/department/list"
WECOM_DEFAULT_USER_SYNC_USERS_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/list"
WECOM_DEFAULT_IM_NOTIFICATION_USERS_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/list"
WECOM_DEFAULT_IM_NOTIFICATION_SEND_MESSAGE_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

WECOM_TIMEOUT = 10
WECOM_MAX_PAGES = 100


def _parse_json_response(response):
    """解析企业微信响应,要求顶层为 dict;否则按 invalid_response 抛出。"""
    try:
        data = response.json()
    except ValueError:
        raise ValueError("WeCom response is not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("WeCom response is not a JSON object")
    return data


def _validate_credentials(config):
    config = config or {}
    for field in ("corp_id", "corp_secret"):
        if not config.get(field):
            return CapabilityExecutionResult.failed_result(
                "WeCom credentials are incomplete",
                code="provider.invalid_config",
                field=field,
            )
    for field, value in config.items():
        if not field.endswith("_url") or not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return CapabilityExecutionResult.failed_result(
                "WeCom endpoint must use HTTP or HTTPS",
                code="provider.invalid_config",
                field=field,
            )
    return None


def _resolve_proxies(config):
    """根据 proxy_url 构造 requests proxies;为空返回 None。"""
    proxy_url = (config or {}).get("proxy_url") or ""
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _resolved_url(config, field_key, default):
    """优先读取实例配置,缺失时回退到官方常量。"""
    config = config or {}
    return config.get(field_key) or default


def _sanitize_url_for_log(url):
    """保留身份接口的安全定位信息，过滤凭据和查询参数。"""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "<invalid-url>"
    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        return "<invalid-url>"
    return f"{parsed.scheme}://{hostname}{port}{parsed.path}"


def _get_access_token(config):
    """统一从基础连接读取 access_token_url,不再依赖 api_base_url 拼接。"""
    url = _resolved_url(config, "access_token_url", WECOM_DEFAULT_ACCESS_TOKEN_URL)
    kwargs = {
        "params": {"corpid": config["corp_id"], "corpsecret": config["corp_secret"]},
        "timeout": WECOM_TIMEOUT,
    }
    proxies = _resolve_proxies(config)
    if proxies is not None:
        kwargs["proxies"] = proxies
    try:
        response = requests.get(url, **kwargs)
        data = _parse_json_response(response)
    except requests.Timeout:
        return None, CapabilityExecutionResult.failed_result(
            "WeCom access token request timed out",
            code="provider.timeout",
            retryable=True,
        )
    except ValueError as error:
        return None, CapabilityExecutionResult.failed_result(
            str(error) or "WeCom access token response is invalid",
            code="provider.invalid_response",
        )
    except (KeyError, requests.RequestException):
        return None, CapabilityExecutionResult.failed_result(
            "WeCom access token request failed",
            code="provider.request_failed",
            retryable=True,
        )

    if response.status_code != 200 or data.get("errcode") or not data.get("access_token"):
        return None, CapabilityExecutionResult.failed_result(
            "WeCom authentication failed",
            code="provider.auth_failed",
            external_code=str(data.get("errcode") or response.status_code),
        )
    return data["access_token"], None


def _request_get(url, config, token, params=None, *, return_response=False):
    """执行带 token 的 GET 请求;显式传入 config 以注入代理配置。"""
    kwargs = {
        "params": {"access_token": token, **(params or {})},
        "timeout": WECOM_TIMEOUT,
    }
    proxies = _resolve_proxies(config)
    if proxies is not None:
        kwargs["proxies"] = proxies
    response = requests.get(url, **kwargs)
    data = _parse_json_response(response)
    if response.status_code != 200 or data.get("errcode"):
        raise ValueError(data.get("errmsg") or "WeCom request failed")
    return (data, response) if return_response else data


def _normalize_users(users):
    normalized = {}
    for user in users:
        user_id = str(user.get("userid") or "").strip()
        if not user_id:
            continue
        item = normalized.setdefault(
            user_id,
            {
                "userid": user_id,
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "mobile": user.get("mobile", ""),
                "department_ids": [],
            },
        )
        item["department_ids"] = sorted(
            {*item["department_ids"], *(str(value) for value in user.get("department") or [])}
        )
    return list(normalized.values())


def _fetch_all_users(config, token, url, params):
    """拉取企业微信成员全部页，按 userid 合并后归一化。

    为防止服务端异常返回相同 cursor 导致无限分页,记录已见 cursor 并设上限。
    """
    aggregated = []
    cursor = ""
    seen_cursors = set()
    proxies = _resolve_proxies(config)
    for _ in range(WECOM_MAX_PAGES):
        page_params = dict(params or {})
        if cursor:
            if cursor in seen_cursors:
                return None, CapabilityExecutionResult.failed_result(
                    "WeCom directory pagination repeated the same cursor",
                    code="provider.invalid_response",
                    field="next_cursor",
                )
            seen_cursors.add(cursor)
            page_params["cursor"] = cursor
        else:
            page_params.pop("cursor", None)
        kwargs = {
            "params": {"access_token": token, **page_params},
            "timeout": WECOM_TIMEOUT,
        }
        if proxies is not None:
            kwargs["proxies"] = proxies
        try:
            response = requests.get(url, **kwargs)
            data = _parse_json_response(response)
        except requests.Timeout:
            return None, CapabilityExecutionResult.failed_result(
                "WeCom directory request timed out",
                code="provider.timeout",
                retryable=True,
            )
        except ValueError as error:
            return None, CapabilityExecutionResult.failed_result(
                str(error) or "WeCom directory response is invalid",
                code="provider.invalid_response",
            )
        except requests.RequestException:
            return None, CapabilityExecutionResult.failed_result(
                "WeCom directory request failed",
                code="provider.request_failed",
                retryable=True,
            )
        if response.status_code != 200 or data.get("errcode"):
            return None, CapabilityExecutionResult.failed_result(
                data.get("errmsg") or "WeCom directory request failed",
                code="provider.auth_failed",
                external_code=str(data.get("errcode") or response.status_code),
            )
        aggregated.extend(data.get("userlist") or [])
        cursor = data.get("next_cursor") or ""
        if not cursor:
            break
    else:
        return None, CapabilityExecutionResult.failed_result(
            "WeCom directory pagination exceeded the page limit",
            code="provider.invalid_response",
            field="next_cursor",
        )
    return _normalize_users(aggregated), None


def _department_tree(departments):
    nodes = {}
    children = {}
    for department in departments:
        department_id = str(department.get("id") or "")
        if not department_id:
            continue
        node = {
            "id": department_id,
            "name": department.get("name") or department_id,
            "parent_id": str(department.get("parentid") or ""),
            "children": [],
            "selectable": True,
        }
        nodes[department_id] = node

    for node in nodes.values():
        parent_id = node["parent_id"]
        if parent_id not in nodes:
            node["parent_id"] = None
        else:
            children.setdefault(parent_id, []).append(node)

    def build(parent_id):
        return [{**node, "children": build(node["id"])} for node in children.get(parent_id, [])]

    return [
        {**node, "children": build(node["id"])}
        for node in nodes.values()
        if node["parent_id"] is None
    ]


class WeComLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def build_login_url(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        config = config or {}
        corp_id = config.get("corp_id", "")
        agent_id = config.get("agent_id", "")
        redirect_uri = kwargs.get("redirect_uri", "")
        if not corp_id or not agent_id or not redirect_uri:
            return CapabilityExecutionResult.failed_result(
                "WeCom login redirect configuration is incomplete",
                code="provider.invalid_config",
            )
        authorize_url = _resolved_url(
            config, "login_auth_authorize_url", WECOM_DEFAULT_LOGIN_AUTH_AUTHORIZE_URL
        )
        query = urlencode({
            "appid": corp_id,
            "agentid": agent_id,
            "redirect_uri": redirect_uri,
            "state": kwargs.get("state", ""),
        })
        return CapabilityExecutionResult.success_result(
            "WeCom login URL generated",
            payload={"authorize_url": f"{authorize_url}?{query}"},
        )

    @classmethod
    def authenticate(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        code = kwargs.get("auth_code", "")
        if error or not code:
            return error or CapabilityExecutionResult.failed_result(
                "WeCom login request is missing code",
                code="provider.invalid_config",
                field="auth_code",
            )
        token, error = _get_access_token(config)
        if error:
            return error
        user_info_url = _resolved_url(
            config, "login_auth_user_info_url", WECOM_DEFAULT_LOGIN_AUTH_USER_INFO_URL
        )
        try:
            identity, response = _request_get(
                user_info_url, config, token, {"code": code}, return_response=True
            )
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result(
                "WeCom login request timed out",
                code="provider.timeout",
                retryable=True,
            )
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                str(error) or "WeCom login response is invalid",
                code="provider.invalid_response",
            )
        except requests.RequestException:
            return CapabilityExecutionResult.failed_result(
                "WeCom login request failed",
                code="provider.request_failed",
                retryable=True,
            )
        # 企业微信当前 /cgi-bin/auth/getuserinfo 文档返回小写 userid；
        # 保留 UserId 兼容历史接口响应，统一输出平台约定的 userid。
        user_id = identity.get("userid") or identity.get("UserId")
        if not user_id:
            logger.warning(
                "WeCom login identity response has no userid or UserId, "
                f"endpoint={_sanitize_url_for_log(user_info_url)}, "
                f"status={response.status_code}, errcode={identity.get('errcode')}, "
                f"errmsg={identity.get('errmsg')!r}, response_keys={sorted(identity.keys())}"
            )
            return CapabilityExecutionResult.failed_result(
                "WeCom user identity is missing",
                code="provider.auth_failed",
            )
        return CapabilityExecutionResult.success_result(
            "WeCom login authenticated",
            payload={"external_user": {"userid": user_id}},
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        _, error = _get_access_token(config)
        return error or CapabilityExecutionResult.success_result("WeCom login capability is ready")


class WeComUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def _departments(cls, config, token, root_department_id=""):
        url = _resolved_url(
            config, "user_sync_departments_url", WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL
        )
        return _request_get(
            url,
            config,
            token,
            {"id": root_department_id} if root_department_id else {},
        ).get("department", [])

    @classmethod
    def list_departments(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        token, error = _get_access_token(config)
        if error:
            return error
        try:
            departments = cls._departments(config, token)
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result(
                "WeCom department request timed out",
                code="provider.timeout",
                retryable=True,
            )
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                str(error) or "WeCom department response is invalid",
                code="provider.invalid_response",
            )
        except requests.RequestException:
            return CapabilityExecutionResult.failed_result(
                "WeCom department request failed",
                code="provider.request_failed",
                retryable=True,
            )
        return CapabilityExecutionResult.success_result(
            "WeCom department options loaded",
            payload={"items": _department_tree(departments)},
        )

    @classmethod
    def sync_users(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        source = kwargs.get("source")
        business_config = getattr(source, "business_config", {}) or {}
        root_department_id = business_config.get("root_department_id")
        root_department_id = str(root_department_id) if root_department_id is not None else ""
        if root_department_id in {"", "0", "__all__", "**all**"}:
            return CapabilityExecutionResult.failed_result(
                "WeCom root department ID must be a real department ID",
                code="provider.invalid_config",
                field="root_department_id",
            )
        include_child = business_config.get("include_child_departments", True)
        token, error = _get_access_token(config)
        if error:
            return error
        try:
            departments = cls._departments(config, token, root_department_id)
        except requests.Timeout:
            return CapabilityExecutionResult.failed_result(
                "WeCom department request timed out",
                code="provider.timeout",
                retryable=True,
            )
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                str(error) or "WeCom department response is invalid",
                code="provider.invalid_response",
            )
        except requests.RequestException:
            return CapabilityExecutionResult.failed_result(
                "WeCom department request failed",
                code="provider.request_failed",
                retryable=True,
            )
        if not include_child:
            departments = [
                item for item in departments if str(item.get("id")) == str(root_department_id)
            ]
        users_url = _resolved_url(
            config, "user_sync_users_url", WECOM_DEFAULT_USER_SYNC_USERS_URL
        )
        normalized_users, user_error = _fetch_all_users(
            config,
            token,
            users_url,
            {"department_id": root_department_id, "fetch_child": 1 if include_child else 0},
        )
        if user_error:
            return user_error
        return CapabilityExecutionResult.success_result(
            f"WeCom user sync payload fetched for source '{getattr(source, 'name', '')}'",
            payload={
                "group_list": [
                    {
                        "id": str(item["id"]),
                        "parent_id": str(item.get("parentid") or ""),
                        "name": item.get("name", ""),
                    }
                    for item in departments
                    if item.get("id") is not None
                ],
                "user_list": normalized_users,
            },
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        _, error = _get_access_token(config)
        return error or CapabilityExecutionResult.success_result("WeCom user sync capability is ready")


class WeComIMNotificationAdapter(BaseIMNotificationAdapter):
    capability_key = "im_notification"

    @classmethod
    def _token(cls, config):
        error = _validate_credentials(config)
        if error:
            return None, error
        return _get_access_token(config)

    @classmethod
    def list_external_users(cls, config, provider_key, capability_key, **kwargs):
        token, error = cls._token(config)
        if error:
            return error
        users_url = _resolved_url(
            config, "im_notification_users_url", WECOM_DEFAULT_IM_NOTIFICATION_USERS_URL
        )
        normalized_users, user_error = _fetch_all_users(
            config,
            token,
            users_url,
            {"department_id": "1", "fetch_child": 1},
        )
        if user_error:
            return user_error
        external_users = [
            {key: item[key] for key in ("userid", "name", "email", "mobile")}
            for item in normalized_users
        ]
        return CapabilityExecutionResult.success_result(
            "WeCom IM users fetched",
            payload={"external_users": external_users},
        )

    @classmethod
    def send_message(cls, config, provider_key, capability_key, **kwargs):
        config = config or {}
        if not config.get("agent_id"):
            return CapabilityExecutionResult.failed_result(
                "WeCom AgentId is missing",
                code="provider.invalid_config",
                field="agent_id",
            )
        receive_ids = kwargs.get("receive_ids") or []
        if not receive_ids:
            return CapabilityExecutionResult.failed_result(
                "No IM receivers provided",
                code="provider.invalid_config",
                field="receive_ids",
            )
        token, error = cls._token(config)
        if error:
            return error
        sent_count = 0
        failures = []
        endpoint = _resolved_url(
            config, "im_notification_send_message_url", WECOM_DEFAULT_IM_NOTIFICATION_SEND_MESSAGE_URL
        )
        proxies = _resolve_proxies(config)
        message_text = f"{kwargs.get('title', '')}\n{kwargs.get('content', '')}".strip()
        for receive_id in receive_ids:
            post_kwargs = {
                "params": {"access_token": token},
                "json": {
                    "touser": receive_id,
                    "msgtype": "text",
                    "agentid": config["agent_id"],
                    "text": {"content": message_text},
                },
                "timeout": WECOM_TIMEOUT,
            }
            if proxies is not None:
                post_kwargs["proxies"] = proxies
            try:
                response = requests.post(endpoint, **post_kwargs)
                data = _parse_json_response(response)
                if response.status_code != 200 or data.get("errcode"):
                    failures.append({
                        "receive_id": receive_id,
                        "message": data.get("errmsg") or "WeCom message send failed",
                    })
                    continue
                sent_count += 1
            except requests.Timeout:
                failures.append({"receive_id": receive_id, "message": "WeCom message request timed out"})
            except (requests.RequestException, ValueError):
                failures.append({"receive_id": receive_id, "message": "WeCom message request failed"})
        if failures:
            return CapabilityExecutionResult(
                success=sent_count > 0,
                summary=f"WeCom IM message sent to {sent_count} users, {len(failures)} failed",
                partial_success=sent_count > 0,
                retryable=True,
                payload={"sent_count": sent_count, "failures": failures},
            )
        return CapabilityExecutionResult.success_result(
            "WeCom IM message sent",
            payload={"sent_count": sent_count},
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        config = config or {}
        if not config.get("agent_id"):
            return CapabilityExecutionResult.failed_result(
                "WeCom AgentId is missing",
                code="provider.invalid_config",
                field="agent_id",
            )
        _, error = cls._token(config)
        return error or CapabilityExecutionResult.success_result("WeCom IM notification capability is ready")
