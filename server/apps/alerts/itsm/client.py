import json
import os
import tempfile
import time
from contextlib import ExitStack
from urllib.parse import quote

import requests

from apps.alerts.itsm.config import ItsmError, validate_response_contract
from apps.alerts.itsm.gateway_loopback import callback_tls_verify, rewrite_gateway_callback_url
from apps.alerts.itsm.transport import deadline_adapter
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator

MAX_RESPONSE_BYTES = 1024 * 1024
HTTP_TIMEOUT = (5, 20)


def _path(data, path):
    if not path:
        return None
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


_LAYOUT_SKIP = {"row", "group", "tab", "tab-panel"}


def _layout_nodes(layout):
    """按表单布局顺序产出带 key 的字段节点，跳过行/分组等容器。"""

    def walk(nodes):
        if isinstance(nodes, dict):
            nodes = nodes.get("children") or nodes.get("list") or [nodes]
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            key = node.get("key")
            if str(node.get("type") or "") not in _LAYOUT_SKIP and isinstance(key, str) and key:
                yield node
            yield from walk(node.get("children") or node.get("list") or [])

    yield from walk(layout or [])


def _node_label(node):
    title = node.get("title")
    title = title.get("value") if isinstance(title, dict) else title
    return str(node.get("name") or node.get("label") or title or node["key"])[:128]


def _node_required(node):
    rule = _path(node, "verification.required")
    return isinstance(rule, dict) and rule.get("value") is True and rule.get("enabled") is not False


def _node_options(node):
    choices = node.get("optionList")
    if not isinstance(choices, list):
        return []
    return [
        {"key": item["key"], "name": str(item.get("name") or item["key"])[:128]}
        for item in choices
        if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"]
    ]


def _layout_fields(layout):
    return [
        {
            "key": node["key"],
            "name": _node_label(node),
            "type": str(node.get("type") or "")[:64],
            "required": _node_required(node),
            "options": _node_options(node),
        }
        for node in _layout_nodes(layout)
    ]


def _apply_selected_options(layout, fields):
    """ITSM 按调用方提交的 options 校验选项值；常量允许填选项名，这里统一换成选项 key。"""
    options = {}
    for node in _layout_nodes(layout):
        key, choices = node["key"], node.get("optionList")
        if key not in fields or not isinstance(choices, list):
            continue
        choices = [item for item in choices if isinstance(item, dict) and isinstance(item.get("key"), str)]
        by_key = {item["key"]: item for item in choices}
        by_name = {str(item["name"]): item for item in choices if item.get("name") is not None}
        values = fields[key] if isinstance(fields[key], list) else [fields[key]]
        if not values or not all(isinstance(value, str) and value for value in values):
            continue
        chosen = [by_key.get(value) or by_name.get(value) for value in values]
        if None in chosen:
            continue
        options[key] = [{"key": item["key"], "name": str(item.get("name") or item["key"]), "parent": None} for item in chosen]
        keys = [item["key"] for item in chosen]
        fields[key] = keys if isinstance(fields[key], list) else keys[0]
    return options


