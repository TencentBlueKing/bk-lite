import logging
from types import SimpleNamespace

import pytest

from apps.core.logger import SafeLogException, safe_log_value
from apps.log.models import CollectConfig as LogCollectConfig
from apps.log.models import CollectInstance, CollectType
from apps.log.services.collector_node_exit import LOG_EXIT_FINISHED_LOG, LogCollectorNodeExit
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject
from apps.monitor.services.collector_node_exit import MONITOR_EXIT_FINISHED_LOG, MonitorCollectorNodeExit
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.node_mgmt.models import CloudRegion, Collector, CollectorConfiguration, Node
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import ChildConfig
from apps.node_mgmt.services.node_collection_exit import EXIT_FAILED_LOG, EXIT_FINISHED_LOG, NodeCollectionExitService
from apps.node_mgmt.tasks import installer as installer_tasks


def _collector(collector_id, name):
    return Collector.objects.create(
        id=collector_id,
        name=name,
        service_type="svc",
        node_operating_system="linux",
        executable_path=f"/bin/{name}",
        execute_parameters="-c",
    )


def _node(node_id, region, ip="10.1.1.1"):
    return Node.objects.create(
        id=node_id,
        name=node_id,
        ip=ip,
        operating_system="linux",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
    )


def _parent(collector, node, name=None):
    config = CollectorConfiguration.objects.create(
        name=name or f"{collector.name}-{node.id}",
        collector=collector,
        cloud_region=node.cloud_region,
        is_pre=True,
    )
    config.nodes.add(node)
    return config


def _child(parent, child_id, content):
    return ChildConfig.objects.create(
        id=child_id,
        collect_type="host",
        config_type="cpu",
        content=content,
        collector_config=parent,
    )


def _monitor(instance_id, object_name, node_id=""):
    monitor_object, _ = MonitorObject.objects.get_or_create(name=object_name, defaults={"level": "base"})
    return MonitorInstance.objects.create(
        id=instance_id,
        name=instance_id,
        monitor_object=monitor_object,
        node_id=node_id or None,
    )


@pytest.mark.django_db
def test_node_exit_retires_linked_host_and_frees_default_parent_name(monkeypatch):
    closed = []

    def _close(instance_ids, *, operator, reason, policy_ids=None):
        closed.append((list(instance_ids), operator, reason))
        return 0

    monkeypatch.setattr(MonitorInstanceRemovalService, "close_alerts_for_instances", _close)
    region = CloudRegion.objects.create(name="exit-linked-region")
    collector = _collector("exit-telegraf", "Telegraf")
    node = _node("exit-linked-node", region)
    node.monitor_id = "linked-host"
    node.save(update_fields=["monitor_id"])
    parent = _parent(collector, node)
    child = _child(parent, "linked-child", "[[inputs.cpu]]")
    instance = _monitor("linked-host", "Host", node.id)
    CollectConfig.objects.create(
        id=child.id,
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )

    NodeCollectionExitService.apply(node, operator="alice")
    node.delete()

    instance.refresh_from_db()
    parent.refresh_from_db()
    child.refresh_from_db()
    assert instance.is_deleted is True
    assert instance.is_active is False
    assert instance.node_id is None
    assert child.content == "[[inputs.cpu]]"
    assert child.collector_config_id == parent.id
    assert parent.name == f"detached-{parent.id}"
    assert closed == [(["linked-host"], "alice", "linked_node_removed")]
    CollectorConfiguration.objects.create(
        name="Telegraf-exit-linked-node",
        collector=collector,
        cloud_region=region,
    )


