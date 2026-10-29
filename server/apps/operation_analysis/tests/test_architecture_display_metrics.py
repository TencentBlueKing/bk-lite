import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException
from apps.operation_analysis.services.architecture_display_metrics import ArchitectureDisplayMetricsService
from apps.operation_analysis.services.architecture_node_status import MAX_INST_UUIDS
from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet
from apps.operation_analysis.views.view import ArchitectureModelViewSet

SECRET = "super-secret-display-metrics"
USER_INFO = {"user": "alice", "team": 1, "domain": "domain.com"}


def _uuid(index: int) -> str:
    return f"00000000-0000-4000-8000-{index:012d}"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _patch_user(monkeypatch, user_info=None):
    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_display_metrics.build_nats_user_info",
        lambda request: user_info or USER_INFO,
    )


def _cmdb(monkeypatch, handler):
    class _Client:
        def get_monitor_ids_by_inst_uuids(self, **kwargs):
            return handler(**kwargs)

    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_display_metrics.CMDB",
        lambda: _Client(),
    )


def _monitor(monkeypatch, handler):
    class _Client:
        def query_instance_display_metrics(self, **kwargs):
            return handler(**kwargs)

    monkeypatch.setattr(
        "apps.operation_analysis.services.architecture_display_metrics.Monitor",
        lambda: _Client(),
    )


def _mapping(*rows, forbidden=None):
    return {
        "result": True,
        "data": {"items": list(rows), "forbidden_inst_uuids": forbidden or []},
    }


def _metrics(requested_id, object_id="12", values=None, columns=None):
    return {
        "result": True,
        "data": {
            "objects": {
                object_id: {
                    "columns": columns or [{"name": "CPU使用率", "keys": ["os::cpu_usage_total"]}],
                }
            },
            "items": [
                {
                    "requested_id": requested_id,
                    "instance_id": requested_id,
                    "monitor_object_id": object_id,
                    "values": values if values is not None else {"os::cpu_usage_total": {"value": "1", "unit": "%"}},
                }
            ],
        },
    }


def _query(monkeypatch, inst_uuids, cmdb, monitor):
    _patch_user(monkeypatch)
    _cmdb(monkeypatch, cmdb)
    _monitor(monkeypatch, monitor)
    return ArchitectureDisplayMetricsService.query(SimpleNamespace(), inst_uuids)


def test_maps_monitor_values_back_to_inst_uuid(monkeypatch):
    inst_uuid = _uuid(1)
    captured = {}

    def cmdb(**kwargs):
        assert kwargs["user_info"] == USER_INFO
        return _mapping(
            {
                "inst_uuid": inst_uuid,
                "monitor_id": "mon-1",
                "model_id": "host",
                "inst_name": "web-01",
            }
        )

    def monitor(**kwargs):
        captured["ids"] = kwargs["instance_ids"]
        assert kwargs["user_info"] == USER_INFO
        return _metrics("mon-1")

    payload = _query(monkeypatch, [inst_uuid], cmdb, monitor)
    assert captured["ids"] == ["mon-1"]
    assert payload["objects"]["12"]["columns"][0]["name"] == "CPU使用率"
    assert payload["items"] == [
        {
            "inst_uuid": inst_uuid,
            "monitor_object_id": "12",
            "values": {"os::cpu_usage_total": {"value": "1", "unit": "%"}},
        }
    ]


def test_shared_monitor_id_is_queried_once(monkeypatch):
    first = _uuid(2)
    second = _uuid(3)
    captured = {}

    def cmdb(**kwargs):
        return _mapping(
            {"inst_uuid": first, "monitor_id": "mon-shared"},
            {"inst_uuid": second, "monitor_id": "mon-shared"},
        )

    def monitor(**kwargs):
        captured["ids"] = kwargs["instance_ids"]
        return _metrics("mon-shared")

    payload = _query(monkeypatch, [first, second], cmdb, monitor)
    assert captured["ids"] == ["mon-shared"]
    assert [item["inst_uuid"] for item in payload["items"]] == [first, second]


