"""采集器配置应用到节点：覆盖旧配置、缺失实体、节点计数。"""
import uuid

import pytest

from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import CollectorConfiguration
from apps.node_mgmt.services.collector_configuration import CollectorConfigurationService

pytestmark = pytest.mark.django_db


def _region():
    return CloudRegion.objects.create(name=f"cr-ccs-{uuid.uuid4().hex[:8]}")


def _node(region, **over):
    data = dict(
        id=f"n-{uuid.uuid4().hex[:8]}",
        name="n",
        ip="10.0.0.2",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
        cpu_architecture="x86_64",
    )
    data.update(over)
    return Node.objects.create(**data)


def _collector(suffix):
    return Collector.objects.create(
        id=f"c-{suffix}-{uuid.uuid4().hex[:8]}",
        name=f"Telegraf-{suffix}",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin",
        execute_parameters="-c",
    )


def _cfg(collector, region, name):
    return CollectorConfiguration.objects.create(
        name=name,
        collector=collector,
        config_template="x",
        cloud_region=region,
    )


def test_apply_to_node_missing_node_and_config():
    ok, msg = CollectorConfigurationService.apply_to_node("missing-node", "missing-cfg")
    assert ok is False
    assert msg == "节点missing-node不存在"

    region = _region()
    node = _node(region)
    ok, msg = CollectorConfigurationService.apply_to_node(node.id, "missing-cfg")
    assert ok is False
    assert msg == "采集器配置missing-cfg不存在"


def test_apply_to_node_replaces_same_collector_config():
    region = _region()
    node = _node(region)
    collector = _collector("one")
    old = _cfg(collector, region, f"old-{uuid.uuid4().hex[:6]}")
    new = _cfg(collector, region, f"new-{uuid.uuid4().hex[:6]}")
    old.nodes.add(node)

    ok, msg = CollectorConfigurationService.apply_to_node(node.id, new.id)
    assert ok is True
    assert msg == ""
    assert node not in old.nodes.all()
    assert node in new.nodes.all()


def test_calculate_node_count_splits_applied_and_pending():
    region = _region()
    applied = _node(region, status={"collectors": [{"configuration_id": ["cfg-1"]}]})
    pending = _node(region, status={"collectors": [{"configuration_id": ["other"]}]})
    configurations = [{"id": "cfg-1", "nodes": [applied.id, pending.id, "ghost"]}]
    out = CollectorConfigurationService.calculate_node_count(configurations)
    assert out[0]["node_count"] == 1
    assert out[0]["nodes"] == [applied.id]
    assert set(out[0]["not_applied_nodes"]) == {pending.id, "ghost"}
