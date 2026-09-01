"""Sidecar 剩余契约：动作 ack、304 无 IP 回退、标签补全、默认配置跳过/更新。"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Action, CollectorConfiguration
from apps.node_mgmt.services.sidecar import Sidecar

pytestmark = pytest.mark.django_db


def _region(suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    return CloudRegion.objects.create(name=f"cr-r13-{suffix}")


def _node(region, **over):
    suffix = uuid.uuid4().hex[:8]
    data = dict(
        id=f"node-r13-{suffix}",
        name="n",
        ip="10.13.13.13",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
        cpu_architecture="x86_64",
    )
    data.update(over)
    return Node.objects.create(**data)


def _request(headers=None, data=None, meta=None):
    req = MagicMock()
    req.headers = headers or {}
    req.META = meta or {}
    req.data = data or {}
    return req


# --------------------------------------------------------------------------
# _collector_status_signature / trigger_converge
# --------------------------------------------------------------------------


def test_trigger_converge_schedules_action_on_signature_change():
    region = _region()
    node = _node(region)
    collector = Collector.objects.create(
        id=f"c-act-{uuid.uuid4().hex[:8]}",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin",
        execute_parameters="-c",
    )
    task = CollectorActionTask.objects.create(collector=collector, action="restart", status="running")
    CollectorActionTaskNode.objects.create(task=task, node=node, status="running", result={})

    with (
        patch("apps.node_mgmt.services.sidecar.cache.get", return_value=None),
        patch("apps.node_mgmt.services.sidecar.cache.set"),
        patch("apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node") as conv,
    ):
        Sidecar.trigger_converge_tasks_if_needed(
            node.id,
            node.ip,
            {"collectors": [{"collector_id": collector.id, "status": "ok"}]},
        )
    conv.delay.assert_called_once_with(node.id)


# --------------------------------------------------------------------------
# update_node_client：304 无 IP、标签补全、动作 ack
# --------------------------------------------------------------------------


def test_update_node_client_etag_hit_looks_up_ip_from_db():
    region = _region()
    node = _node(region, ip="10.9.8.7")
    req = SimpleNamespace(
        headers={"If-None-Match": '"etag-r13"'},
        data={"node_details": {"status": {"cpu": 2}}},
    )
    with (
        patch("apps.node_mgmt.services.sidecar.cache.get", return_value="etag-r13"),
        patch.object(Sidecar, "trigger_converge_tasks_if_needed") as converge,
    ):
        resp = Sidecar.update_node_client(req, node.id)
    assert resp.status_code == 304
    converge.assert_called_once_with(node.id, "10.9.8.7", {"cpu": 2})


def test_update_node_client_applies_install_method_and_node_type_tags():
    region = _region()
    node = _node(region)
    req = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "edge",
            "node_details": {
                "ip": node.ip,
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/sidecar",
                "metrics": {},
                "status": {},
                "log_file_list": [],
                "tags": [
                    f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
                    f"{ControllerConstants.CLOUD_TAG}:{region.id}",
                ],
            },
        },
    )
    with (
        patch("apps.node_mgmt.services.sidecar.cache.get", return_value=None),
        patch("apps.node_mgmt.services.sidecar.cache.set"),
        patch.object(Sidecar, "trigger_converge_tasks_if_needed"),
    ):
        resp = Sidecar.update_node_client(req, node.id)
    assert resp.status_code == 202
    node.refresh_from_db()
    assert node.install_method == ControllerConstants.MANUAL
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER
    assert node.cloud_region_id == region.id


def test_update_node_client_acks_waiting_action_task():
    region = _region()
    node = _node(region)
    collector = Collector.objects.create(
        id=f"c-wait-{uuid.uuid4().hex[:8]}",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin",
        execute_parameters="-c",
    )
    task = CollectorActionTask.objects.create(collector=collector, action="restart", status="waiting")
    task_node = CollectorActionTaskNode.objects.create(task=task, node=node, status="waiting", result={})
    Action.objects.create(node=node, action=[{"task_id": task.id, "collector_id": collector.id}])

    req = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": node.name,
            "node_details": {
                "ip": node.ip,
                "operating_system": "linux",
                "collector_configuration_directory": "/etc/sidecar",
                "metrics": {},
                "status": {},
                "log_file_list": [],
                "tags": [],
            },
        },
    )
    with (
        patch("apps.node_mgmt.services.sidecar.cache.get", return_value=None),
        patch("apps.node_mgmt.services.sidecar.cache.set"),
        patch.object(Sidecar, "trigger_converge_tasks_if_needed"),
    ):
        resp = Sidecar.update_node_client(req, node.id)
    assert resp.status_code == 202
    task_node.refresh_from_db()
    assert task_node.status == "running"
    assert task_node.result["overall_status"] == "running"
    assert not Action.objects.filter(node=node).exists()


def test_update_node_client_updates_running_action_consume_ack():
    region = _region()
    node = _node(region)
    collector = Collector.objects.create(
        id=f"c-run-{uuid.uuid4().hex[:8]}",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin",
        execute_parameters="-c",
    )
    task = CollectorActionTask.objects.create(collector=collector, action="restart", status="waiting")
    task_node = CollectorActionTaskNode.objects.create(
        task=task,
        node=node,
        status="running",
        result={"steps": [{"action": "consume_ack", "status": "running"}]},
    )
    Action.objects.create(node=node, action=[{"task_id": task.id, "collector_id": collector.id}])

    req = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": node.name,
            "node_details": {
                "ip": node.ip,
                "operating_system": "linux",
                "collector_configuration_directory": "/etc/sidecar",
                "metrics": {},
                "status": {},
                "log_file_list": [],
                "tags": [],
            },
        },
    )
    with (
        patch("apps.node_mgmt.services.sidecar.cache.get", return_value=None),
        patch("apps.node_mgmt.services.sidecar.cache.set"),
        patch.object(Sidecar, "trigger_converge_tasks_if_needed"),
    ):
        resp = Sidecar.update_node_client(req, node.id)
    assert resp.status_code == 202
    task_node.refresh_from_db()
    steps = {step["action"]: step for step in task_node.result["steps"]}
    assert steps["consume_ack"]["status"] == "success"
    assert "execute_command" in steps
    task.refresh_from_db()
    assert task.status == "running"


# --------------------------------------------------------------------------
# get_node_config：ETag 命中但节点不存在
# --------------------------------------------------------------------------


def test_get_node_config_etag_hit_missing_node_returns_404():
    req = _request(headers={"If-None-Match": "stale"})
    with patch("apps.node_mgmt.services.sidecar.cache.get", return_value="stale"):
        resp = Sidecar.get_node_config(req, "missing-node-r13", "cfg-x")
    assert resp.status_code == 404
    assert json.loads(resp.content)["error"] == "Node not found"


# --------------------------------------------------------------------------
# create_default_config
# --------------------------------------------------------------------------


def _collector(region, name, default_config):
    return Collector.objects.create(
        id=f"c-{name}-{uuid.uuid4().hex[:8]}",
        name=name,
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin",
        execute_parameters="-c",
        default_config=default_config,
    )


def test_create_default_config_skips_container_collector_on_host():
    region = _region()
    node = _node(region)
    collector = _collector(region, "Snmptrapd", {"nats": "x"})
    assert collector.name in CollectorConstants.DEFAULT_CONTAINER_COLLECTOR_CONFIGS
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [])
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


def test_create_default_config_skips_when_template_missing():
    region = _region()
    node = _node(region)
    collector = _collector(region, "Telegraf", {"other": "x"})
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [])
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


def test_create_default_config_updates_existing_pre_and_skips_identical():
    region = _region()
    node = _node(region)
    collector = _collector(region, "Telegraf", {"nats": "url={{ HOST }}"})
    cfg = CollectorConfiguration.objects.create(
        name=f"pre-{collector.id}",
        collector=collector,
        config_template="old",
        is_pre=True,
        cloud_region=region,
    )
    cfg.nodes.add(node)
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats", "HOST": "10.1.1.1"}),
    ):
        Sidecar.create_default_config(node, [])
    cfg.refresh_from_db()
    assert "10.1.1.1" in cfg.config_template

    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats", "HOST": "10.1.1.1"}),
    ):
        Sidecar.create_default_config(node, [])
    assert CollectorConfiguration.objects.filter(collector=collector, nodes=node).count() == 1


def test_create_default_config_skips_custom_and_swallows_render_error():
    region = _region()
    node = _node(region)
    custom = _collector(region, "Vector", {"nats": "ok"})
    cfg = CollectorConfiguration.objects.create(
        name="custom",
        collector=custom,
        config_template="user",
        is_pre=False,
        cloud_region=region,
    )
    cfg.nodes.add(node)
    boom = _collector(region, "Broken", {"nats": "{% invalid jinja %}"})
    with (
        patch.object(
            Sidecar,
            "_get_default_collectors_for_node",
            return_value={custom.name: custom, boom.name: boom},
        ),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [])
    assert not CollectorConfiguration.objects.filter(collector=boom).exists()
    assert CollectorConfiguration.objects.get(pk=cfg.pk).config_template == "user"


def test_create_default_config_appends_add_config_for_container():
    region = _region()
    node = _node(region, node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    collector = _collector(region, "Telegraf", {"nats": "base", "add_config": "extra-line"})
    with (
        patch.object(Sidecar, "_get_default_collectors_for_node", return_value={collector.name: collector}),
        patch.object(Sidecar, "get_cloud_region_envconfig", return_value={"SIDECAR_INPUT_MODE": "nats"}),
    ):
        Sidecar.create_default_config(node, [ControllerConstants.NODE_TYPE_CONTAINER])
    cfg = CollectorConfiguration.objects.get(collector=collector, nodes=node, is_pre=True)
    assert "extra-line" in cfg.config_template
