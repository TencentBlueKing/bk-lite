"""本包厂商请求层：token、代理、分页与带 token 的 HTTP。能力模块不要再抄一份。"""

from urllib.parse import urlparse

import requests

from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

WECOM_DEFAULT_ACCESS_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_DEFAULT_LOGIN_AUTH_AUTHORIZE_URL = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
WECOM_DEFAULT_LOGIN_AUTH_USER_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL = "https://qyapi.weixin.qq.com/cgi-bin/department/list"
WECOM_DEFAULT_USER_SYNC_USERS_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/list"
WECOM_DEFAULT_IM_NOTIFICATION_USERS_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/list"
WECOM_DEFAULT_IM_NOTIFICATION_SEND_MESSAGE_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

WECOM_TIMEOUT = 10
WECOM_MAX_PAGES = 100
WECOM_GROUP_CREATE_CANDIDATE_PROBE_LIMIT = 20
WECOM_GROUP_MEMBER_ISOLATION_CALL_LIMIT = 32


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


def _map_wecom_request_exception(error, *, timeout_message, invalid_message, request_failed_message):
    """把 Timeout / ValueError / RequestException 映射为统一的 CapabilityExecutionResult。"""
    if isinstance(error, requests.Timeout):
        return CapabilityExecutionResult.failed_result(
            timeout_message,
            code="provider.timeout",
            retryable=True,
        )
    if isinstance(error, ValueError):
        return CapabilityExecutionResult.failed_result(
            str(error) or invalid_message,
            code="provider.invalid_response",
        )
    if isinstance(error, (KeyError, requests.RequestException)):
        return CapabilityExecutionResult.failed_result(
            request_failed_message,
            code="provider.request_failed",
            retryable=True,
        )
    raise error


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
    except (KeyError, ValueError, requests.Timeout, requests.RequestException) as error:
        return None, _map_wecom_request_exception(
            error,
            timeout_message="WeCom access token request timed out",
            invalid_message="WeCom access token response is invalid",
            request_failed_message="WeCom access token request failed",
        )

    if response.status_code != 200 or data.get("errcode") or not data.get("access_token"):
        return None, CapabilityExecutionResult.failed_result(
            "WeCom authentication failed",
            code="provider.auth_failed",
            external_code=str(data.get("errcode") or response.status_code),
        )
    return data["access_token"], None


def _fetch_visible_departments(config, token):
    url = _resolved_url(config, "user_sync_departments_url", WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL)
    try:
        data = _request_get(url, config, token)
    except (ValueError, requests.Timeout, requests.RequestException) as error:
        return None, _map_wecom_request_exception(
            error,
            timeout_message="WeCom department request timed out",
            invalid_message="WeCom department response is invalid",
            request_failed_message="WeCom department request failed",
        )
    return data.get("department") or [], None


def _visible_department_root_ids(departments):
    """应用可见部门林的根：父部门不在本次返回集合内。

    空列表表示权限范围内没有可见部门（例如可见范围仅成员/标签），不臆造公司根 ``1``。
    """
    visible_id_set = set()
    for department in departments or []:
        department_id = str(department.get("id") or "").strip()
        if department_id:
            visible_id_set.add(department_id)
    if not visible_id_set:
        return []

    roots = []
    for department in departments or []:
        department_id = str(department.get("id") or "").strip()
        if not department_id:
            continue
        parent_id = str(department.get("parentid") or "").strip()
        if parent_id not in visible_id_set and department_id not in roots:
            roots.append(department_id)
    return roots


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
        except (ValueError, requests.Timeout, requests.RequestException) as error:
            return None, _map_wecom_request_exception(
                error,
                timeout_message="WeCom directory request timed out",
                invalid_message="WeCom directory response is invalid",
                request_failed_message="WeCom directory request failed",
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