@pytest.mark.django_db
def test_node_exit_keeps_unlinked_monitor_and_log_configs():
    region = CloudRegion.objects.create(name="exit-unlinked-region")
    collector = _collector("exit-filebeat", "Filebeat")
    node = _node("exit-unlinked-node", region)
    parent = _parent(collector, node)
    monitor_child = _child(parent, "mysql-child", "[[inputs.mysql]]")
    log_child = _child(parent, "log-child", "paths: [/var/log/app]")
    monitor_instance = _monitor("mysql-1", "MySQL")
    CollectConfig.objects.create(
        id=monitor_child.id,
        monitor_instance=monitor_instance,
        collector="Filebeat",
        collect_type="mysql",
        config_type="mysql",
        file_type="toml",
        is_child=True,
    )
    collect_type = CollectType.objects.create(name="file", collector="Filebeat", icon="file")
    log_instance = CollectInstance.objects.create(
        id="log-1",
        name="app",
        collect_type=collect_type,
        node_id=node.id,
    )
    LogCollectConfig.objects.create(
        id=log_child.id,
        collect_instance=log_instance,
        file_type="yaml",
        is_child=True,
    )

    NodeCollectionExitService.apply(node, operator="alice")
    node.delete()

    monitor_instance.refresh_from_db()
    monitor_config = CollectConfig.objects.get(id=monitor_child.id)
    log_instance.refresh_from_db()
    assert monitor_instance.is_deleted is False
    assert monitor_config.executor_node_removed is True
    assert monitor_config.executor_node_id == "exit-unlinked-node"
    assert monitor_config.executor_node_name == "exit-unlinked-node"
    assert ChildConfig.objects.filter(id=monitor_child.id, content="[[inputs.mysql]]").exists()
    assert log_instance.collector_node_removed is True
    assert log_instance.node_id is None
    assert log_instance.removed_collector_node_name == "exit-unlinked-node"
    assert LogCollectConfig.objects.filter(id=log_child.id).exists()
    assert ChildConfig.objects.filter(id=log_child.id).exists()


@pytest.mark.django_db
def test_reassign_moves_only_the_instance_child_and_clear_deletes_only_that_config():
    region = CloudRegion.objects.create(name="exit-reassign-region")
    collector = _collector("exit-reassign-telegraf", "Telegraf")
    source = _node("exit-source-node", region, ip="10.4.4.1")
    target = _node("exit-target-node", region, ip="10.4.4.2")
    parent = _parent(collector, source)
    mysql_child = _child(parent, "reassign-mysql", "[[inputs.mysql]]")
    redis_child = _child(parent, "reassign-redis", "[[inputs.redis]]")
    mysql = _monitor("reassign-mysql-instance", "MySQL")
    redis = _monitor("reassign-redis-instance", "Redis")
    for instance, child, config_type in (
        (mysql, mysql_child, "mysql"),
        (redis, redis_child, "redis"),
    ):
        CollectConfig.objects.create(
            id=child.id,
            monitor_instance=instance,
            collector="Telegraf",
            collect_type="database",
            config_type=config_type,
            file_type="toml",
            is_child=True,
        )

    NodeCollectionExitService.apply(source, operator="alice")
    MonitorCollectorNodeExit.reassign(mysql.id, target.id)

    mysql_child.refresh_from_db()
    redis_child.refresh_from_db()
    mysql_config = CollectConfig.objects.get(id=mysql_child.id)
    redis_config = CollectConfig.objects.get(id=redis_child.id)
    assert mysql_child.collector_config_id != parent.id
    assert list(mysql_child.collector_config.nodes.values_list("id", flat=True)) == [target.id]
    assert redis_child.collector_config_id == parent.id
    assert mysql_config.executor_node_removed is False
    assert redis_config.executor_node_removed is True

    MonitorCollectorNodeExit.clear(redis.id)

    assert not ChildConfig.objects.filter(id=redis_child.id).exists()
    assert not CollectConfig.objects.filter(id=redis_child.id).exists()
    assert ChildConfig.objects.filter(id=mysql_child.id).exists()
    assert MonitorInstance.objects.filter(id=redis.id, is_deleted=False).exists()


