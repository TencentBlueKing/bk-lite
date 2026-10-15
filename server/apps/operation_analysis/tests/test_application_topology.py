import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException
from apps.operation_analysis.services.application_topology import ApplicationTopologyError, ApplicationTopologyService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HOST_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MONITOR_ID = "monitor-1"
SECRET = "super-secret-nats-payload"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _topology():
    return {
        "result": True,
        "data": {
            "center": {"id": CENTER_UUID, "name": "系统甲", "model_id": "system", "hop": 0, "category": "application", "app_topo_layer": "system"},
            "nodes": [
                {"id": CENTER_UUID, "name": "系统甲", "model_id": "system", "hop": 0, "category": "application", "app_topo_layer": "system"},
                {"id": HOST_UUID, "name": "host-01", "model_id": "host", "hop": 1, "category": "host", "app_topo_layer": "host"},
            ],
            "links": [{"id": "edge-1", "source": CENTER_UUID, "target": HOST_UUID}],
        },
    }


class _Cmdb:
    def application_resource_topology_by_uuid(self, **kwargs):
        return _topology()

    def get_monitor_ids_by_inst_uuids(self, **kwargs):
        return {
            "result": True,
            "data": {
                "items": [
                    {"inst_uuid": CENTER_UUID, "monitor_id": ""},
                    {"inst_uuid": HOST_UUID, "monitor_id": MONITOR_ID},
                ]
            },
        }


class _Monitor:
    def __init__(self, summaries):
        self.ingest_client = self
        self.summaries = summaries

    def run(self, name, query_data=None, user_info=None):
        assert name == "query_latest_active_alerts"
        assert SECRET not in json.dumps(query_data)
        return {"result": True, "data": {"instance_summaries": self.summaries, "secret": SECRET}}


def test_application_topology_overlay_distinguishes_unmonitored_and_quiet(monkeypatch):
    monkeypatch.setattr("apps.operation_analysis.services.application_topology.CMDB", lambda: _Cmdb())
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.Monitor",
        lambda: _Monitor([{"instance_id": MONITOR_ID, "count": 0, "max_level": None}]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.build_nats_user_info",
        lambda request: {"user": "alice"},
    )
    result = ApplicationTopologyService.build(SimpleNamespace(), CENTER_UUID, 3)
    by_id = {node["id"]: node for node in result["nodes"]}
    assert by_id[CENTER_UUID]["alert_count"] is None
    assert by_id[CENTER_UUID]["monitor_id"] == ""
    assert by_id[HOST_UUID]["alert_count"] == 0
    assert by_id[HOST_UUID]["monitor_id"] == MONITOR_ID
    assert SECRET not in json.dumps(result)


def test_application_topology_missing_summary_stays_unknown(monkeypatch):
    monkeypatch.setattr("apps.operation_analysis.services.application_topology.CMDB", lambda: _Cmdb())
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.Monitor",
        lambda: _Monitor([]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.build_nats_user_info",
        lambda request: {"user": "alice"},
    )
    result = ApplicationTopologyService.build(SimpleNamespace(), CENTER_UUID, 3)
    host = next(node for node in result["nodes"] if node["id"] == HOST_UUID)
    assert host["monitor_id"] == MONITOR_ID
    assert host["alert_count"] is None
    assert host["max_level"] is None


def test_application_topology_view_rejects_bad_depth():
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/application_topology/",
        {"inst_uuid": CENTER_UUID, "depth": 6},
        format="json",
    )
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True, is_superuser=True, username="alice"))
    response = SceneWidgetViewSet.as_view({"post": "application_topology"})(request)
    assert response.status_code == 400


def test_application_topology_view_maps_unsupported_model(monkeypatch):
    def fail(request, inst_uuid, depth):
        raise ApplicationTopologyError("unsupported_model")

    monkeypatch.setattr(ApplicationTopologyService, "build", staticmethod(fail))
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/application_topology/",
        {"inst_uuid": CENTER_UUID},
        format="json",
    )
    force_authenticate(request, user=SimpleNamespace(is_authenticated=True, is_superuser=True, username="alice"))
    response = SceneWidgetViewSet.as_view({"post": "application_topology"})(request)
    body = _render(response)
    assert response.status_code == 400
    assert body["result"] is False
    assert "应用拓扑仅支持" in body["message"]


def test_application_topology_blank_count_stays_unknown(monkeypatch):
    monkeypatch.setattr("apps.operation_analysis.services.application_topology.CMDB", lambda: _Cmdb())
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.Monitor",
        lambda: _Monitor([{"instance_id": MONITOR_ID, "count": "", "max_level": "critical", "secret": SECRET}]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.build_nats_user_info",
        lambda request: {"user": "alice"},
    )
    result = ApplicationTopologyService.build(SimpleNamespace(), CENTER_UUID, 3)
    host = next(node for node in result["nodes"] if node["id"] == HOST_UUID)
    assert host["alert_count"] is None
    assert host["max_level"] is None
    assert SECRET not in json.dumps(result)


def test_application_topology_source_failure_logs_once_without_payload(monkeypatch, caplog):
    original = RuntimeError(f"nats unavailable {SECRET}")

    class BoomCmdb:
        def application_resource_topology_by_uuid(self, **kwargs):
            raise original

    monkeypatch.setattr("apps.operation_analysis.services.application_topology.CMDB", lambda: BoomCmdb())
    monkeypatch.setattr(
        "apps.operation_analysis.services.application_topology.build_nats_user_info",
        lambda request: {"user": "alice", "token": SECRET},
    )

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(ApplicationTopologyError) as exc_info:
            ApplicationTopologyService.build(SimpleNamespace(), CENTER_UUID, 3)

    assert exc_info.value.code == "source_failure"
    assert SECRET not in str(exc_info.value)
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=application_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    assert record.args == ("topology", "RuntimeError", CENTER_UUID)
    assert record.exc_info[0] is SafeLogException
    assert str(record.exc_info[1]) == "RuntimeError"
    assert record.exc_info[2] is original.__traceback__
    rendered = record.getMessage()
    rendered = f"{rendered}\n{logging.Formatter().formatException(record.exc_info)}"
    assert SECRET not in rendered
    assert SECRET not in caplog.text