def test_empty_monitor_and_forbidden_are_omitted(monkeypatch):
    kept = _uuid(4)
    empty = _uuid(5)
    forbidden = _uuid(6)
    called = {"monitor": False}

    def cmdb(**kwargs):
        return _mapping(
            {"inst_uuid": kept, "monitor_id": "mon-4"},
            {"inst_uuid": empty, "monitor_id": ""},
            {"inst_uuid": forbidden, "monitor_id": "mon-hidden"},
            forbidden=[forbidden],
        )

    def monitor(**kwargs):
        called["monitor"] = True
        assert kwargs["instance_ids"] == ["mon-4"]
        return _metrics("mon-4")

    payload = _query(monkeypatch, [kept, empty, forbidden], cmdb, monitor)
    assert called["monitor"] is True
    assert [item["inst_uuid"] for item in payload["items"]] == [kept]


def test_monitor_failure_omits_values_and_logs_once(monkeypatch, caplog):
    inst_uuid = _uuid(7)

    def cmdb(**kwargs):
        return _mapping({"inst_uuid": inst_uuid, "monitor_id": "mon-7"})

    def monitor(**kwargs):
        raise RuntimeError(f"metrics down {SECRET}")

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        payload = _query(monkeypatch, [inst_uuid], cmdb, monitor)

    assert payload == {"objects": {}, "items": []}
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == ("event=architecture_display_metrics_batch_failed failed_stage=%s error_type=%s batch_index=%s batch_size=%s")
    assert record.args == ("display_metrics", "RuntimeError", 0, 1)
    assert record.exc_info[0] is SafeLogException
    rendered = f"{record.getMessage()}\n{logging.Formatter().formatException(record.exc_info)}"
    assert SECRET not in rendered
    assert SECRET not in json.dumps(payload)


def test_false_nats_result_has_no_traceback(monkeypatch, caplog):
    inst_uuid = _uuid(8)

    def cmdb(**kwargs):
        return _mapping({"inst_uuid": inst_uuid, "monitor_id": "mon-8"})

    def monitor(**kwargs):
        return {"result": False, "data": {}, "message": SECRET}

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        payload = _query(monkeypatch, [inst_uuid], cmdb, monitor)

    assert payload["items"] == []
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].args[1] == "NatsResultFalse"
    assert error_records[0].exc_info is None
    assert SECRET not in error_records[0].getMessage()


def test_non_list_and_over_limit_are_rejected(monkeypatch):
    called = {"cmdb": False}

    def cmdb(**kwargs):
        called["cmdb"] = True
        return _mapping()

    _patch_user(monkeypatch)
    _cmdb(monkeypatch, cmdb)
    with pytest.raises(ValidationError):
        ArchitectureDisplayMetricsService.query(SimpleNamespace(), "not-a-list")
    with pytest.raises(ValidationError):
        ArchitectureDisplayMetricsService.query(SimpleNamespace(), [_uuid(index) for index in range(MAX_INST_UUIDS + 1)])
    assert called["cmdb"] is False


def test_view_returns_items_and_share_has_no_endpoint(monkeypatch):
    inst_uuid = _uuid(9)

    def query(request, inst_uuids):
        assert inst_uuids == [inst_uuid]
        return {"objects": {}, "items": [{"inst_uuid": inst_uuid, "monitor_object_id": "12", "values": {}}]}

    monkeypatch.setattr(ArchitectureDisplayMetricsService, "query", staticmethod(query))
    request = APIRequestFactory().post(
        "/operation_analysis/api/architecture/display_metrics/",
        {"inst_uuids": [inst_uuid]},
        format="json",
    )
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True, is_superuser=True, username="alice", locale="zh"))
    response = ArchitectureModelViewSet.as_view({"post": "display_metrics"})(request)
    body = _render(response)
    assert response.status_code == 200
    assert body["result"] is True
    assert body["data"]["items"][0]["inst_uuid"] == inst_uuid
    assert not hasattr(DashboardShareAccessViewSet, "display_metrics")


def test_display_metrics_rpc_uses_ingest_client():
    from apps.rpc.monitor import Monitor

    calls = {}

    class _Ingest:
        def run(self, name, **kwargs):
            calls["name"] = name
            calls["kwargs"] = kwargs
            return {"result": True}

    client = Monitor.__new__(Monitor)
    client.ingest_client = _Ingest()
    result = client.query_instance_display_metrics(instance_ids=["a"], user_info={"user": "alice"})
    assert result == {"result": True}
    assert calls == {
        "name": "query_instance_display_metrics",
        "kwargs": {"instance_ids": ["a"], "user_info": {"user": "alice"}},
    }