@pytest.mark.django_db
def test_log_clear_keeps_instance_and_reassign_sets_node():
    region = CloudRegion.objects.create(name="exit-log-region")
    collector = _collector("exit-log-filebeat", "Filebeat")
    source = _node("exit-log-source", region, ip="10.5.5.1")
    target = _node("exit-log-target", region, ip="10.5.5.2")
    parent = _parent(collector, source)
    child = _child(parent, "log-reassign-child", "paths: [/var/log/app]")
    collect_type = CollectType.objects.create(name="log-file", collector="Filebeat", icon="file")
    instance = CollectInstance.objects.create(id="log-reassign", name="app", collect_type=collect_type, node_id=source.id)
    LogCollectConfig.objects.create(id=child.id, collect_instance=instance, file_type="yaml", is_child=True)

    NodeCollectionExitService.apply(source, operator="alice")
    LogCollectorNodeExit.reassign(instance.id, target.id)

    instance.refresh_from_db()
    child.refresh_from_db()
    parent.refresh_from_db()
    assert instance.collector_node_removed is False
    assert instance.node_id == target.id
    assert child.collector_config_id != parent.id
    assert list(child.collector_config.nodes.values_list("id", flat=True)) == [target.id]
    assert not parent.nodes.filter(id=target.id).exists()

    NodeCollectionExitService.apply(target, operator="alice")
    LogCollectorNodeExit.clear(instance.id)

    instance.refresh_from_db()
    assert instance.id == "log-reassign"
    assert instance.collector_node_removed is False
    assert not LogCollectConfig.objects.filter(collect_instance=instance).exists()
    assert not ChildConfig.objects.filter(id=child.id).exists()


@pytest.mark.django_db
def test_shared_parent_exit_keeps_instances_still_served_by_another_node():
    region = CloudRegion.objects.create(name="exit-shared-region")
    collector = _collector("exit-shared-telegraf", "Telegraf")
    leaving = _node("exit-shared-leaving", region, ip="10.6.6.1")
    staying = _node("exit-shared-staying", region, ip="10.6.6.2")
    shared = _parent(collector, leaving, name="shared-parent")
    shared.nodes.add(staying)
    staying_child = _child(shared, "shared-staying-child", "[[inputs.redis]]")
    staying_log_child = _child(shared, "shared-staying-log-child", "paths: [/var/log/stay]")
    leaving_child = _child(shared, "shared-leaving-child", "paths: [/var/log/leave]")
    exclusive = _parent(collector, leaving, name="exclusive-parent")
    exclusive_child = _child(exclusive, "exclusive-child", "[[inputs.mysql]]")
    staying_monitor = _monitor("shared-staying-monitor", "Redis")
    leaving_monitor = _monitor("exclusive-monitor", "MySQL")
    CollectConfig.objects.create(
        id=staying_child.id,
        monitor_instance=staying_monitor,
        collector="Telegraf",
        collect_type="database",
        config_type="redis",
        file_type="toml",
        is_child=True,
    )
    CollectConfig.objects.create(
        id=exclusive_child.id,
        monitor_instance=leaving_monitor,
        collector="Telegraf",
        collect_type="database",
        config_type="mysql",
        file_type="toml",
        is_child=True,
    )
    collect_type = CollectType.objects.create(name="shared-log", collector="Filebeat", icon="file")
    staying_log = CollectInstance.objects.create(
        id="shared-staying-log",
        name="stay",
        collect_type=collect_type,
        node_id=staying.id,
    )
    leaving_log = CollectInstance.objects.create(
        id="shared-leaving-log",
        name="leave",
        collect_type=collect_type,
        node_id=leaving.id,
    )
    LogCollectConfig.objects.create(id=staying_log_child.id, collect_instance=staying_log, file_type="yaml", is_child=True)
    LogCollectConfig.objects.create(id=leaving_child.id, collect_instance=leaving_log, file_type="yaml", is_child=True)

    NodeCollectionExitService.apply(leaving, operator="alice")

    staying_config = CollectConfig.objects.get(id=staying_child.id)
    leaving_config = CollectConfig.objects.get(id=exclusive_child.id)
    staying_log.refresh_from_db()
    leaving_log.refresh_from_db()
    staying_child.refresh_from_db()
    assert staying_config.executor_node_removed is False
    assert staying_log.collector_node_removed is False
    assert staying_log.node_id == staying.id
    assert staying_child.content == "[[inputs.redis]]"
    assert ChildConfig.objects.filter(id=staying_log_child.id, content="paths: [/var/log/stay]").exists()
    assert leaving_config.executor_node_removed is True
    assert leaving_log.collector_node_removed is True
    assert leaving_log.node_id is None
    assert ChildConfig.objects.filter(id=exclusive_child.id, content="[[inputs.mysql]]").exists()


