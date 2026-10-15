"""新内置采集器写入后，为已纳管节点补齐缺失的预置配置。"""

import logging
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.logger import SafeLogException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Collector, CollectorConfiguration, CollectorDefaultBackfill, Node
from apps.node_mgmt.services.collector_default_backfill import NODE_FAILED_LOG
from apps.node_mgmt.tasks.collector_default_backfill import (
    COMPLETED_LOG,
    EXHAUSTED_LOG,
    TASK_FAILED_LOG,
    backfill_collector_default_configs,
)

SECRET_SENTINEL = "password=BACKFILL-SECRET-SENTINEL"
pytestmark = pytest.mark.django_db


def _region():
    return CloudRegion.objects.create(name=f"cr-backfill-{uuid.uuid4().hex[:8]}")


def _node(region, suffix, **over):
    data = dict(
        id=f"node-backfill-{suffix}",
        name=f"n-{suffix}",
        ip=f"10.8.0.{suffix}",
        operating_system="linux",
        cpu_architecture="x86_64",
        collector_configuration_directory="/opt/fusion-collectors",
        cloud_region=region,
    )
    data.update(over)
    return Node.objects.create(**data)


def _payload(collector_id="telegraf-linux-x64", **over):
    data = dict(
        id=collector_id,
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        execute_parameters="-c",
        controller_default_run=True,
        default_config={"nats": "interval = 10"},
        tags=[],
    )
    data.update(over)
    return data


def test_new_builtin_collector_backfills_matching_managed_nodes_only():
    region = _region()
    linux = _node(region, 1)
    windows = _node(region, 2, operating_system="windows", ip="10.8.0.2")
    arm = _node(region, 3, cpu_architecture="arm64", ip="10.8.0.3")
    aliased = _node(region, 4, cpu_architecture="amd64", ip="10.8.0.4")
    upper_alias = _node(region, 6, cpu_architecture="AMD64", ip="10.8.0.6")
    unknown_arch = _node(region, 5, cpu_architecture="", ip="10.8.0.5")
    unrecognized = _node(region, 7, cpu_architecture="not-a-real-arch", ip="10.8.0.7")

    assert import_collector([_payload()]) is None
    assert CollectorConfiguration.objects.count() == 0
    assert CollectorDefaultBackfill.objects.filter(collector_id="telegraf-linux-x64", status="pending").count() == 1

    result = backfill_collector_default_configs()

    assert result["claimed"] is True
    created_node_ids = set(CollectorConfiguration.objects.filter(is_pre=True).values_list("nodes__id", flat=True))
    assert created_node_ids == {linux.id, aliased.id, upper_alias.id, unknown_arch.id, unrecognized.id}
    assert windows.id not in created_node_ids
    assert arm.id not in created_node_ids
    assert CollectorDefaultBackfill.objects.get(collector_id="telegraf-linux-x64").status == "done"
    again = backfill_collector_default_configs()
    assert again["claimed"] is False
    assert CollectorConfiguration.objects.count() == 5


def test_update_existing_collector_does_not_schedule_backfill_or_rewrite_config():
    region = _region()
    node = _node(region, 1)
    import_collector([_payload()])
    backfill_collector_default_configs()
    config = CollectorConfiguration.objects.get(nodes=node)
    original = config.config_template
    CollectorDefaultBackfill.objects.all().delete()

    updated = _payload(default_config={"nats": "interval = 99"})
    assert import_collector([updated]) is None

    assert CollectorDefaultBackfill.objects.count() == 0
    config.refresh_from_db()
    assert config.config_template == original


def test_custom_and_existing_pre_configs_stay_unchanged():
    region = _region()
    custom_node = _node(region, 1)
    pre_node = _node(region, 2, ip="10.8.0.2")
    other_node = _node(region, 3, ip="10.8.0.3")
    import_collector([_payload()])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    custom = CollectorConfiguration.objects.create(
        name="custom-telegraf",
        collector=collector,
        config_template="user-template",
        is_pre=False,
        cloud_region=region,
    )
    custom.nodes.add(custom_node)
    pre = CollectorConfiguration.objects.create(
        name=f"Telegraf-{pre_node.id}",
        collector=collector,
        config_template="old-pre",
        is_pre=True,
        cloud_region=region,
    )
    pre.nodes.add(pre_node)
    other = Collector.objects.create(
        id="vector-linux-x64",
        name="Vector",
        service_type="svc",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/bin/vector",
        execute_parameters="-c",
        controller_default_run=True,
        default_config={"nats": "vector"},
    )
    other_config = CollectorConfiguration.objects.create(
        name="vector-kept",
        collector=other,
        config_template="vector-old",
        is_pre=True,
        cloud_region=region,
    )
    other_config.nodes.add(other_node)

    backfill_collector_default_configs()

    custom.refresh_from_db()
    pre.refresh_from_db()
    other_config.refresh_from_db()
    assert custom.config_template == "user-template"
    assert pre.config_template == "old-pre"
    assert other_config.config_template == "vector-old"
    assert CollectorConfiguration.objects.filter(collector=collector, nodes=other_node, is_pre=True).exists()
    assert CollectorConfiguration.objects.filter(collector=collector).count() == 3


