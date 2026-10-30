"""ITSM HTTP 契约：只替换外部 HTTP，不模拟内部解析/校验。"""
import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.alerts.itsm.client import ItsmClient, ItsmError

NATIVE_ROOT = "https://itsm.example/openapi/v1/itsm/openapi/v1"


@pytest.fixture(name="connection")
def itsm_connection():
    return {
        "url": NATIVE_ROOT,
        "token_env": "TEST_ITSM_TOKEN",
        "instance_id": "test-itsm",
        "teams": [1],
        "create_id_path": "id",
        "detail_fields": {
            "id": "id",
            "title": "title",
            "number": "sn",
            "status": "status",
            "end_at": "end_at",
            "label": "status_display",
        },
        "states": {"running": {"label": "处理中", "closed": False}, "termination": {"label": "已终止", "closed": True}},
    }


def response(body, status=200):
    result = MagicMock(status_code=status)
    result.iter_content.return_value = [json.dumps(body).encode()]
    return result


def test_create_preserves_long_id_and_does_not_retry(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    with patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"id": 102026090716182700005102}})
    ) as http:
        assert ItsmClient(connection).create("workflow", {"ticket__title": "CPU 告警"}) == "102026090716182700005102"
        assert http.call_count == 1
        assert http.call_args.args[1] == NATIVE_ROOT + "/ticket/create/"
        assert http.call_args.kwargs["json"]["is_submit"] is True
        assert http.call_args.kwargs["allow_redirects"] is False
        assert http.call_args.kwargs["verify"] is True


@pytest.mark.parametrize("outcome", [requests.ReadTimeout("SENSITIVE-SENTINEL"), response({"result": True, "data": {}}), response({}, 500)])
def test_uncertain_create_never_becomes_retryable_failure(connection, monkeypatch, outcome):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    with patch("requests.Session.request", side_effect=outcome if isinstance(outcome, Exception) else None, return_value=outcome):
        with pytest.raises(ItsmError) as error:
            ItsmClient(connection).create("wf", {"ticket__title": "test"})
        assert error.value.outcome == "unknown"
        assert "SENSITIVE-SENTINEL" not in str(error.value)


def test_unknown_status_without_end_at_is_not_closed(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "secret")
    with patch(
        "requests.Session.request",
        return_value=response({"code": "20000", "data": {"id": "123", "status": "suspend", "status_display": "处理中"}}),
    ) as http:
        detail = ItsmClient(connection).detail("123")
    assert http.call_args.args[1] == NATIVE_ROOT + "/ticket/detail/?id=123"
    assert detail["is_closed"] is False
    assert detail["status_label"] == "处理中"


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 500])
def test_non_success_detail_never_counts_as_ticket_close(connection, monkeypatch, status):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    with patch("requests.Session.request", return_value=response({"result": False, "message": "SENSITIVE-SENTINEL"}, status)):
        with pytest.raises(ItsmError) as error:
            ItsmClient(connection).detail("123")
        assert "SENSITIVE-SENTINEL" not in str(error.value)


def test_service_catalog_keeps_enabled_services_and_display_label(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    body = {
        "code": "20000",
        "data": {
            "results": [
                {"name": "终端服务 / 个人电脑或外设申请与更换", "workflow_id": "20261008185800000809", "enabled": True},
                {"name": "停用服务", "workflow_id": "disabled", "enabled": False},
                {"name": "未绑定流程", "workflow_id": "  ", "enabled": True},
            ]
        },
    }
    with patch("requests.Session.request", return_value=response(body)) as http:
        assert ItsmClient(connection).services() == [{"workflow_key": "20261008185800000809", "label": "终端服务 / 个人电脑或外设申请与更换"}]
    assert http.call_args.args[1] == NATIVE_ROOT + "/service_catalog/service_list/"


def test_oversized_response_is_bounded_unknown(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "secret")
    large = response({})
    large.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
    with patch("requests.Session.request", return_value=large), pytest.raises(ItsmError) as error:
        ItsmClient(connection).create("wf", {})
    assert error.value.outcome == "unknown"


def test_slow_socket_does_not_extend_total_read_deadline():
    from apps.alerts.itsm.transport import DeadlineReader

    sock = MagicMock()
    sock.recv_into.return_value = 1
    reader = DeadlineReader(sock, deadline=30)
    with patch("apps.alerts.itsm.transport.time.monotonic", side_effect=[0, 19, 29, 31]):
        assert reader.readinto(bytearray(8192)) == 1
        assert reader.readinto(bytearray(8192)) == 1
        assert reader.readinto(bytearray(8192)) == 1
        with pytest.raises(TimeoutError):
            reader.readinto(bytearray(8192))
    assert sock.settimeout.call_args_list[-1].args == (1,)
    assert sock.recv_into.call_count == 3


def test_deadline_socket_keeps_response_file_alive_after_socket_close():
    import http.client
    import socket
    import time

    from apps.alerts.itsm.transport import DeadlineSocket

    reader, writer = socket.socketpair()
    try:
        writer.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
        response = http.client.HTTPResponse(DeadlineSocket(reader, time.monotonic() + 2))
        response.begin()
        reader.close()
        assert response.read() == b"{}"
        response.close()
    finally:
        reader.close()
        writer.close()


def test_end_at_displays_ticket_closed_without_changing_meaning_of_alert(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "secret")
    body = {"code": "20000", "data": {"id": "123", "status": "finished", "status_display": "已完成", "end_at": "2026-10-27T10:00:00+08:00"}}
    with patch("requests.Session.request", return_value=response(body)):
        detail = ItsmClient(connection).detail("123")
    assert detail["is_closed"] is True
    assert detail["status_label"] == "工单已关闭"


def test_incomplete_contract_blocks_ticket_requests_before_http():
    client = ItsmClient({"url": "https://itsm.example/api", "detail_fields": {"id": "ticket.id"}})
    with patch("requests.Session.request") as http, pytest.raises(ItsmError, match="接口联调") as error:
        client.create("workflow", {"ticket__title": "告警"})
    assert error.value.outcome == "config_error"
    http.assert_not_called()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (requests.exceptions.SSLError("SENSITIVE-SENTINEL"), "证书"),
        (requests.exceptions.ReadTimeout("SENSITIVE-SENTINEL"), "超时"),
        (requests.exceptions.ConnectionError("SENSITIVE-SENTINEL"), "网络连接"),
    ],
)
@pytest.mark.parametrize("operation,outcome", [("test_connection", "failed"), ("create", "unknown")])
def test_connection_failure_has_actionable_safe_reason(connection, monkeypatch, failure, expected, operation, outcome):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    with patch("requests.Session.request", side_effect=failure) as http, pytest.raises(ItsmError) as error:
        client = ItsmClient(connection)
        if operation == "create":
            client.create("wf", {"ticket__title": "test"})
        else:
            client.test_connection()
    assert expected in str(error.value)
    assert "SENSITIVE-SENTINEL" not in str(error.value)
    assert error.value.outcome == outcome
    http.assert_called_once()