@pytest.mark.django_db
def test_uninstall_controller_removes_node_after_collection_exit(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="uninstall-exit-region")
    node = _node("uninstall-exit-node", region, ip="10.9.9.9")
    task = ControllerTask.objects.create(cloud_region=region, type="uninstall", status="pending", created_by="alice")
    ControllerTaskNode.objects.create(
        task=task,
        ip=node.ip,
        os="linux",
        port=22,
        username="root",
        password="cipher",
        node_id=node.id,
        status="waiting",
        result={},
    )
    monkeypatch.setattr(installer_tasks, "AESCryptor", lambda: SimpleNamespace(decode=lambda value: "secret"))
    monkeypatch.setattr(installer_tasks, "exec_command_to_remote", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer_tasks, "get_uninstall_command", lambda os_name: "uninstall")

    caplog.set_level(logging.DEBUG, logger="node")
    installer_tasks.uninstall_controller(task.id)

    assert not Node.objects.filter(id=node.id).exists()
    task.refresh_from_db()
    assert task.status == "finished"
    finished = [record for record in caplog.records if record.msg == EXIT_FINISHED_LOG]
    assert len(finished) == 1
    assert finished[0].args == (safe_log_value(node.id), 0)
    assert finished[0].getMessage() == EXIT_FINISHED_LOG % finished[0].args
    formatted = logging.Formatter().format(finished[0])
    assert "cipher" not in formatted
    assert "secret" not in formatted
    assert "cipher" not in caplog.text
    assert "secret" not in caplog.text


CHILD_CONTENT_SENTINEL = "CHILD-CONTENT-MUST-NOT-ENTER-LOGS"
MONITOR_FAILURE_SENTINEL = "MONITOR-EXIT-SECRET-MUST-NOT-ENTER-LOGS"


def _last_traceback_name(exc_info):
    traceback_frame = exc_info[2]
    while traceback_frame.tb_next is not None:
        traceback_frame = traceback_frame.tb_next
    return traceback_frame.tb_frame.f_code.co_name