def test_container_collector_is_limited_to_container_nodes_and_appends_add_config():
    region = _region()
    host = _node(region, 1)
    container = _node(region, 2, ip="10.8.0.2", node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    tagged = _node(
        region,
        3,
        ip="10.8.0.3",
        node_type=ControllerConstants.NODE_TYPE_HOST,
        tags=[f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}"],
    )
    payload = _payload(
        "snmptrapd-linux",
        name="Snmptrapd",
        default_config={"nats": "base", "add_config": "extra-line"},
    )
    import_collector([payload])

    backfill_collector_default_configs()

    assert not CollectorConfiguration.objects.filter(nodes=host).exists()
    for node in (container, tagged):
        config = CollectorConfiguration.objects.get(nodes=node, is_pre=True)
        assert "base" in config.config_template
        assert "extra-line" in config.config_template


def test_lower_priority_architecture_does_not_replace_existing_named_config():
    region = _region()
    occupied = _node(region, 1)
    free = _node(region, 2, ip="10.8.0.2")
    empty_arch = _node(region, 3, ip="10.8.0.3", cpu_architecture="")
    generic = Collector.objects.create(
        id="telegraf-linux-generic",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        cpu_architecture="",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
        controller_default_run=True,
        default_config={"nats": "generic"},
        is_pre=True,
    )
    existing = CollectorConfiguration.objects.create(
        name=f"Telegraf-{occupied.id}",
        collector=generic,
        config_template="generic-kept",
        is_pre=True,
        cloud_region=region,
    )
    existing.nodes.add(occupied)
    import_collector([_payload()])

    backfill_collector_default_configs()

    existing.refresh_from_db()
    assert existing.config_template == "generic-kept"
    assert existing.collector_id == generic.id
    assert CollectorConfiguration.objects.filter(nodes=free, collector_id="telegraf-linux-x64").exists()
    assert not CollectorConfiguration.objects.filter(nodes=empty_arch, collector_id="telegraf-linux-x64").exists()


def test_one_node_failure_does_not_block_others_and_retries_then_stops(caplog):
    good_region = _region()
    bad_region = _region()
    good = _node(good_region, 1)
    _node(bad_region, 2, ip="10.8.0.2")
    import_collector([_payload(default_config={"nats": "ok {{ HOST }}"})])

    def env_for(region_id, keys=None):
        if region_id == bad_region.id:
            raise RuntimeError(SECRET_SENTINEL)
        return {"SIDECAR_INPUT_MODE": "nats", "HOST": "10.1.1.1"}

    caplog.set_level(logging.DEBUG, logger="node")
    with patch("apps.node_mgmt.services.collector_default_backfill.RegionService.get_cloud_region_envconfig", side_effect=env_for):
        for _ in range(4):
            backfill_collector_default_configs()
        with caplog.at_level(logging.DEBUG, logger="node"):
            backfill_collector_default_configs()

    assert CollectorConfiguration.objects.filter(nodes=good, is_pre=True).get().config_template == "ok 10.1.1.1"
    row = CollectorDefaultBackfill.objects.get(collector_id="telegraf-linux-x64")
    assert row.status == "failed"
    assert row.attempts == 5
    assert CollectorConfiguration.objects.count() == 1
    node_records = [record for record in caplog.records if record.msg == NODE_FAILED_LOG]
    assert node_records
    assert all(record.levelno == logging.WARNING for record in node_records)
    node_record = node_records[-1]
    assert node_record.args[2] == "RuntimeError"
    assert node_record.getMessage() == NODE_FAILED_LOG % node_record.args
    assert "failed_stage=render" in node_record.getMessage()
    error_records = [record for record in caplog.records if record.msg == EXHAUSTED_LOG and record.exc_info]
    assert len(error_records) == 1
    error_record = error_records[0]
    assert error_record.levelno == logging.ERROR
    assert error_record.args[1:] == ("RuntimeError", 5)
    assert error_record.getMessage() == EXHAUSTED_LOG % error_record.args
    assert error_record.exc_info[0] is SafeLogException
    assert error_record.exc_info[1].args == ("RuntimeError",)
    traceback_frame = error_record.exc_info[2]
    while traceback_frame.tb_next is not None:
        traceback_frame = traceback_frame.tb_next
    assert traceback_frame.tb_frame.f_code.co_name == "env_for"
    formatted = logging.Formatter().format(error_record)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in logging.Formatter().format(node_record)
    assert SECRET_SENTINEL not in caplog.text


def test_node_limit_resumes_from_cursor(monkeypatch):
    monkeypatch.setattr("apps.node_mgmt.services.collector_default_backfill.NODE_LIMIT_PER_RUN", 1)
    region = _region()
    first = _node(region, 1, id="n-1", ip="10.8.0.1")
    second = _node(region, 2, id="n-2", ip="10.8.0.2")
    import_collector([_payload()])

    backfill_collector_default_configs()
    row = CollectorDefaultBackfill.objects.get()
    assert row.status == "pending"
    assert row.cursor_id == first.id
    assert CollectorConfiguration.objects.filter(nodes=first).exists()
    assert not CollectorConfiguration.objects.filter(nodes=second).exists()

    backfill_collector_default_configs()
    row.refresh_from_db()
    assert row.status == "done"
    assert CollectorConfiguration.objects.filter(nodes=second).exists()


def test_stale_worker_cannot_overwrite_reclaimed_backfill():
    region = _region()
    _node(region, 1)
    import_collector([_payload()])
    old_lock = timezone.now() - timedelta(minutes=20)
    CollectorDefaultBackfill.objects.update(
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=old_lock,
        cursor_id="stale-cursor",
        attempts=1,
    )
    new_lock = timezone.now()
    CollectorDefaultBackfill.objects.update(
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=new_lock,
        cursor_id="owner-cursor",
        attempts=2,
    )

    from apps.node_mgmt.tasks.collector_default_backfill import _apply_result

    _apply_result(
        "telegraf-linux-x64",
        old_lock,
        {"created": 9, "failed": 0, "hit_limit": False, "cursor_id": "", "last_error": None},
    )

    row = CollectorDefaultBackfill.objects.get()
    assert row.status == CollectorDefaultBackfill.STATUS_RUNNING
    assert row.cursor_id == "owner-cursor"
    assert row.attempts == 2
    assert row.locked_at is not None


def test_stale_running_backfill_is_reclaimed():
    region = _region()
    node = _node(region, 1)
    import_collector([_payload()])
    CollectorDefaultBackfill.objects.update(
        status=CollectorDefaultBackfill.STATUS_RUNNING,
        locked_at=timezone.now() - timedelta(minutes=16),
    )

    backfill_collector_default_configs()

    assert CollectorConfiguration.objects.filter(nodes=node, is_pre=True).exists()
    assert CollectorDefaultBackfill.objects.get().status == "done"


def test_hard_failure_keeps_pending_and_logs_one_safe_traceback(caplog):
    region = _region()
    _node(region, 1)
    import_collector([_payload()])
    error = RuntimeError(SECRET_SENTINEL)
    caplog.set_level(logging.DEBUG, logger="node")

    with patch(
        "apps.node_mgmt.tasks.collector_default_backfill.execute_collector_default_backfill",
        side_effect=error,
    ):
        result = backfill_collector_default_configs()

    assert result["claimed"] is True
    row = CollectorDefaultBackfill.objects.get()
    assert row.status == "pending"
    assert row.attempts == 1
    assert CollectorConfiguration.objects.count() == 0
    failed_records = [record for record in caplog.records if record.levelno == logging.ERROR and record.exc_info]
    assert len(failed_records) == 1
    record = failed_records[0]
    assert record.msg == TASK_FAILED_LOG
    assert record.args[1:] == ("backfill", "RuntimeError")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(record)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text


def test_success_log_uses_stable_template(caplog):
    region = _region()
    _node(region, 1)
    import_collector([_payload()])
    caplog.set_level(logging.INFO, logger="node")

    backfill_collector_default_configs()

    records = [record for record in caplog.records if record.msg == COMPLETED_LOG]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.args[1:] == ("done", 1, 0)
    assert record.getMessage() == COMPLETED_LOG % record.args


def test_non_default_collector_does_not_create_backfill_row():
    import_collector([_payload(controller_default_run=False)])
    assert Collector.objects.filter(id="telegraf-linux-x64").exists()
    assert CollectorDefaultBackfill.objects.count() == 0


def test_commit_clears_catalog_etag_and_enqueues_only_for_backfill(django_capture_on_commit_callbacks):
    with (
        patch("apps.node_mgmt.tasks.collector_default_backfill.backfill_collector_default_configs.delay") as delay,
        patch("apps.node_mgmt.tasks.collector_default_backfill.cache.delete") as delete_cache,
        django_capture_on_commit_callbacks(execute=True),
    ):
        import_collector([_payload()])
    delay.assert_called_once_with()
    delete_cache.assert_called_once_with("collectors_etag")

    with (
        patch("apps.node_mgmt.tasks.collector_default_backfill.backfill_collector_default_configs.delay") as delay,
        patch("apps.node_mgmt.tasks.collector_default_backfill.cache.delete") as delete_cache,
        django_capture_on_commit_callbacks(execute=True),
    ):
            import_collector([_payload("plain-linux", name="Plain", controller_default_run=False, default_config={})])
    delay.assert_not_called()
    delete_cache.assert_not_called()


@pytest.mark.unit
def test_backfill_beat_runs_every_five_minutes():
    from apps.node_mgmt.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE["backfill_collector_default_configs"]
    assert entry["task"] == "apps.node_mgmt.tasks.collector_default_backfill.backfill_collector_default_configs"
    assert entry["schedule"].minute == set(range(0, 60, 5))