@pytest.mark.parametrize("status,expected", [(401, "认证失败"), (403, "权限不足"), (404, "接口不存在"), (302, "重定向"), (503, "服务异常")])
def test_connection_http_errors_are_clear_even_for_non_json_body(connection, monkeypatch, status, expected):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    remote = response({}, status)
    remote.iter_content.return_value = [b"<html>SENSITIVE-SENTINEL</html>"]
    with patch("requests.Session.request", return_value=remote), pytest.raises(ItsmError) as error:
        ItsmClient(connection).test_connection()
    assert expected in str(error.value)
    assert "SENSITIVE-SENTINEL" not in str(error.value)
    assert error.value.outcome == "failed"


@pytest.mark.parametrize("operation,outcome", [("test_connection", "failed"), ("create", "unknown")])
def test_non_json_success_response_does_not_leak_or_allow_blind_retry(connection, monkeypatch, operation, outcome):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    remote = response({})
    remote.iter_content.return_value = [b"<html>SENSITIVE-SENTINEL</html>"]
    with patch("requests.Session.request", return_value=remote) as http, pytest.raises(ItsmError) as error:
        client = ItsmClient(connection)
        if operation == "create":
            client.create("wf", {"ticket__title": "test"})
        else:
            client.test_connection()
    assert "JSON" in str(error.value)
    assert "SENSITIVE-SENTINEL" not in str(error.value)
    assert error.value.outcome == outcome
    http.assert_called_once()


def test_form_fields_read_layout_from_workflow_version(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "secret")
    body = {
        "code": "20000",
        "data": {
            "items": [
                {
                    "workflow_key": "wf-1",
                    "form_canvas_data": {
                        "form_data": {
                            "layout": [
                                {"type": "row", "children": [{"type": "input", "key": "ticket__title", "name": "标题"}]},
                                {"type": "textarea", "key": "content", "label": "描述"},
                            ]
                        }
                    },
                }
            ]
        },
    }
    with patch("requests.Session.request", return_value=response(body)) as http:
        fields = ItsmClient(connection).form_fields("wf-1")
    assert http.call_args.args[1] == NATIVE_ROOT + "/workflows/?workflow_keys=wf-1"
    assert fields == [
        {"key": "ticket__title", "name": "标题", "type": "input"},
        {"key": "content", "name": "描述", "type": "textarea"},
    ]


def test_gateway_loopback_survives_missing_async_callback(monkeypatch):
    monkeypatch.setitem(sys.modules, "apps.core.openapi.async_callback", None)
    sys.modules.pop("apps.alerts.itsm.gateway_loopback", None)
    try:
        mod = importlib.import_module("apps.alerts.itsm.gateway_loopback")
        url = "https://10.11.10.182/openapi/v1/itsm/openapi/v1/ticket/list/"
        assert mod.rewrite_gateway_callback_url(url) == url
        assert mod.callback_tls_verify(url) is True
    finally:
        sys.modules.pop("apps.alerts.itsm.gateway_loopback", None)
        importlib.import_module("apps.alerts.itsm.gateway_loopback")


def test_comment_is_skipped_on_native_openapi(connection, monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "secret")
    with patch("requests.Session.request") as http, pytest.raises(ItsmError, match="留言") as error:
        ItsmClient(connection).comment("123", "告警已关闭")
    assert error.value.outcome == "failed"
    http.assert_not_called()
