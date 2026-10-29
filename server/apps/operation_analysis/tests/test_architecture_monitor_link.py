import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException
from apps.operation_analysis.services.architecture_monitor_link import ArchitectureMonitorLinkService
from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet
from apps.operation_analysis.views.view import ArchitectureModelViewSet

SECRET = "super-secret-monitor-link"
USER_INFO = {"user": "alice", "team": 1, "domain": "domain.com", "locale": "en", "is_superuser": False}
REQUEST = SimpleNamespace()
MONITOR_ID = "('web-01',)"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _patch_user(monkeypatch, user_info=None):
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_monitor_link.build_nats_user_info",
        lambda request: user_info or USER_INFO,
    )


def _monitor(monkeypatch, **methods):
    class _Client:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def _missing(**kwargs):
                self.calls.append((name, kwargs))
                handler = methods.get(name)
                if handler is None:
                    raise AssertionError(name)
                return handler(**kwargs)

            return _missing

    client = _Client()
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_monitor_link.Monitor",
        lambda: client,
    )
    return client


def _auth(request, *, superuser):
    force_authenticate(
        request,
        user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=superuser,
            username="alice" if superuser else "bob",
            locale="zh",
            permission={} if not superuser else {"view-View": ["*"]},
        ),
    )


def _get(monitor_id="mon-1", *, superuser=True, query=None):
    params = {"monitor_id": monitor_id} if query is None else query
    request = APIRequestFactory().get("/operation_analysis/api/architecture/monitor_link/", params)
    _auth(request, superuser=superuser)
    return ArchitectureModelViewSet.as_view({"get": "monitor_link"})(request)


def _lookup(**overrides):
    payload = {
        "monitor_object": {
            "id": 11,
            "name": "Host",
            "display_name": "主机",
            "instance_id_keys": ["instance_id"],
        },
        "instance": {
            "instance_id": MONITOR_ID,
            "instance_name": "web-01",
            "instance_id_values": ["web-01"],
            "instance_id_keys": ["instance_id"],
        },
    }
    payload.update(overrides)
    return payload


def test_success_calls_both_rpcs_and_returns_link_context(monkeypatch):
    plugins = [{"id": 7, "name": "Host", "collect_type": "netflow", "token": SECRET}]

    def lookup_monitor_instance(**kwargs):
        assert kwargs == {"instance_id": MONITOR_ID, "user_info": USER_INFO}
        return {"result": True, "data": _lookup()}

    def get_monitor_effective_plugins(**kwargs):
        assert kwargs["monitor_object_id"] == 11
        assert kwargs["instance_id"] == MONITOR_ID
        assert kwargs["user_info"] == USER_INFO
        assert kwargs["locale"] == "en"
        return {"result": True, "data": plugins}

    client = _monitor(
        monkeypatch,
        lookup_monitor_instance=lookup_monitor_instance,
        get_monitor_effective_plugins=get_monitor_effective_plugins,
    )
    _patch_user(monkeypatch)
    data = ArchitectureMonitorLinkService.resolve(REQUEST, f"  {MONITOR_ID}  ")
    assert [name for name, _kwargs in client.calls] == [
        "lookup_monitor_instance",
        "get_monitor_effective_plugins",
    ]
    assert data["monitor_object"]["name"] == "Host"
    assert data["instance"]["instance_name"] == "web-01"
    assert data["plugins"] == plugins


def test_missing_lookup_skips_plugins_and_returns_empty_context(monkeypatch):
    client = _monitor(
        monkeypatch,
        lookup_monitor_instance=lambda **kwargs: {"result": True, "data": None},
    )
    _patch_user(monkeypatch)
    assert ArchitectureMonitorLinkService.resolve(REQUEST, MONITOR_ID) == {
        "monitor_object": None,
        "instance": None,
        "plugins": [],
    }
    assert [name for name, _kwargs in client.calls] == ["lookup_monitor_instance"]


def test_unauthorized_plugins_return_empty_context(monkeypatch):
    client = _monitor(
        monkeypatch,
        lookup_monitor_instance=lambda **kwargs: {"result": True, "data": _lookup()},
        get_monitor_effective_plugins=lambda **kwargs: {"result": True, "data": None},
    )
    _patch_user(monkeypatch)
    assert ArchitectureMonitorLinkService.resolve(REQUEST, MONITOR_ID)["plugins"] == []
    assert ArchitectureMonitorLinkService.resolve(REQUEST, MONITOR_ID)["monitor_object"] is None
    assert [name for name, _kwargs in client.calls] == [
        "lookup_monitor_instance",
        "get_monitor_effective_plugins",
        "lookup_monitor_instance",
        "get_monitor_effective_plugins",
    ]


