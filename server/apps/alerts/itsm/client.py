import json
import os
import tempfile
import time
from contextlib import ExitStack
from urllib.parse import quote

import requests

from apps.alerts.itsm.config import ItsmError, validate_response_contract
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


def _layout_fields(layout):
    found = []

    def walk(nodes):
        if isinstance(nodes, dict):
            nodes = nodes.get("children") or nodes.get("list") or [nodes]
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            kind = str(node.get("type") or "")
            if kind in _LAYOUT_SKIP:
                walk(node.get("children") or node.get("list") or [])
                continue
            key = node.get("key")
            if isinstance(key, str) and key:
                found.append({"key": key, "name": str(node.get("name") or node.get("label") or key)[:128], "type": kind[:64]})
            walk(node.get("children") or node.get("list") or [])

    walk(layout or [])
    return found


class ItsmClient:
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
            guard_target = self._token is not None or bool(self.connection.get("credential_id"))
            if guard_target:
                SSRFValidator.validate(url)
            with ExitStack() as stack:
                session = stack.enter_context(requests.Session())
                verify = self.connection.get("ca_bundle") or True
                if self.connection.get("ca_pem"):
                    certificate = stack.enter_context(tempfile.NamedTemporaryFile(mode="w+", suffix=".pem"))
                    certificate.write(self.connection["ca_pem"])
                    certificate.flush()
                    verify = certificate.name
                session.trust_env = False
                session.mount("https://", deadline_adapter(started + 30, guard_url=url if guard_target else None))
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
        data = self._request(
            "POST",
            "ticket_create/",
            {"workflow_key": workflow_key, "is_submit": True, "form_data": fields},
        )
        ticket_id = _path(data, self.connection["create_id_path"])
        if isinstance(ticket_id, bool) or not isinstance(ticket_id, (str, int)) or not str(ticket_id) or len(str(ticket_id)) > 128:
            raise ItsmError("建单响应缺少有效工单 ID，需核查", "unknown")
        return str(ticket_id)

    def detail(self, ticket_id):
        validate_response_contract(self.connection)
        data = self._request("GET", "ticket_detail/" + quote(str(ticket_id), safe="") + "/")
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
        self._request("POST", "ticket_comment/", {"ticket": str(ticket_id), "content": content})

    def services(self):
        data = self._request("GET", "service_catalog/")
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise ItsmError("ITSM 响应格式异常", "failed")
        found = []
        for item in results:
            if not isinstance(item, dict) or item.get("enabled") is False:
                continue
            workflow_key = item.get("workflow_key")
            if not isinstance(workflow_key, str) or not workflow_key.strip() or len(workflow_key) > 200:
                continue
            label = item.get("display") or item.get("service_name") or workflow_key
            found.append({"workflow_key": workflow_key.strip(), "label": str(label)[:200]})
        return found

    def form_fields(self, workflow_key):
        data = self._request("GET", "ticket_form/?workflow_key=" + quote(str(workflow_key), safe=""))
        return _layout_fields(_path(data, "canvas_data.form_data.layout"))

    def test_connection(self):
        self._request("GET", "ticket_list/?page=1&page_size=1")
