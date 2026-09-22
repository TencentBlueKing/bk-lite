"""通过任务保存序列化 Interface 验证主机来源与可信区域。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
from apps.rpc.node_mgmt import NodeMgmt

HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
OTHER_UUID = "4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc"


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.User.objects", SimpleNamespace(all=lambda: SimpleNamespace(values=lambda *a: [])))
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **kw: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions", lambda *a: {})
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission", lambda *a, **kw: True)
    rows = {
        HOST_UUID: {"inst_uuid": HOST_UUID, "model_id": "host", "inst_name": "host-a", "ip_addr": "10.0.0.8", "cloud": 2, "organization": [1]},
        OTHER_UUID: {"inst_uuid": OTHER_UUID, "model_id": "host", "inst_name": "host-b", "ip_addr": "10.0.0.9", "cloud": 2, "organization": [1]},
    }
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids", lambda ids: [deepcopy(rows[i]) for i in ids if i in rows]
    )
    monkeypatch.setattr(
        NodeMgmt,
        "get_authorized_nodes_by_ids",
        lambda self, ids, permission_data: [
            {"id": "proxy-1", "node_type": "container", "organization_ids": [1]},
        ],
    )
    monkeypatch.setattr(NodeMgmt, "get_nodes_by_ids", lambda self, ids: [{"id": "proxy-1", "cloud_region_id": 2}])
    return rows


def task_serializer(data=None, *, instance=None, team=1):
    payload = {
        "name": "nginx-host-discovery",
        "model_id": "nginx",
        "task_type": "middleware",
        "driver_type": "job",
        "cycle_value_type": "cycle",
        "timeout": 60,
        "team": [team],
        "credential": [],
        "ip_range": "",
        "instances": [{"inst_uuid": HOST_UUID, "ip_addr": "203.0.113.99"}],
        "access_point": [{"id": "proxy-1", "cloud_region": 999}],
        "params": {"target_source": "host", "target_cloud_region_id": 999},
    }
    if instance is not None:
        payload = {}
    payload.update(data or {})
    request = SimpleNamespace(user=SimpleNamespace(username="reader", domain="domain-a", group_list=[]), COOKIES={"current_team": str(team)})
    return CollectModelSerializer(instance, data=payload, partial=instance is not None, context={"request": request})


def test_host_discovery_uses_trusted_host_and_access_point_region(catalog):
    serializer = task_serializer()
    assert serializer.is_valid(), serializer.errors
    result = serializer.validated_data
    assert result["model_id"] == "nginx"
    assert result["instances"] == [catalog[HOST_UUID]]
    assert result["params"]["target_cloud_region_id"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"cloud": 3},
        {"cloud": None},
        {"organization": [2]},
        {"ip_addr": ""},
        {"ip_addr": "not-an-ip"},
        {"model_id": "nginx"},
    ],
)
def test_discovery_rejects_hosts_outside_the_execution_scope(catalog, changes):
    catalog[HOST_UUID].update(changes)
    serializer = task_serializer()
    assert not serializer.is_valid()
    assert "instances" in serializer.errors


@pytest.mark.parametrize("instances", [[], [{"inst_uuid": HOST_UUID}] * 2049])
def test_discovery_requires_a_bounded_nonempty_target_set(catalog, instances):
    serializer = task_serializer({"instances": instances})
    assert not serializer.is_valid()
    assert "instances" in serializer.errors


def test_distinct_hosts_cannot_share_an_execution_ip(catalog):
    catalog[OTHER_UUID]["ip_addr"] = "10.0.0.8"
    serializer = task_serializer({"instances": [{"inst_uuid": HOST_UUID}, {"inst_uuid": OTHER_UUID}]})
    assert not serializer.is_valid()
    assert "instances" in serializer.errors


@pytest.mark.parametrize("params", [{"target_source": "invalid"}, {"target_source": []}])
def test_unknown_target_source_is_rejected(catalog, params):
    serializer = task_serializer({"params": params})
    assert not serializer.is_valid()
    assert "params" in serializer.errors


def test_host_mode_cannot_also_submit_ip_range(catalog):
    serializer = task_serializer({"ip_range": "10.0.0.1-10.0.0.2"})
    assert not serializer.is_valid()
    assert "ip_range" in serializer.errors


@pytest.mark.parametrize(
    "node",
    [[], [{"id": "proxy-1", "node_type": "host", "organization_ids": [1]}], [{"id": "proxy-1", "node_type": "container", "organization_ids": [2]}]],
)
def test_access_point_must_be_authorized_executor_in_task_scope(catalog, monkeypatch, node):
    monkeypatch.setattr(NodeMgmt, "get_authorized_nodes_by_ids", lambda *a, **kw: node)
    serializer = task_serializer()
    assert not serializer.is_valid()
    assert "access_point" in serializer.errors


def test_partial_update_revalidates_scope_and_preserves_other_params(catalog):
    existing = CollectModels(
        model_id="nginx",
        task_type="middleware",
        driver_type="job",
        team=[1],
        instances=[catalog[HOST_UUID]],
        access_point=[{"id": "proxy-1"}],
        params={"target_source": "host", "ip_precheck": True, "credential_set_version": "v2"},
    )
    serializer = task_serializer({"params": {"ip_precheck": False}}, instance=existing)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"] == {
        "target_source": "host",
        "target_cloud_region_id": 2,
        "ip_precheck": False,
        "credential_set_version": "v2",
    }
    denied = task_serializer({"team": [2]}, instance=existing)
    assert not denied.is_valid()


@pytest.mark.parametrize("params", [{"target_source": None}, []])
def test_malformed_explicit_source_or_params_is_rejected(catalog, params):
    serializer = task_serializer({"params": params})
    assert not serializer.is_valid()
    assert "params" in serializer.errors


@pytest.mark.parametrize(
    "changes",
    [
        {"model_id": "config_file", "task_type": "config_file"},
        {"model_id": "host", "task_type": "host"},
        {"model_id": "nginx", "driver_type": "protocol"},
        {"model_id": "not-a-plugin"},
        {"model_id": "nginx", "task_type": "db"},
    ],
)
def test_request_cannot_spoof_plugin_capability(catalog, changes):
    serializer = task_serializer(changes)
    assert not serializer.is_valid()
    assert "params" in serializer.errors


def test_host_source_overrides_enterprise_target_model_only_for_discovery(catalog, monkeypatch):
    from apps.cmdb.serializers import collect_serializer

    original = collect_serializer.get_collect_object_meta

    def enterprise_meta(model_id, driver_type=None):
        return {**original(model_id, driver_type), "target_model_id": model_id}

    monkeypatch.setattr(collect_serializer, "get_collect_object_meta", enterprise_meta)
    discovery = task_serializer()
    assert discovery.is_valid(), discovery.errors
    asset = task_serializer({"params": {"target_source": "asset"}})
    assert not asset.is_valid()
    assert "instances" in asset.errors


def test_invisible_uuid_cannot_be_used_as_execution_target(catalog, monkeypatch):
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission", lambda *a, **kw: False)
    serializer = task_serializer()
    assert not serializer.is_valid()
    assert "instances" in serializer.errors


@pytest.mark.parametrize("region", [None, 0, "unknown", True])
def test_unconfirmed_proxy_region_fails_closed(catalog, monkeypatch, region):
    monkeypatch.setattr(NodeMgmt, "get_nodes_by_ids", lambda *a: [{"id": "proxy-1", "cloud_region_id": region}])
    serializer = task_serializer()
    assert not serializer.is_valid()
    assert "access_point" in serializer.errors


@pytest.mark.parametrize("method", ["get_nodes_by_ids", "get_authorized_nodes_by_ids"])
def test_proxy_rpc_failure_rejects_save_without_exposing_response(catalog, monkeypatch, method):
    def failed(*args, **kwargs):
        raise RuntimeError("private-response-sentinel")

    monkeypatch.setattr(NodeMgmt, method, failed)
    serializer = task_serializer()
    assert not serializer.is_valid()
    assert "access_point" in serializer.errors
    assert "private-response-sentinel" not in str(serializer.errors)


def test_resaving_refreshes_host_ip_and_switching_clears_region(catalog):
    initial = task_serializer()
    assert initial.is_valid(), initial.errors
    existing = CollectModels(**initial.validated_data)
    catalog[HOST_UUID]["ip_addr"] = "10.0.0.18"
    refreshed = task_serializer({"timeout": 90}, instance=existing)
    assert refreshed.is_valid(), refreshed.errors
    assert refreshed.validated_data["instances"][0]["ip_addr"] == "10.0.0.18"
    switched = task_serializer({"params": {"target_source": "ip"}, "instances": [], "ip_range": "10.0.0.20"}, instance=existing)
    assert switched.is_valid(), switched.errors
    assert switched.validated_data["instances"] == []
    assert "target_cloud_region_id" not in switched.validated_data["params"]


def test_proxy_authorization_uses_request_identity_and_current_team(catalog, monkeypatch):
    captured = []

    def authorized(self, ids, permission_data):
        captured.append((ids, permission_data))
        return [{"id": "proxy-1", "node_type": "container", "organization_ids": [2]}]

    monkeypatch.setattr(NodeMgmt, "get_authorized_nodes_by_ids", authorized)
    catalog[HOST_UUID]["organization"] = [2]
    serializer = task_serializer(team=2)
    assert serializer.is_valid(), serializer.errors
    assert captured == [(["proxy-1"], {"username": "reader", "domain": "domain-a", "current_team": "2"})]


@pytest.mark.django_db
def test_service_update_clears_persisted_hosts_before_pushing_new_config(catalog, mocker, django_capture_on_commit_callbacks):
    import tomllib

    from apps.cmdb.node_configs.config_factory import NodeParamsFactory
    from apps.cmdb.services.collect_service import CollectModelService
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    serializer = task_serializer({"is_interval": True, "cycle_value": "30"})
    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()
    request = serializer.context["request"]
    request.data = {
        "name": instance.name,
        "model_id": "nginx",
        "driver_type": "job",
        "task_type": "middleware",
        "timeout": 60,
        "team": [1],
        "input_method": 0,
        "scan_cycle": {"value_type": "cycle", "value": "30"},
        "instances": [],
        "ip_range": "10.0.0.20",
        "params": {"target_source": "ip"},
        "credential": [{"port": 22}],
    }
    view = SimpleNamespace(
        get_object=lambda: instance,
        get_serializer=lambda obj, **kwargs: CollectModelSerializer(obj, context={"request": request}, **kwargs),
        perform_update=lambda saved: saved.save(),
    )
    # 外部权限/配置传输由边界替身提供；转换、序列化、落库、配置渲染与首次采集编排真实执行。
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    events = []
    mocker.patch.object(CollectModelService, "delete_butch_node_params", side_effect=lambda old: events.append(("delete", old.instances)))

    def push(task):
        config = NodeParamsFactory.get_node_params(task, resolve_credentials=False).push_params()[0]
        headers = tomllib.loads(config["content"])["inputs"]["prometheus"][0]["http_headers"]
        events.append(("push", headers))

    mocker.patch.object(CollectModelService, "push_butch_node_params", side_effect=push)
    ready = mocker.spy(FirstCollectionOrchestrator, "mark_config_ready_and_dispatch")

    with django_capture_on_commit_callbacks(execute=True):
        assert CollectModelService.update(request, view) == instance.id
    instance.refresh_from_db()
    assert instance.instances == []
    assert instance.ip_range == "10.0.0.20"
    assert instance.params["target_source"] == "ip"
    assert "target_cloud_region_id" not in instance.params
    assert events[0][0] == "delete"
    assert events[0][1][0]["inst_uuid"] == HOST_UUID
    assert events[1][0] == "push"
    assert events[1][1]["cmdbhosts"] == "10.0.0.20"
    assert "cmdbcloud_region_id" not in events[1][1]
    ready.assert_called_once()


def test_repeated_uuid_is_one_host_target(catalog):
    serializer = task_serializer({"instances": [{"inst_uuid": HOST_UUID}, {"inst_uuid": HOST_UUID}]})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["instances"] == [catalog[HOST_UUID]]


def test_maximum_host_count_is_accepted_without_truncation(catalog):
    from ipaddress import IPv4Address
    from uuid import uuid4

    catalog.clear()
    for index in range(2048):
        uuid = str(uuid4())
        catalog[uuid] = {"inst_uuid": uuid, "model_id": "host", "ip_addr": str(IPv4Address("10.0.0.1") + index), "cloud": 2, "organization": [1]}
    serializer = task_serializer({"instances": [{"inst_uuid": uuid} for uuid in catalog]})
    assert serializer.is_valid(), serializer.errors
    assert len(serializer.validated_data["instances"]) == 2048