class ItsmClient:
    supports_comment = False

    def __init__(self, connection, *, allow_disabled=False, token=None):
        self.connection = connection
        self.allow_disabled = allow_disabled
        self._token = token  # 表单探测的临时凭据，仅驻留本次请求内存。

    def _request(self, method, path, payload=None):
        if self._token is not None:
            token = self._token
        elif self.connection.get("credential_id"):
            from apps.alerts.itsm.integration import resolve_token

            token = resolve_token(self.connection["credential_id"], allow_disabled=self.allow_disabled, expected_url=self.connection["url"])
        else:
            token = os.getenv(self.connection.get("token_env", ""))
        if not token:
            raise ItsmError("ITSM 认证凭据未配置")
        outcome = "unknown" if method == "POST" else "failed"
        started = time.monotonic()
        try:
            # requests 默认不重试；禁用环境代理和重定向，凭据只发往部署指定的网关。
            url = self.connection["url"].rstrip("/") + "/" + path
            rewritten = rewrite_gateway_callback_url(url)
            loopback = rewritten != url
            url = rewritten
            guard_target = self._token is not None or bool(self.connection.get("credential_id"))
            if guard_target:
                if loopback:
                    SSRFValidator.validate_callback(url)
                else:
                    SSRFValidator.validate(url)
            with ExitStack() as stack:
                session = stack.enter_context(requests.Session())
                verify = self.connection.get("ca_bundle") or True
                if self.connection.get("ca_pem"):
                    certificate = stack.enter_context(tempfile.NamedTemporaryFile(mode="w+", suffix=".pem"))
                    certificate.write(self.connection["ca_pem"])
                    certificate.flush()
                    verify = certificate.name
                elif loopback:
                    verify = callback_tls_verify(url)
                session.trust_env = False
                session.mount("https://", deadline_adapter(started + 30, guard_url=None if loopback else (url if guard_target else None)))
                response = session.request(
                    method,
                    url,
                    json=payload,
                    headers={"Authorization": "Bearer " + token},
                    timeout=HTTP_TIMEOUT,
                    verify=verify,
                    allow_redirects=False,
                    stream=True,
                )
                with response:
                    # 只读探测先识别 HTTP 错误，避免网关 HTML 覆盖真正原因。
                    # POST 仍沿用下方业务拒绝判断，保持结果不明时禁止重发。
                    if method == "GET" and response.status_code != 200:
                        reason = {
                            401: "ITSM 认证失败（HTTP 401），请检查令牌是否有效或已过期",
                            403: "ITSM 接口权限不足（HTTP 403），请检查集成账号权限",
                            404: "ITSM 接口不存在（HTTP 404），请检查完整 API 根地址及网关路由",
                        }.get(response.status_code)
                        if reason is None:
                            if 300 <= response.status_code < 400:
                                reason = "ITSM 返回重定向，请填写最终 API 根地址；认证请求不跟随跳转"
                            elif response.status_code >= 500:
                                reason = "ITSM 网关或服务异常，请检查 ITSM 服务状态"
                            else:
                                reason = "ITSM 接口请求失败，请检查 API 地址及接口访问限制"
                        raise ItsmError(reason, "failed")
                    body = bytearray()
                    for chunk in response.iter_content(8192):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES or time.monotonic() - started > 30:
                            raise ItsmError("ITSM 响应超过调用预算", outcome)
                        body.extend(chunk)
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ItsmError("ITSM 响应格式异常", outcome)
                    code = str(data.get("code") or "")
                    if response.status_code in {400, 401, 403} and code in {"40000", "40100", "40300"}:
                        raise ItsmError("ITSM 拒绝请求，请检查表单及连接权限", "failed")
                    comment_ok = response.status_code == 201 and code == "20100"
                    query_ok = response.status_code == 200 and code == "20000" and data.get("result") is not False
                    if not comment_ok and not query_ok:
                        raise ItsmError("ITSM 未返回有效成功结果", outcome)
                    return data.get("data")
        except SSRFError:
            raise ItsmError("ITSM 目标不符合网络访问策略，请检查系统内网白名单", "config_error") from None
        except requests.exceptions.SSLError:
            raise ItsmError("ITSM TLS 校验失败，请检查受信 CA 证书、服务端证书链、有效期及访问地址是否与证书匹配", outcome) from None
        except requests.exceptions.Timeout:
            raise ItsmError("ITSM 请求超时，请检查告警服务到 ITSM 的网络及服务响应", outcome) from None
        except requests.exceptions.ConnectionError:
            raise ItsmError("ITSM 网络连接失败或中断，请检查告警服务到目标地址的网络及端口", outcome) from None
        except requests.RequestException:
            raise ItsmError("ITSM HTTP 请求失败，请检查网关地址和服务配置", outcome) from None
        except (ValueError, TypeError):
            raise ItsmError("ITSM 响应不是有效的 JSON，请检查 API 根地址及网关路由", outcome) from None

    def create(self, workflow_key, fields):
        validate_response_contract(self.connection)
        prepared = dict(fields)
        try:
            options = _apply_selected_options(self._form_layout(workflow_key), prepared)
            fields = prepared
        except Exception:
            # 读不到或解析不了表单只影响选项校验，交给 ITSM 明确拒绝；不能因此放弃这次建单。
            options = {}
        data = self._request(
            "POST",
            "ticket/create/",
            {"workflow_key": workflow_key, "is_submit": True, "form_data": fields, "options": options},
        )
        ticket_id = _path(data, self.connection["create_id_path"])
        if isinstance(ticket_id, bool) or not isinstance(ticket_id, (str, int)) or not str(ticket_id) or len(str(ticket_id)) > 128:
            raise ItsmError("建单响应缺少有效工单 ID，需核查", "unknown")
        return str(ticket_id)

    def detail(self, ticket_id):
        validate_response_contract(self.connection)
        data = self._request("GET", "ticket/detail/?id=" + quote(str(ticket_id), safe=""))
        fields = self.connection["detail_fields"]
        actual_id = _path(data, fields["id"])
        if str(actual_id) != str(ticket_id):
            raise ItsmError("ITSM 工单 ID 校验失败", "failed")
        raw_status = _path(data, fields["status"])
        ended = bool(_path(data, fields.get("end_at", "ticket.end_at")))
        label = _path(data, fields.get("label", "ticket.status_display"))
        return {
            "ticket_id": str(actual_id),
            "ticket_number": str(_path(data, fields.get("number", "")) or "")[:128],
            "ticket_title": str(_path(data, fields.get("title", "")) or "")[:500],
            "ticket_status": str(raw_status or "")[:128],
            "status_label": "工单已关闭" if ended else str(label or raw_status or "")[:128],
            "is_closed": ended,
        }

    def comment(self, ticket_id, content):
        raise ItsmError("ITSM 原生 OpenAPI 暂不支持工单留言", "failed")

    def services(self):
        data = self._request("GET", "service_catalog/service_list/")
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise ItsmError("ITSM 响应格式异常", "failed")
        found = []
        for item in results:
            if not isinstance(item, dict) or item.get("enabled") is False:
                continue
            workflow_key = item.get("workflow_id") or item.get("workflow_key")
            if not isinstance(workflow_key, str) or not workflow_key.strip() or len(workflow_key) > 200:
                continue
            label = item.get("workflow_display") or item.get("name") or item.get("display") or item.get("service_name")
            label = label or workflow_key
            found.append({"workflow_key": workflow_key.strip(), "label": str(label)[:200]})
        return found

    def _form_layout(self, workflow_key):
        data = self._request("GET", "workflows/?workflow_keys=" + quote(str(workflow_key), safe=""))
        items = data.get("items") if isinstance(data, dict) else None
        canvas = items[0].get("form_canvas_data") if isinstance(items, list) and items and isinstance(items[0], dict) else {}
        return _path(canvas if isinstance(canvas, dict) else {}, "form_data.layout")

    def form_fields(self, workflow_key):
        return _layout_fields(self._form_layout(workflow_key))

    def test_connection(self):
        self._request("GET", "ticket/list/?page=1&page_size=1")