def test_empty_monitor_id_skips_rpc(monkeypatch):
    client = _monitor(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        ArchitectureMonitorLinkService.resolve(REQUEST, "  ")
    assert client.calls == []
    assert "请提供 monitor_id" in str(exc.value.detail)


def test_non_string_monitor_id_skips_rpc(monkeypatch):
    client = _monitor(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        ArchitectureMonitorLinkService.resolve(REQUEST, 11)
    assert client.calls == []
    assert "monitor_id" in exc.value.detail


def test_rpc_exception_is_a_readable_message(monkeypatch, caplog):
    def lookup_monitor_instance(**kwargs):
        raise RuntimeError(f"nats dump {SECRET}")

    _monitor(monkeypatch, lookup_monitor_instance=lookup_monitor_instance)
    _patch_user(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(ValidationError) as exc:
            ArchitectureMonitorLinkService.resolve(REQUEST, MONITOR_ID)
    assert exc.value.detail["detail"] == "监控链接解析失败"
    assert SECRET not in json.dumps(exc.value.detail)
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=architecture_monitor_link_failed failed_stage=%s error_type=%s monitor_id=%s"
    assert record.args[0] == "lookup"
    assert record.args[1] == "RuntimeError"
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[1].__traceback__ is None
    assert record.exc_info[2] is not None
    rendered = f"{record.getMessage()}\n{logging.Formatter().formatException(record.exc_info)}"
    assert SECRET not in rendered


def test_rpc_false_result_does_not_dump_the_body(monkeypatch, caplog):
    def lookup_monitor_instance(**kwargs):
        return {"result": False, "message": SECRET, "data": {"password": SECRET}}

    _monitor(monkeypatch, lookup_monitor_instance=lookup_monitor_instance)
    _patch_user(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(ValidationError) as exc:
            ArchitectureMonitorLinkService.resolve(REQUEST, MONITOR_ID)
    assert exc.value.detail["detail"] == "监控链接解析失败"
    assert SECRET not in json.dumps(exc.value.detail)
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.args[1] == "NatsResultFalse"
    assert record.exc_info is None
    assert SECRET not in record.getMessage()


def test_view_returns_context_and_share_has_no_action(monkeypatch):
    monkeypatch.setattr(
        ArchitectureMonitorLinkService,
        "resolve",
        staticmethod(
            lambda request, monitor_id: {
                "monitor_object": {"id": 11, "name": "Host"},
                "instance": {"instance_id": monitor_id, "instance_name": "web-01"},
                "plugins": [{"name": "Host", "collect_type": "netflow"}],
            }
        ),
    )
    response = _get(MONITOR_ID)
    body = _render(response)
    assert response.status_code == 200
    assert body["result"] is True
    assert body["data"]["monitor_object"]["id"] == 11
    assert body["data"]["plugins"][0]["collect_type"] == "netflow"
    assert body["message"] == "success"
    assert not hasattr(DashboardShareAccessViewSet, "monitor_link")


def test_view_rejects_user_without_architecture_permission():
    assert _get(MONITOR_ID, superuser=False).status_code == 403


def test_view_empty_monitor_id_is_400_without_rpc(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_monitor_link.Monitor",
        lambda: (_ for _ in ()).throw(AssertionError("rpc")),
    )
    response = _get("", query={})
    body = _render(response)
    assert response.status_code == 400
    assert body["result"] is False
    assert "请提供 monitor_id" in body["message"]


def test_monitor_rpc_methods_use_ingest_client():
    from apps.rpc.monitor import Monitor

    calls = []

    class _Ingest:
        def run(self, name, **kwargs):
            calls.append((name, kwargs))
            return {"result": True, "data": None}

    client = Monitor.__new__(Monitor)
    client.ingest_client = _Ingest()
    client.lookup_monitor_instance("mon-1", user_info=USER_INFO)
    client.get_monitor_effective_plugins(11, "mon-1", user_info=USER_INFO, locale="en")
    assert calls == [
        ("lookup_monitor_instance", {"instance_id": "mon-1", "user_info": USER_INFO}),
        (
            "get_monitor_effective_plugins",
            {"monitor_object_id": 11, "instance_id": "mon-1", "user_info": USER_INFO, "locale": "en"},
        ),
    ]
