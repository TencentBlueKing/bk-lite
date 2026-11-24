"""同一节点 ID 心跳重建后，把停采的监控和日志配置挂回。"""

import logging
from types import SimpleNamespace

import pytest

from apps.core.logger import SafeLogException, safe_log_value
from apps.log.models import CollectConfig as LogCollectConfig
from apps.log.models import CollectInstance, CollectType
from apps.log.services.collector_node_exit import LOG_RETURN_FINISHED_LOG
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject
from apps.monitor.services.collector_node_exit import MONITOR_RETURN_FINISHED_LOG
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import CloudRegion, Collector, CollectorConfiguration, Node
from apps.node_mgmt.models.sidecar import ChildConfig, NodeCollectorConfiguration
from apps.node_mgmt.services.node_collection_exit import EXIT_FAILED_LOG, NodeCollectionExitService
from apps.node_mgmt.services.sidecar import Sidecar

RETURN_SECRET = "RETURN-SECRET-MUST-NOT-ENTER-LOGS"
CHILD_CONTENT = "CHILD-CONTENT-MUST-NOT-ENTER-LOGS"


def _collector(collector_id, name):
    return Collector.objects.create(
        id=collector_id,
        name=name,
        service_type="svc",
        node_operating_system="linux",
        executable_path=f"/bin/{name}",
        execute_parameters="-c",
    )


def _node(node_id, region, ip):
    return Node.objects.create(
        id=node_id,
        name=node_id,
        ip=ip,
        operating_system="linux",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
    )


def _parent(collector, node):
    config = CollectorConfiguration.objects.create(
        name=f"{collector.name}-{node.id}",
        collector=collector,
        cloud_region=node.cloud_region,
        is_pre=True,
    )
    config.nodes.add(node)
    return config


def _heartbeat(region, node_id, ip):
    return SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "returned-host",
            "node_details": {
                "ip": ip,
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors/generated",
                "metrics": {},
                "status": {"status": 0},
                "tags": [
                    f"zone:{region.id}",
                    "group:1",
                    f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.AUTO}",
                    f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
                ],
                "log_file_list": [],
            },
        },
    )


def _last_traceback_name(exc_info):
    traceback_frame = exc_info[2]
    while traceback_frame.tb_next is not None:
        traceback_frame = traceback_frame.tb_next
    return traceback_frame.tb_frame.f_code.co_name


