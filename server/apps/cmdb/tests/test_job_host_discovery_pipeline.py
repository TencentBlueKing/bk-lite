"""主机目标贯穿节点配置与对账输入，结果仍使用原插件身份。"""

import pytest
import tomllib

from apps.cmdb.collection.collect_tasks.middleware import MiddlewareCollect
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.collect_service import CollectModelService


def discovery_task(**overrides):
    fields = dict(
        id=42,
        name="nginx-discovery",
        model_id="nginx",
        driver_type="job",
        task_type="middleware",
        timeout=60,
        team=[1],
        cycle_value_type="cycle",
        cycle_value="30",
        is_interval=True,
        access_point=[{"id": "proxy-1"}],
        ip_range="",
        instances=[
            {
                "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                "model_id": "host",
                "ip_addr": "10.0.0.8",
                "inst_name": "source-host",
                "organization": [1, 2],
            }
        ],
        params={"target_source": "host", "target_cloud_region_id": 2},
        credential=[],
    )
    fields.update(overrides)
    return CollectModels(**fields)


def test_final_nginx_config_uses_host_ip_and_trusted_region():
    task = discovery_task()
    node = NodeParamsFactory.get_node_params(task, resolve_credentials=False)
    config = node.push_params()[0]
    headers = tomllib.loads(config["content"])["inputs"]["prometheus"][0]["http_headers"]
    assert headers["cmdbhosts"] == "10.0.0.8"
    assert headers["cmdbmodel_id"] == "nginx"
    assert headers["cmdbplugin_name"] == "nginx_info"
    assert headers["cmdbcloud_region_id"] == "2"
    assert headers["instance_id"] == "cmdb_42"


@pytest.mark.parametrize("count", [1, 2])
def test_discovered_assets_use_task_organization_not_source_host_identity(count):
    task = discovery_task()
    task.instances *= count
    collect = MiddlewareCollect(task.id, task=task)
    assert collect.format_params() == ("nginx", None, [1], None, True)


def test_switching_to_ip_explicitly_clears_host_targets():
    task = discovery_task()
    data, _, _ = CollectModelService.format_params(
        {
            "name": task.name,
            "model_id": "nginx",
            "task_type": "middleware",
            "driver_type": "job",
            "timeout": 60,
            "team": [1],
            "input_method": 0,
            "scan_cycle": {"value_type": "cycle", "value": "30"},
            "instances": [],
            "ip_range": "10.0.0.9-10.0.0.9",
            "params": {"target_source": "ip"},
        }
    )
    for key, value in data.items():
        setattr(task, key, value)
    assert NodeParamsFactory.get_node_params(task, resolve_credentials=False).get_hosts() == ("hosts", "10.0.0.9-10.0.0.9")


def test_multiple_credentials_keep_host_scope_in_rendered_config():
    from apps.cmdb.node_configs.ssh.nginx import NginxNodeParams

    task = discovery_task()
    task.instances.append({"inst_uuid": "4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc", "ip_addr": "10.0.0.9"})
    node = NginxNodeParams(
        task,
        resolved_credentials=[
            {"credential_id": "first", "username": "root", "password": "first-secret", "port": 22},
            {"credential_id": "second", "username": "ops", "password": "second-secret", "port": 2200},
        ],
    )
    config = node.push_params()[0]["content"]
    headers = tomllib.loads(config)["inputs"]["prometheus"][0]["http_headers"]
    assert headers["cmdbhosts"] == "10.0.0.8,10.0.0.9"
    assert headers["cmdbmodel_id"] == "nginx"
    assert headers["cmdbplugin_name"] == "nginx_info"
    assert headers["cmdbcloud_region_id"] == "2"
    assert headers["cmdbcredential_count"] == "2"
    assert "first-secret" not in config
    assert "second-secret" not in config


@pytest.mark.django_db
def test_host_discovery_first_collection_executes_the_same_persisted_config(mocker):
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = discovery_task()
    task.save()
    run = FirstCollectionOrchestrator.schedule(task)
    assert run is not None
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)
    execute = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.NodeMgmt.run_telegraf_child_configs_once",
        return_value={"status": "accepted", "channels": {"cmdb_42": {"status": "accepted", "task_id": "execution-1"}}},
    )
    assert FirstCollectionOrchestrator.execute(run.id)["status"] == "accepted"
    execute.assert_called_once_with(
        request_id=f"first-collection-{run.id}",
        config_ids=["cmdb_42"],
        expected_node_id="proxy-1",
        organization_ids=[1],
    )
