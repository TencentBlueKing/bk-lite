"""失败采集器定时 restart：3-tries 下发，已停止/空配置 Beats/离线/在途跳过，日志契约。"""

import logging
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.logger import SafeLogException
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Action
from apps.node_mgmt.tasks.collector_auto_restart import (
    COMPLETED_LOG,
    FAILED_LOG,
    SKIPPED_LOG,
    restart_failed_collectors,
)

THREE_TRIES = CollectorConstants.SIDECAR_COLLECTOR_START_RETRY_EXHAUSTED
EMPTY_MODULE = CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[0]
SECRET_SENTINEL = "password=AUTO-RESTART-SECRET-SENTINEL payload=do-not-log"


def _region():
    return CloudRegion.objects.create(name=f"cr-auto-restart-{uuid.uuid4().hex[:8]}")


def _collector(name, **over):
    suffix = uuid.uuid4().hex[:8]
    data = dict(
        id=f"{name.lower()}-{suffix}",
        name=name,
        service_type="svc",
        node_operating_system="linux",
        executable_path=f"/opt/fusion-collectors/bin/{name.lower()}",
        execute_parameters="-c",
    )
    data.update(over)
    return Collector.objects.create(**data)


def _node(region, collectors_status, *, updated_at=None, **over):
    suffix = uuid.uuid4().hex[:8]
    data = dict(
        id=f"node-ar-{suffix}",
        name=f"n-{suffix}",
        ip="10.9.0.1",
        operating_system="linux",
        collector_configuration_directory="/opt/fusion-collectors",
        cloud_region=region,
        status={"collectors": collectors_status},
    )
    data.update(over)
    node = Node.objects.create(**data)
    if updated_at is not None:
        Node.objects.filter(id=node.id).update(updated_at=updated_at)
        node.refresh_from_db()
    return node


def _failed_item(collector, verbose_message=THREE_TRIES, status=2):
    return {
        "collector_id": collector.id,
        "status": status,
        "verbose_message": verbose_message,
    }


@pytest.fixture
def patch_timeout_task():
    with patch("apps.node_mgmt.services.node.timeout_collector_action_task.apply_async") as apply_mock:
        yield apply_mock


def _restart_tasks():
    return CollectorActionTask.objects.filter(action="restart")


def _restart_actions():
    return list(Action.objects.all())


@pytest.mark.django_db
def test_three_tries_dispatches_restart_for_telegraf_nats_vector_and_beats(patch_timeout_task):
    region = _region()
    telegraf = _collector("Telegraf")
    nats_executor = _collector("NATS-Executor")
    vector = _collector("Vector")
    filebeat = _collector("Filebeat")
    node = _node(
        region,
        [
            _failed_item(telegraf),
            _failed_item(nats_executor),
            _failed_item(vector),
            _failed_item(filebeat),
        ],
    )

    result = restart_failed_collectors()

    assert result["hit_count"] == 4
    assert result["dispatched_tasks"] == 4
    tasks = list(_restart_tasks())
    assert len(tasks) == 4
    assert {task.collector_id for task in tasks} == {telegraf.id, nats_executor.id, vector.id, filebeat.id}
    assert {task.created_by for task in tasks} == {"system"}
    actions = Action.objects.get(node=node).action
    assert len(actions) == 4
    for item in actions:
        assert item["properties"] == {"restart": True}
        assert "systemctl" not in str(item).lower()
    assert patch_timeout_task.call_count == 4


@pytest.mark.django_db
def test_stopped_collectors_are_not_restarted(patch_timeout_task):
    region = _region()
    telegraf = _collector("Telegraf")
    vector = _collector("Vector")
    _node(region, [_failed_item(telegraf, status=3), _failed_item(vector, status=4)])

    result = restart_failed_collectors()

    assert result["hit_count"] == 0
    assert result["dispatched_tasks"] == 0
    assert result["skip_stopped"] == 2
    assert _restart_tasks().count() == 0
    assert _restart_actions() == []


@pytest.mark.django_db
def test_empty_beats_config_is_not_restarted_even_with_three_tries_text(patch_timeout_task):
    region = _region()
    filebeat = _collector("Filebeat")
    metricbeat = _collector("Metricbeat")
    winlogbeat = _collector("Winlogbeat")
    _node(
        region,
        [
            _failed_item(filebeat, verbose_message=EMPTY_MODULE),
            _failed_item(
                metricbeat,
                verbose_message=f"{THREE_TRIES}\n{EMPTY_MODULE}",
            ),
            _failed_item(winlogbeat, verbose_message=CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[2]),
        ],
    )

    result = restart_failed_collectors()

    assert result["hit_count"] == 0
    assert result["skip_empty_beats"] == 3
    assert _restart_tasks().count() == 0