@pytest.mark.django_db
def test_same_node_id_heartbeat_reattaches_monitor_and_log(monkeypatch, caplog):
    monkeypatch.setattr(MonitorInstanceRemovalService, "close_alerts_for_instances", lambda *args, **kwargs: 0)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    region = CloudRegion.objects.create(name="returned-region")
    telegraf = _collector("returned-telegraf", "Telegraf")
    filebeat = _collector("returned-filebeat", "Filebeat")
    node = _node("returned-node", region, "10.44.44.44")
    node.monitor_id = ""
    node.save(update_fields=["monitor_id"])
    host_parent = _parent(telegraf, node)
    log_parent = _parent(filebeat, node)
    host_child = ChildConfig.objects.create(
        id="returned-host-child",
        collect_type="host",
        config_type="cpu",
        content=CHILD_CONTENT,
        collector_config=host_parent,
    )
    mysql_child = ChildConfig.objects.create(
        id="returned-mysql-child",
        collect_type="database",
        config_type="mysql",
        content="[[inputs.mysql]]",
        collector_config=host_parent,
    )
    log_child = ChildConfig.objects.create(
        id="returned-log-child",
        collect_type="log",
        config_type="file",
        content="paths: [/var/log/app]",
        collector_config=log_parent,
    )
    host_object, _ = MonitorObject.objects.get_or_create(name="Host", defaults={"level": "base"})
    mysql_object, _ = MonitorObject.objects.get_or_create(name="MySQL", defaults={"level": "base"})
    host = MonitorInstance.objects.create(id="returned-host", name="returned-host", monitor_object=host_object, node_id=node.id)
    mysql = MonitorInstance.objects.create(id="returned-mysql", name="returned-mysql", monitor_object=mysql_object)
    CollectConfig.objects.create(
        id=host_child.id,
        monitor_instance=host,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    CollectConfig.objects.create(
        id=mysql_child.id,
        monitor_instance=mysql,
        collector="Telegraf",
        collect_type="database",
        config_type="mysql",
        file_type="toml",
        is_child=True,
    )
    log_type = CollectType.objects.create(name="returned-log-type", collector="Filebeat", icon="file")
    log_instance = CollectInstance.objects.create(
        id="returned-log",
        name="returned-log",
        collect_type=log_type,
        node_id=node.id,
    )
    LogCollectConfig.objects.create(id=log_child.id, collect_instance=log_instance, file_type="yaml", is_child=True)

    NodeCollectionExitService.apply(node, operator="alice")
    node.delete()

    caplog.set_level(logging.DEBUG, logger="monitor")
    caplog.set_level(logging.DEBUG, logger="log")
    response = Sidecar.update_node_client(_heartbeat(region, "returned-node", "10.44.44.44"), "returned-node")

    assert response.status_code == 202
    restored = Node.objects.get(id="returned-node")
    host.refresh_from_db()
    mysql.refresh_from_db()
    log_instance.refresh_from_db()
    host_child.refresh_from_db()
    mysql_child.refresh_from_db()
    log_child.refresh_from_db()
    host_config = CollectConfig.objects.get(id=host_child.id)
    mysql_config = CollectConfig.objects.get(id=mysql_child.id)
    assert restored.monitor_id == host.id
    assert host.node_id == restored.id
    assert host.is_deleted is False
    assert mysql.node_id is None
    assert host_config.executor_node_removed is False
    assert host_config.executor_node_id == ""
    assert host_config.executor_node_name == ""
    assert mysql_config.executor_node_removed is False
    assert host_child.content == CHILD_CONTENT
    assert list(host_child.collector_config.nodes.values_list("id", flat=True)) == [restored.id]
    assert list(mysql_child.collector_config.nodes.values_list("id", flat=True)) == [restored.id]
    assert list(log_child.collector_config.nodes.values_list("id", flat=True)) == [restored.id]
    assert NodeCollectorConfiguration.objects.filter(node_id=restored.id, collector_config_id=host_child.collector_config_id).exists()
    assert NodeCollectorConfiguration.objects.filter(node_id=restored.id, collector_config_id=log_child.collector_config_id).exists()
    assert log_instance.node_id == restored.id
    assert log_instance.collector_node_removed is False
    assert log_instance.removed_collector_node_id == ""
    assert log_instance.removed_collector_node_name == ""

    monitor_finished = [record for record in caplog.records if record.msg == MONITOR_RETURN_FINISHED_LOG]
    log_finished = [record for record in caplog.records if record.msg == LOG_RETURN_FINISHED_LOG]
    assert len(monitor_finished) == 1
    assert monitor_finished[0].levelno == logging.DEBUG
    assert monitor_finished[0].args == (safe_log_value(restored.id), 2, safe_log_value(host.id))
    assert monitor_finished[0].getMessage() == MONITOR_RETURN_FINISHED_LOG % monitor_finished[0].args
    assert len(log_finished) == 1
    assert log_finished[0].levelno == logging.DEBUG
    assert log_finished[0].args == (safe_log_value(restored.id), 1)
    assert log_finished[0].getMessage() == LOG_RETURN_FINISHED_LOG % log_finished[0].args
    rendered = "\n".join(logging.Formatter().format(record) for record in (monitor_finished[0], log_finished[0]))
    assert CHILD_CONTENT not in rendered
    assert CHILD_CONTENT not in caplog.text


@pytest.mark.django_db
def test_returned_monitor_id_is_not_overwritten_when_present():
    region = CloudRegion.objects.create(name="returned-keep-region")
    collector = _collector("returned-keep-telegraf", "Telegraf")
    node = _node("returned-keep-node", region, "10.44.44.45")
    node.monitor_id = "preset-monitor"
    node.save(update_fields=["monitor_id"])
    from apps.node_mgmt.models import NodeOrganization

    NodeOrganization.objects.create(node=node, organization=1)
    parent = _parent(collector, node)
    child = ChildConfig.objects.create(
        id="returned-keep-child",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.cpu]]",
        collector_config=parent,
    )
    host_object, _ = MonitorObject.objects.get_or_create(name="Host", defaults={"level": "base"})
    host = MonitorInstance.objects.create(id="returned-keep-host", name="returned-keep-host", monitor_object=host_object)
    CollectConfig.objects.create(
        id=child.id,
        monitor_instance=host,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
        executor_node_removed=True,
        executor_node_id=node.id,
        executor_node_name=node.name,
    )

    Sidecar._notify_collectors_node_returned(node)

    node.refresh_from_db()
    host.refresh_from_db()
    assert node.monitor_id == "preset-monitor"
    assert host.node_id == node.id
    assert CollectConfig.objects.get(id=child.id).executor_node_removed is False