@pytest.mark.django_db
def test_node_exit_logs_bound_ids_and_omits_child_content(caplog):
    region = CloudRegion.objects.create(name="exit-log-region")
    collector = _collector("exit-log-telegraf", "Telegraf")
    node = _node("exit\r\nlog-node", region)
    parent = _parent(collector, node)
    child = _child(parent, "log-safe-child", CHILD_CONTENT_SENTINEL)
    instance = _monitor("log-safe-host", "Host", node.id)
    CollectConfig.objects.create(
        id=child.id,
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    log_type = CollectType.objects.create(name="exit-log-type", collector="Telegraf", icon="icon")
    log_instance = CollectInstance.objects.create(
        id="exit-log-instance",
        name="exit-log-instance",
        collect_type=log_type,
        node_id=node.id,
    )

    caplog.set_level(logging.DEBUG, logger="node")
    caplog.set_level(logging.DEBUG, logger="monitor")
    caplog.set_level(logging.DEBUG, logger="log")
    NodeCollectionExitService.apply(node, operator="alice")

    node.refresh_from_db()
    child.refresh_from_db()
    instance.refresh_from_db()
    log_instance.refresh_from_db()
    assert node.id == "exit\r\nlog-node"
    assert child.content == CHILD_CONTENT_SENTINEL
    assert instance.is_deleted is True
    assert log_instance.collector_node_removed is True
    assert log_instance.node_id is None

    finished = [record for record in caplog.records if record.msg == EXIT_FINISHED_LOG]
    monitor_finished = [record for record in caplog.records if record.msg == MONITOR_EXIT_FINISHED_LOG]
    log_finished = [record for record in caplog.records if record.msg == LOG_EXIT_FINISHED_LOG]
    assert len(finished) == 1
    assert len(monitor_finished) == 1
    assert len(log_finished) == 1
    bounded_id = safe_log_value(node.id)
    assert "\r" not in bounded_id and "\n" not in bounded_id
    assert finished[0].levelno == logging.INFO
    assert finished[0].args == (bounded_id, 2)
    assert finished[0].getMessage() == EXIT_FINISHED_LOG % finished[0].args
    assert monitor_finished[0].levelno == logging.DEBUG
    assert monitor_finished[0].args[0] == bounded_id
    assert monitor_finished[0].getMessage() == MONITOR_EXIT_FINISHED_LOG % monitor_finished[0].args
    assert log_finished[0].levelno == logging.DEBUG
    assert log_finished[0].args == (bounded_id, 1)
    assert log_finished[0].getMessage() == LOG_EXIT_FINISHED_LOG % log_finished[0].args
    rendered = "\n".join(logging.Formatter().format(record) for record in (finished[0], monitor_finished[0], log_finished[0]))
    assert CHILD_CONTENT_SENTINEL not in rendered
    assert CHILD_CONTENT_SENTINEL not in caplog.text
    assert "\r" not in finished[0].getMessage()
    assert not [record for record in caplog.records if record.levelno == logging.ERROR and record.exc_info]


@pytest.mark.django_db
def test_monitor_exit_failure_logs_one_safe_traceback_and_keeps_exit(monkeypatch, caplog):
    raised = []

    def _boom(*args, **kwargs):
        error = RuntimeError(MONITOR_FAILURE_SENTINEL)
        raised.append(error)
        raise error

    monkeypatch.setattr(
        "apps.monitor.services.collector_node_exit.MonitorCollectorNodeExit.on_node_removed",
        _boom,
    )
    region = CloudRegion.objects.create(name="exit-monitor-fail-region")
    collector = _collector("exit-fail-telegraf", "Telegraf")
    node = _node("exit-monitor-fail", region)
    parent = _parent(collector, node)
    child = _child(parent, "fail-child", CHILD_CONTENT_SENTINEL)
    log_type = CollectType.objects.create(name="exit-fail-type", collector="Telegraf", icon="icon")
    log_instance = CollectInstance.objects.create(
        id="exit-fail-log",
        name="exit-fail-log",
        collect_type=log_type,
        node_id=node.id,
    )

    caplog.set_level(logging.DEBUG, logger="node")
    caplog.set_level(logging.DEBUG, logger="log")
    NodeCollectionExitService.apply(node, operator="alice")

    parent.refresh_from_db()
    child.refresh_from_db()
    log_instance.refresh_from_db()
    assert parent.name == f"detached-{parent.id}"
    assert child.content == CHILD_CONTENT_SENTINEL
    assert log_instance.collector_node_removed is True
    assert str(raised[0]) == MONITOR_FAILURE_SENTINEL

    errors = [record for record in caplog.records if record.msg == EXIT_FAILED_LOG and record.exc_info]
    assert len(errors) == 1
    error_record = errors[0]
    assert error_record.levelno == logging.ERROR
    assert error_record.args == (safe_log_value(node.id), "monitor", "RuntimeError")
    assert error_record.getMessage() == EXIT_FAILED_LOG % error_record.args
    assert error_record.exc_info[0] is SafeLogException
    assert error_record.exc_info[1].args == ("RuntimeError",)
    assert error_record.exc_info[2] is raised[0].__traceback__
    assert _last_traceback_name(error_record.exc_info) == "_boom"
    formatted = logging.Formatter().format(error_record)
    assert MONITOR_FAILURE_SENTINEL not in formatted
    assert CHILD_CONTENT_SENTINEL not in formatted
    assert MONITOR_FAILURE_SENTINEL not in caplog.text
    assert CHILD_CONTENT_SENTINEL not in caplog.text
    assert [record for record in caplog.records if record.msg == LOG_EXIT_FINISHED_LOG]
    assert [record for record in caplog.records if record.msg == EXIT_FINISHED_LOG]