@pytest.mark.django_db
def test_offline_node_failed_collector_is_not_restarted(patch_timeout_task):
    region = _region()
    telegraf = _collector("Telegraf")
    _node(
        region,
        [_failed_item(telegraf)],
        updated_at=timezone.now() - timedelta(minutes=2),
    )

    result = restart_failed_collectors()

    assert result["scanned_nodes"] == 0
    assert result["hit_count"] == 0
    assert result["skip_offline"] == 1
    assert _restart_tasks().count() == 0
    assert _restart_actions() == []


@pytest.mark.django_db
@pytest.mark.parametrize("in_flight_status", ["waiting", "running"])
def test_in_flight_restart_is_not_dispatched_again(patch_timeout_task, in_flight_status):
    region = _region()
    telegraf = _collector("Telegraf")
    node = _node(region, [_failed_item(telegraf)])
    task = CollectorActionTask.objects.create(
        collector=telegraf,
        cloud_region=region,
        action="restart",
        status=in_flight_status,
        total_count=1,
        created_by="ops",
    )
    CollectorActionTaskNode.objects.create(task=task, node=node, status=in_flight_status, result={})

    result = restart_failed_collectors()

    assert result["hit_count"] == 0
    assert result["skip_in_flight"] == 1
    assert _restart_tasks().count() == 1
    assert _restart_actions() == []


@pytest.mark.django_db
def test_groups_same_collector_across_nodes_into_one_batch(patch_timeout_task):
    region = _region()
    telegraf = _collector("Telegraf")
    node_a = _node(region, [_failed_item(telegraf)], ip="10.9.0.2")
    node_b = _node(region, [_failed_item(telegraf)], ip="10.9.0.3")

    result = restart_failed_collectors()

    assert result["hit_count"] == 2
    assert result["dispatched_tasks"] == 1
    task = _restart_tasks().get()
    assert task.collector_id == telegraf.id
    assert task.total_count == 2
    assert task.created_by == "system"
    assert CollectorActionTaskNode.objects.filter(task=task).count() == 2
    assert Action.objects.filter(node_id__in=[node_a.id, node_b.id]).count() == 2


@pytest.mark.unit
def test_hourly_beat_schedule_points_to_restart_task():
    from apps.node_mgmt.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE["restart_failed_collectors"]
    assert entry["task"] == "apps.node_mgmt.tasks.collector_auto_restart.restart_failed_collectors"
    assert entry["schedule"].minute == {0}
    assert entry["schedule"].hour == set(range(24))


@pytest.mark.django_db
def test_summary_log_uses_stable_template_and_skips_stay_debug(patch_timeout_task, caplog):
    region = _region()
    telegraf = _collector("Telegraf")
    filebeat = _collector("Filebeat")
    _node(region, [_failed_item(telegraf), _failed_item(filebeat, verbose_message=EMPTY_MODULE)])

    caplog.set_level(logging.DEBUG, logger="node")
    result = restart_failed_collectors()

    info_records = [record for record in caplog.records if record.msg == COMPLETED_LOG]
    assert len(info_records) == 1
    record = info_records[0]
    assert record.levelno == logging.INFO
    assert record.name == "node"
    assert record.args == (
        result["scanned_nodes"],
        result["hit_count"],
        result["dispatched_tasks"],
        result["skip_stopped"],
        result["skip_empty_beats"],
        result["skip_offline"],
        result["skip_in_flight"],
    )
    formatted = logging.Formatter().format(record)
    assert record.getMessage() == COMPLETED_LOG % record.args
    assert "event=collector_auto_restart_completed" in formatted
    assert SECRET_SENTINEL not in formatted
    skip_records = [item for item in caplog.records if item.msg == SKIPPED_LOG]
    assert skip_records
    assert all(item.levelno == logging.DEBUG for item in skip_records)
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)


@pytest.mark.django_db
def test_dispatch_failure_has_single_traceback_and_omits_sensitive_sentinel(patch_timeout_task, caplog):
    region = _region()
    telegraf = _collector("Telegraf")
    _node(region, [_failed_item(telegraf)])
    error = RuntimeError(SECRET_SENTINEL)

    caplog.set_level(logging.DEBUG, logger="node")
    with patch(
        "apps.node_mgmt.services.node.NodeService.batch_operate_node_collector",
        side_effect=error,
    ):
        result = restart_failed_collectors()

    assert result["hit_count"] == 1
    assert result["dispatched_tasks"] == 0
    assert _restart_tasks().count() == 0
    failed_records = [
        record
        for record in caplog.records
        if record.name == "node" and record.levelno == logging.ERROR and record.exc_info
    ]
    assert len(failed_records) == 1
    record = failed_records[0]
    assert record.msg == FAILED_LOG
    assert record.args == (telegraf.id, "dispatch", "RuntimeError")
    assert record.getMessage() == FAILED_LOG % record.args
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(record)
    assert "failed_stage=dispatch" in formatted
    assert "error_type=RuntimeError" in formatted
    assert SECRET_SENTINEL not in record.msg
    assert SECRET_SENTINEL not in str(record.args)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text
    assert "systemctl" not in caplog.text.lower()