@pytest.mark.django_db
def test_return_notification_failure_does_not_block_heartbeat(monkeypatch, caplog):
    raised = []

    def _boom(*args, **kwargs):
        error = RuntimeError(RETURN_SECRET)
        raised.append(error)
        raise error

    called = []

    def _log_ok(node, organization_ids):
        called.append((node.id, list(organization_ids)))

    monkeypatch.setattr("apps.monitor.services.collector_node_exit.MonitorCollectorNodeExit.on_node_returned", _boom)
    monkeypatch.setattr("apps.log.services.collector_node_exit.LogCollectorNodeExit.on_node_returned", _log_ok)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    region = CloudRegion.objects.create(name="returned-fail-region")

    caplog.set_level(logging.DEBUG, logger="node")
    response = Sidecar.update_node_client(_heartbeat(region, "returned-fail-node", "10.44.44.46"), "returned-fail-node")

    assert response.status_code == 202
    assert Node.objects.filter(id="returned-fail-node").exists()
    assert called == [("returned-fail-node", [1])]
    errors = [record for record in caplog.records if record.msg == EXIT_FAILED_LOG and record.exc_info]
    assert len(errors) == 1
    error_record = errors[0]
    assert error_record.levelno == logging.ERROR
    assert error_record.args == (safe_log_value("returned-fail-node"), "monitor_returned", "RuntimeError")
    assert error_record.getMessage() == EXIT_FAILED_LOG % error_record.args
    assert error_record.exc_info[0] is SafeLogException
    assert error_record.exc_info[1].args == ("RuntimeError",)
    assert error_record.exc_info[2] is raised[0].__traceback__
    assert _last_traceback_name(error_record.exc_info) == "_boom"
    formatted = logging.Formatter().format(error_record)
    assert RETURN_SECRET not in formatted
    assert RETURN_SECRET not in caplog.text


@pytest.mark.django_db
def test_later_heartbeat_retries_collector_return(monkeypatch):
    called = []
    monkeypatch.setattr(Sidecar, "_notify_collectors_node_returned", lambda node: called.append(node.id))
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    region = CloudRegion.objects.create(name="returned-retry-region")

    Sidecar.update_node_client(_heartbeat(region, "returned-retry-node", "10.44.44.48"), "returned-retry-node")
    Sidecar.update_node_client(_heartbeat(region, "returned-retry-node", "10.44.44.48"), "returned-retry-node")

    assert called == ["returned-retry-node", "returned-retry-node"]


@pytest.mark.django_db
def test_return_keeps_other_hosts_when_node_id_is_taken():
    from apps.monitor.services.collector_node_exit import MonitorCollectorNodeExit
    from apps.node_mgmt.models import NodeOrganization

    region = CloudRegion.objects.create(name="returned-collision-region")
    node = _node("returned-collision-node", region, "10.44.44.49")
    NodeOrganization.objects.create(node=node, organization=1)
    host_object, _ = MonitorObject.objects.get_or_create(name="Host", defaults={"level": "base"})
    first = MonitorInstance.objects.create(id="returned-collision-a", name="a", monitor_object=host_object)
    second = MonitorInstance.objects.create(id="returned-collision-b", name="b", monitor_object=host_object)
    for instance, config_id in ((first, "returned-collision-cfg-a"), (second, "returned-collision-cfg-b")):
        CollectConfig.objects.create(
            id=config_id,
            monitor_instance=instance,
            collector="Telegraf",
            collect_type="host",
            config_type="cpu",
            file_type="toml",
            is_child=True,
            executor_node_removed=True,
            executor_node_id=node.id,
            executor_node_name=node.name,
        )

    returned = MonitorCollectorNodeExit.on_node_returned(node, [1])

    first.refresh_from_db()
    second.refresh_from_db()
    linked = [item for item in (first, second) if item.node_id == node.id]
    assert len(linked) == 1
    assert returned == linked[0].id
    assert CollectConfig.objects.filter(executor_node_removed=True).count() == 0
