import inspect
import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.serializers.scene_widget_serializers import RelatedTopologyRequestSerializer
from apps.operation_analysis.services.related_topology import RelatedTopologyError, RelatedTopologyService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
NEIGHBOR_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SECRET_SENTINEL = "super-secret-nats-payload"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _post_request(user, data):
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/related_topology/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _topology_request():
    return SimpleNamespace(
        user=SimpleNamespace(
            username="testuser",
            domain="domain.com",
            locale="en",
            timezone="Asia/Shanghai",
            permission={},
            group_tree=[],
            is_superuser=False,
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def _tree(*, with_neighbor=True, neighbor_name="edge-switch"):
    neighbor = []
    if with_neighbor:
        neighbor = [
            {
                "inst_uuid": NEIGHBOR_UUID,
                "inst_name": neighbor_name,
                "model_id": "switch",
                "model_name": "交换机",
                "asst_id": "connect",
                "children": [],
            }
        ]
    center = {
        "inst_uuid": CENTER_UUID,
        "inst_name": "core-host",
        "model_id": "host",
        "model_name": "主机",
        "children": neighbor,
    }
    return {
        "src_result": center,
        "dst_result": {
            "inst_uuid": CENTER_UUID,
            "inst_name": "core-host",
            "model_id": "host",
            "children": [],
        },
    }


class _FakeCMDB:
    def __init__(self, tree=None, mappings=None, neighbor_result=None, mapping_result=None):
        self.tree = tree if tree is not None else _tree()
        self.mappings = mappings if mappings is not None else []
        self.neighbor_result = neighbor_result
        self.mapping_result = mapping_result
        self.neighbor_calls = []
        self.mapping_calls = []

    def topo_search_lite_by_uuid(self, **kwargs):
        self.neighbor_calls.append(kwargs)
        if self.neighbor_result is not None:
            return self.neighbor_result
        return {"result": True, "data": self.tree, "message": ""}

    def get_monitor_ids_by_inst_uuids(self, **kwargs):
        self.mapping_calls.append(kwargs)
        if self.mapping_result is not None:
            return self.mapping_result
        return {"result": True, "data": {"items": self.mappings}, "message": ""}


class _FakeMonitor:
    def __init__(self, summaries=None, alert_result=None, error=None):
        self.summaries = summaries if summaries is not None else []
        self.alert_result = alert_result
        self.error = error
        self.calls = []
        self.ingest_client = self

    def run(self, method_name, **kwargs):
        self.calls.append((method_name, kwargs))
        if self.error is not None:
            raise self.error
        if self.alert_result is not None:
            return self.alert_result
        return {
            "result": True,
            "data": {"count": 0, "max_level": None, "items": [], "instance_summaries": self.summaries},
            "message": "",
        }


def _install(monkeypatch, cmdb, monitor=None):
    monkeypatch.setattr("apps.operation_analysis.services.related_topology.CMDB", lambda: cmdb)
    monkeypatch.setattr(
        "apps.operation_analysis.services.related_topology.Monitor",
        lambda: monitor or _FakeMonitor(),
    )


def test_request_serializer_accepts_single_uuid_and_rejects_legacy_payloads():
    serializer = RelatedTopologyRequestSerializer(data={"inst_uuid": CENTER_UUID})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"inst_uuid": CENTER_UUID}

    for payload in (
        {},
        {"inst_uuid": "not-a-uuid"},
        {"inst_uuids": [CENTER_UUID]},
        {"inst_uuid": CENTER_UUID, "model_id": "host"},
        {"inst_uuid": CENTER_UUID, "inst_uuids": [CENTER_UUID]},
    ):
        invalid = RelatedTopologyRequestSerializer(data=payload)
        assert not invalid.is_valid(), payload


def test_service_does_not_import_cmdb_instance_manage():
    source = inspect.getsource(RelatedTopologyService)
    assert "InstanceManage" not in source


def test_build_overlays_count_and_leaves_unmapped_distinct_from_quiet(monkeypatch):
    cmdb = _FakeCMDB(
        mappings=[
            {"inst_uuid": CENTER_UUID, "model_id": "host", "monitor_id": "mon-center"},
            {"inst_uuid": NEIGHBOR_UUID, "model_id": "switch", "monitor_id": ""},
        ]
    )
    monitor = _FakeMonitor(
        summaries=[
            {"instance_id": "mon-center", "count": 3, "max_level": "error"},
        ]
    )
    _install(monkeypatch, cmdb, monitor)

    result = RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)

    assert result["center_inst_uuid"] == CENTER_UUID
    center = result["src_result"]
    neighbor = center["children"][0]
    assert center["monitor_id"] == "mon-center"
    assert center["alert_count"] == 3
    assert center["max_level"] == "error"
    assert neighbor["monitor_id"] == ""
    assert neighbor["alert_count"] is None
    assert neighbor["max_level"] is None
    assert center["model_name"] == "主机"
    assert neighbor["model_name"] == "交换机"
    assert result["dst_result"]["alert_count"] == 3
    assert cmdb.neighbor_calls[0]["inst_uuid"] == CENTER_UUID
    assert cmdb.neighbor_calls[0]["user_info"]["user"] == "testuser"
    assert "model_id" not in cmdb.neighbor_calls[0]
    assert set(cmdb.mapping_calls[0]["inst_uuids"]) == {CENTER_UUID, NEIGHBOR_UUID}
    assert monitor.calls[0][0] == "query_latest_active_alerts"
    assert monitor.calls[0][1]["query_data"]["instance_ids"] == ["mon-center"]


