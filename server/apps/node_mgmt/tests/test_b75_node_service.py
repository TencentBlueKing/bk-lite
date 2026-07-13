"""NodeService 真实行为测试：节点列表过滤、批量绑定/操作、默认配置创建、查询辅助。

仅 mock celery.apply_async、SystemMgmt RPC、Sidecar.get_cloud_region_envconfig 边界。
断言真实 DB 副作用与返回值。
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.utils import timezone as dj_timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import (
    Action,
    CollectorConfiguration,
    NodeOrganization,
)
from apps.node_mgmt.services.node import NodeService


@pytest.fixture
def setup(db):
    region = CloudRegion.objects.create(name="cr-node-svc")
    collector = Collector.objects.create(
        id="col-svc",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )
    node = Node.objects.create(
        id="node-svc-1",
        name="alpha",
        ip="10.1.1.1",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    return region, collector, node


# --------------------------------------------------------------------------- #
# get_node_list
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_node_list_fail_closed_without_permission_or_org(setup):
    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=None, is_manual=None, is_container=None,
    )
    assert result["count"] == 0
    assert result["nodes"] == []


@pytest.mark.django_db
def test_get_node_list_skip_permission_returns_nodes(setup):
    region, collector, node = setup
    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=None, is_manual=None, is_container=None,
        skip_permission=True,
    )
    assert result["count"] == 1
    assert result["nodes"][0]["id"] == node.id


@pytest.mark.django_db
def test_get_node_list_filters_by_name_ip_os(setup):
    region, collector, node = setup
    Node.objects.create(
        id="node-svc-2", name="beta", ip="192.168.0.9", operating_system="windows",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name="alph", ip="10.1", os="linux",
        page=1, page_size=10, is_active=None, is_manual=None, is_container=None,
        skip_permission=True,
    )
    assert result["count"] == 1
    assert result["nodes"][0]["name"] == "alpha"


@pytest.mark.django_db
def test_get_node_list_page_size_all(setup):
    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=-1, is_active=None, is_manual=None, is_container=None,
        skip_permission=True,
    )
    assert result["count"] == 1


@pytest.mark.django_db
def test_get_node_list_page_size_all_is_capped(setup, monkeypatch):
    region, collector, node = setup
    Node.objects.create(
        id="node-svc-2", name="beta", ip="10.1.1.2", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    Node.objects.create(
        id="node-svc-3", name="gamma", ip="10.1.1.3", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    monkeypatch.setattr(NodeService, "NODE_LIST_PAGE_SIZE_MAX", 2)

    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=-1, is_active=None, is_manual=None, is_container=None,
        skip_permission=True,
    )

    assert result["count"] == 3
    assert len(result["nodes"]) == 2


@pytest.mark.django_db
def test_get_node_list_page_size_above_limit_is_capped(setup, monkeypatch):
    region, collector, node = setup
    Node.objects.create(
        id="node-svc-2", name="beta", ip="10.1.1.2", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    Node.objects.create(
        id="node-svc-3", name="gamma", ip="10.1.1.3", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
    )
    monkeypatch.setattr(NodeService, "NODE_LIST_PAGE_SIZE_MAX", 2)

    result = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=999, is_active=None, is_manual=None, is_container=None,
        skip_permission=True,
    )

    assert result["count"] == 3
    assert len(result["nodes"]) == 2


@pytest.mark.django_db
def test_get_node_list_is_container_and_is_manual_filters(setup):
    region, collector, node = setup
    Node.objects.create(
        id="node-container", name="cont", ip="10.1.1.2", operating_system="linux",
        collector_configuration_directory="/etc", cloud_region=region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
        install_method=ControllerConstants.MANUAL,
    )
    container_only = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=None, is_manual=None, is_container=True,
        skip_permission=True,
    )
    assert container_only["count"] == 1
    manual_only = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=None, is_manual=True, is_container=None,
        skip_permission=True,
    )
    assert manual_only["count"] == 1


@pytest.mark.django_db
def test_get_node_list_is_active_filter(setup):
    region, collector, node = setup
    # 把 updated_at 设到 2 分钟前 -> is_active False
    old = dj_timezone.now() - timedelta(minutes=2)
    Node.objects.filter(id=node.id).update(updated_at=old)
    inactive = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=False, is_manual=None, is_container=None,
        skip_permission=True,
    )
    assert inactive["count"] == 1
    active = NodeService.get_node_list(
        organization_ids=[], cloud_region_id=None, name=None, ip=None, os=None,
        page=1, page_size=10, is_active=True, is_manual=None, is_container=None,
        skip_permission=True,
    )
    assert active["count"] == 0


# --------------------------------------------------------------------------- #
# batch_binding_node_configuration
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_batch_binding_node_configuration_success(setup):
    region, collector, node = setup
    config = CollectorConfiguration.objects.create(
        name="cfg-bind", collector=collector, cloud_region=region
    )
    ok, msg = NodeService.batch_binding_node_configuration([node.id], config.id)
    assert ok is True
    assert config.nodes.filter(id=node.id).exists()


@pytest.mark.django_db
def test_batch_binding_node_configuration_not_found(setup):
    ok, msg = NodeService.batch_binding_node_configuration(["x"], "no-config")
    assert ok is False
    assert "不存在" in msg


@pytest.mark.django_db
def test_batch_binding_overrides_existing_config(setup):
    region, collector, node = setup
    old_config = CollectorConfiguration.objects.create(
        name="cfg-old", collector=collector, cloud_region=region
    )
    old_config.nodes.add(node)
    new_config = CollectorConfiguration.objects.create(
        name="cfg-new", collector=collector, cloud_region=region
    )
    ok, _ = NodeService.batch_binding_node_configuration([node.id], new_config.id)
    assert ok is True
    assert not old_config.nodes.filter(id=node.id).exists()
    assert new_config.nodes.filter(id=node.id).exists()


# --------------------------------------------------------------------------- #
# batch_operate_node_collector
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_batch_operate_no_nodes_raises():
    with pytest.raises(BaseAppException) as exc:
        NodeService.batch_operate_node_collector(["nope"], "col", "start")
    assert "No valid nodes" in str(exc.value)


@pytest.mark.django_db
def test_batch_operate_stop_creates_task_and_actions(setup):
    region, collector, node = setup
    with patch(
        "apps.node_mgmt.services.node.timeout_collector_action_task.apply_async"
    ) as apply_mock:
        task_id = NodeService.batch_operate_node_collector(
            [node.id], collector.id, "stop", created_by="tester"
        )
    apply_mock.assert_called_once()
    task = CollectorActionTask.objects.get(id=task_id)
    assert task.action == "stop"
    assert task.total_count == 1
    # action 记录写入
    action = Action.objects.get(node=node)
    assert action.action[0]["collector_id"] == collector.id
    assert action.action[0]["properties"] == {"stop": True}
    # task_node 进入 running
    tn = CollectorActionTaskNode.objects.get(task=task, node=node)
    assert tn.status == "running"
    assert tn.result["overall_status"] == "running"


@pytest.mark.django_db
def test_batch_operate_start_creates_default_config(setup):
    region, collector, node = setup
    collector.default_config = {"nats": "key = value"}
    collector.save()
    with patch(
        "apps.node_mgmt.services.node.timeout_collector_action_task.apply_async"
    ), patch(
        "apps.node_mgmt.services.node.Sidecar.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats"},
    ):
        NodeService.batch_operate_node_collector([node.id], collector.id, "start")
    # 为没有配置的节点创建了默认配置
    assert CollectorConfiguration.objects.filter(collector=collector, nodes=node).exists()


# --------------------------------------------------------------------------- #
# _create_collector_default_config
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_create_default_config_no_default_config_skips(setup):
    region, collector, node = setup
    # collector.default_config 为空 -> 直接返回，不创建
    NodeService._create_collector_default_config(node, collector)
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


@pytest.mark.django_db
def test_create_default_config_no_template_for_mode_skips(setup):
    region, collector, node = setup
    collector.default_config = {"other_mode": "x"}
    collector.save()
    with patch(
        "apps.node_mgmt.services.node.Sidecar.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats"},
    ):
        NodeService._create_collector_default_config(node, collector)
    assert not CollectorConfiguration.objects.filter(collector=collector).exists()


@pytest.mark.django_db
def test_create_default_config_renders_template(setup):
    region, collector, node = setup
    collector.default_config = {"nats": "url = {{ SERVER }}"}
    collector.save()
    with patch(
        "apps.node_mgmt.services.node.Sidecar.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats", "SERVER": "host.local"},
    ):
        NodeService._create_collector_default_config(node, collector)
    cfg = CollectorConfiguration.objects.get(collector=collector)
    assert "host.local" in cfg.config_template
    assert cfg.is_pre is True


@pytest.mark.django_db
def test_create_default_config_container_appends_add_config(setup):
    region, collector, node = setup
    node.node_type = ControllerConstants.NODE_TYPE_CONTAINER
    node.save()
    collector.default_config = {"nats": "base", "add_config": "extra-line"}
    collector.save()
    with patch(
        "apps.node_mgmt.services.node.Sidecar.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats"},
    ):
        NodeService._create_collector_default_config(node, collector)
    cfg = CollectorConfiguration.objects.get(collector=collector)
    assert "extra-line" in cfg.config_template


# --------------------------------------------------------------------------- #
# get_authorized_nodes_by_ids / get_node_names_by_ids / get_nodes_by_ids
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_create_default_config_render_failure_raises_base_exception(setup):
    region, collector, node = setup
    collector.default_config = {"nats": "{% invalid jinja %}"}
    collector.save()
    with patch(
        "apps.node_mgmt.services.node.Sidecar.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats"},
    ):
        with pytest.raises(BaseAppException):
            NodeService._create_collector_default_config(node, collector)


@pytest.mark.django_db
def test_get_authorized_nodes_empty_ids_returns_empty():
    assert NodeService.get_authorized_nodes_by_ids([]) == []
    assert NodeService.get_authorized_nodes_by_ids([None, ""]) == []


@pytest.mark.django_db
def test_get_authorized_nodes_no_permission_returns_all(setup):
    region, collector, node = setup
    NodeOrganization.objects.create(node=node, organization=7)
    result = NodeService.get_authorized_nodes_by_ids([node.id])
    assert len(result) == 1
    assert result[0]["id"] == node.id
    assert 7 in result[0]["organization_ids"]


@pytest.mark.django_db
def test_get_node_names_by_ids(setup):
    region, collector, node = setup
    result = NodeService.get_node_names_by_ids([node.id, None])
    assert result == [{"id": node.id, "name": "alpha"}]


@pytest.mark.django_db
def test_get_node_names_by_ids_empty():
    assert NodeService.get_node_names_by_ids([]) == []


@pytest.mark.django_db
def test_get_nodes_by_ids_returns_full_info(setup):
    region, collector, node = setup
    NodeOrganization.objects.create(node=node, organization=3)
    result = NodeService.get_nodes_by_ids([node.id])
    assert len(result) == 1
    item = result[0]
    assert item["cloud_region_name"] == "cr-node-svc"
    assert item["operating_system"] == "linux"
    assert 3 in item["organization_ids"]


@pytest.mark.django_db
def test_get_nodes_by_ids_empty():
    assert NodeService.get_nodes_by_ids([]) == []


# --------------------------------------------------------------------------- #
# process_node_data
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_process_node_data_marks_active_and_collector_names(setup):
    region, collector, node = setup
    config = CollectorConfiguration.objects.create(
        name="cfg-process", collector=collector, cloud_region=region
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    node_data = [
        {
            "id": node.id,
            "name": node.name,
            "updated_at": now_iso,
            "status": {
                "collectors": [
                    {"collector_id": collector.id, "configuration_id": config.id, "status": 0}
                ]
            },
        }
    ]
    result = NodeService.process_node_data(node_data)
    assert result[0]["active"] is True
    coll = result[0]["status"]["collectors"][0]
    assert coll["collector_name"] == "Telegraf"
    assert coll["configuration_name"] == "cfg-process"


@pytest.mark.django_db
def test_process_node_data_inactive_when_old(setup):
    region, collector, node = setup
    old_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S%z")
    node_data = [{"id": node.id, "name": node.name, "updated_at": old_iso, "status": {}}]
    result = NodeService.process_node_data(node_data)
    assert result[0]["active"] is False


@pytest.mark.django_db
def test_process_node_data_includes_install_status(setup):
    region, collector, node = setup
    from apps.node_mgmt.models.installer import NodeCollectorInstallStatus

    NodeCollectorInstallStatus.objects.create(
        node=node, collector=collector, status="success", result={"msg": "ok"}
    )
    NodeCollectorInstallStatus.objects.create(
        node=node, collector=collector, status="error", result={"msg": "bad"}
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    node_data = [{"id": node.id, "name": node.name, "updated_at": now_iso, "status": {}}]
    result = NodeService.process_node_data(node_data)
    installs = result[0]["status"]["collectors_install"]
    statuses = sorted(item["status"] for item in installs)
    assert statuses == [11, 12]
    assert all(item["collector_name"] == "Telegraf" for item in installs)


@pytest.mark.django_db
def test_build_scoped_permission_no_team_returns_empty():
    assert NodeService._build_scoped_permission({"username": "u", "domain": "d"}) == {}


@pytest.mark.django_db
def test_build_scoped_permission_invalid_team_returns_empty():
    assert NodeService._build_scoped_permission(
        {"username": "u", "domain": "d", "current_team": "abc"}
    ) == {}