def test_build_count_zero_is_not_unmapped(monkeypatch):
    cmdb = _FakeCMDB(
        tree=_tree(with_neighbor=False),
        mappings=[{"inst_uuid": CENTER_UUID, "model_id": "host", "monitor_id": "mon-center"}],
    )
    monitor = _FakeMonitor(summaries=[{"instance_id": "mon-center", "count": 0, "max_level": None}])
    _install(monkeypatch, cmdb, monitor)

    result = RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)

    assert result["src_result"]["monitor_id"] == "mon-center"
    assert result["src_result"]["alert_count"] == 0
    assert result["src_result"]["max_level"] is None
    assert result["src_result"]["children"] == []


def test_build_empty_neighbors_skips_alert_query(monkeypatch):
    cmdb = _FakeCMDB(tree=_tree(with_neighbor=False), mappings=[{"inst_uuid": CENTER_UUID, "model_id": "host", "monitor_id": ""}])
    monitor = _FakeMonitor()
    _install(monkeypatch, cmdb, monitor)

    result = RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)

    assert result["src_result"]["children"] == []
    assert result["src_result"]["alert_count"] is None
    assert monitor.calls == []


def test_build_maps_nats_permission_and_not_found(monkeypatch, caplog):
    for nats_code, http_code in (
        ("permission_denied", "permission_denied"),
        ("not_found", "not_found"),
        ("invalid_inst_uuid", "invalid_request"),
    ):
        cmdb = _FakeCMDB(neighbor_result={"result": False, "data": {"code": nats_code, "token": SECRET_SENTINEL}, "message": "nope"})
        _install(monkeypatch, cmdb)
        with caplog.at_level(logging.ERROR, logger="operation_analysis"):
            with pytest.raises(RelatedTopologyError) as exc_info:
                RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)
        assert exc_info.value.code == http_code
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert SECRET_SENTINEL not in caplog.text
        caplog.clear()


def test_build_source_failure_logs_once_without_payload(monkeypatch, caplog):
    cmdb = _FakeCMDB(
        mappings=[{"inst_uuid": CENTER_UUID, "model_id": "host", "monitor_id": "mon-center"}],
        mapping_result={
            "result": True,
            "data": {"items": [{"inst_uuid": CENTER_UUID, "monitor_id": "mon-center", "token": SECRET_SENTINEL}]},
            "message": "",
        },
    )

    class BoomMonitor(_FakeMonitor):
        def run(self, method_name, **kwargs):
            raise RuntimeError("nats unavailable")

    monitor = BoomMonitor()
    _install(monkeypatch, cmdb, monitor)

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(RelatedTopologyError) as exc_info:
            RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)

    assert exc_info.value.code == "source_failure"
    assert exc_info.value.message == "关联拓扑查询失败"
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=related_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    assert record.args == ("active_alerts", "RuntimeError", CENTER_UUID)
    rendered = record.getMessage()
    assert "active_alerts" in rendered
    assert CENTER_UUID in rendered
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in caplog.text
    assert record.exc_info is not None


def test_build_nats_false_result_logs_once_without_payload(monkeypatch, caplog):
    cmdb = _FakeCMDB(
        mapping_result={
            "result": False,
            "data": {"token": SECRET_SENTINEL, "items": [{"monitor_id": "mon-center"}]},
            "message": "nats down",
        }
    )
    monitor = _FakeMonitor()
    _install(monkeypatch, cmdb, monitor)

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(RelatedTopologyError) as exc_info:
            RelatedTopologyService.build(request=_topology_request(), inst_uuid=CENTER_UUID)

    assert exc_info.value.code == "source_failure"
    assert exc_info.value.message == "关联拓扑查询失败"
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=related_topology_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    assert record.args == ("monitor_ids", "NatsResultFalse", CENTER_UUID)
    rendered = record.getMessage()
    assert "monitor_ids" in rendered
    assert "NatsResultFalse" in rendered
    assert CENTER_UUID in rendered
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in caplog.text
    assert record.exc_info is None
    assert monitor.calls == []


def _anonymous_user():
    return SimpleNamespace(
        is_authenticated=True,
        is_superuser=False,
        username="testuser",
        domain="domain.com",
        locale="en",
        timezone="Asia/Shanghai",
        permission={},
        group_tree=[],
    )


def test_view_does_not_require_ops_analysis_menu_permission(monkeypatch):
    captured = {}

    def fake_build(request, inst_uuid):
        captured["inst_uuid"] = inst_uuid
        captured["user"] = request.user.username
        return {"center_inst_uuid": inst_uuid, "src_result": {}, "dst_result": {}}

    monkeypatch.setattr(RelatedTopologyService, "build", staticmethod(fake_build))

    request = _post_request(_anonymous_user(), {"inst_uuid": CENTER_UUID})
    response = SceneWidgetViewSet.as_view({"post": "related_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["center_inst_uuid"] == CENTER_UUID
    assert captured == {"inst_uuid": CENTER_UUID, "user": "testuser"}


def test_view_maps_permission_denied_and_rejects_model_id(monkeypatch):
    called = {"build": False}

    def fake_build(*args, **kwargs):
        called["build"] = True
        raise RelatedTopologyError("permission_denied")

    monkeypatch.setattr(RelatedTopologyService, "build", staticmethod(fake_build))

    denied = SceneWidgetViewSet.as_view({"post": "related_topology"})(_post_request(_anonymous_user(), {"inst_uuid": CENTER_UUID}))
    denied_payload = _render(denied)
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert denied_payload["result"] is False
    assert "无权限" in denied_payload["message"]

    rejected = SceneWidgetViewSet.as_view({"post": "related_topology"})(
        _post_request(_anonymous_user(), {"inst_uuid": CENTER_UUID, "model_id": "host"})
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert called["build"] is True
