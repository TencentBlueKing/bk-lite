"""子对象专用发现：调度、scoped 投影、创建入队与日志契约。"""

import logging
import traceback
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.monitor.models.monitor_object import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.services.child_instance_discovery import (
    CHILD_DISCOVERY_FULL_SYNC_SECONDS,
    CHILD_DISCOVERY_MIN_INTERVAL_SECONDS,
    CHILD_DISCOVERY_WARMUP_SECONDS,
    LOG_CANCELLED,
    LOG_COMPLETED,
    LOG_FAILED,
    LOG_SCHEDULED,
    LOG_SKIPPED,
    LOG_STARTED,
    LOG_STOPPED,
    cancel_child_instance_discovery,
    child_discovery_task_id,
    enqueue_child_instance_discovery,
    format_vm_step,
    inject_promql_label_matchers,
    next_child_discovery_countdown,
    normalize_collect_interval,
    run_child_instance_discovery,
)
from apps.monitor.tasks.services.sync_instance import SyncInstance


def _vm_result(*items):
    return {"data": {"result": list(items)}}


def test_full_sync_beat_remains_every_ten_minutes():
    from apps.monitor.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE["sync_instance_and_group"]
    assert entry["task"] == "apps.monitor.tasks.grouping_rule.sync_instance_and_group"
    assert entry["schedule"]._orig_minute == "*/10"


class TestNextChildDiscoveryCountdown:
    def test_interval_60_skips_one_minute_warmup(self):
        assert next_child_discovery_countdown(0, 60) == 60
        assert next_child_discovery_countdown(CHILD_DISCOVERY_WARMUP_SECONDS - 1, 60) == 60
        assert next_child_discovery_countdown(CHILD_DISCOVERY_WARMUP_SECONDS, 60) == 60

    def test_interval_300_warms_up_then_follows_collect_interval(self):
        assert next_child_discovery_countdown(0, 300) == CHILD_DISCOVERY_MIN_INTERVAL_SECONDS
        assert (
            next_child_discovery_countdown(CHILD_DISCOVERY_WARMUP_SECONDS - 1, 300)
            == CHILD_DISCOVERY_MIN_INTERVAL_SECONDS
        )
        assert next_child_discovery_countdown(CHILD_DISCOVERY_WARMUP_SECONDS, 300) == 300

    def test_interval_at_least_full_sync_stops_after_warmup(self):
        assert next_child_discovery_countdown(0, CHILD_DISCOVERY_FULL_SYNC_SECONDS) == 60
        assert next_child_discovery_countdown(
            CHILD_DISCOVERY_WARMUP_SECONDS, CHILD_DISCOVERY_FULL_SYNC_SECONDS
        ) is None


class TestNormalizeAndVmStep:
    def test_normalize_collect_interval(self):
        assert normalize_collect_interval(None, "", "abc") == 60
        assert normalize_collect_interval("300", 15) == 300
        assert normalize_collect_interval(0, -1, 45) == 45

    def test_vm_step_not_shorter_than_collect_interval(self):
        assert format_vm_step(60) == "60s"
        assert format_vm_step(300) == "300s"
        assert format_vm_step(30) == "60s"


class TestInjectPromqlLabelMatchers:
    def test_injects_into_existing_selector(self):
        query = inject_promql_label_matchers(
            'kube_node_info{instance_type="k3s"}',
            {"instance_id": "c1"},
        )
        assert query == 'kube_node_info{instance_type="k3s",instance_id="c1"}'

    def test_injects_into_empty_selector(self):
        assert inject_promql_label_matchers("any({}) by (instance_id)", {"instance_id": "h1"}) == (
            'any({instance_id="h1"}) by (instance_id)'
        )

    def test_escapes_quotes(self):
        query = inject_promql_label_matchers('up{job="a"}', {"instance_id": 'a"b'})
        assert 'instance_id="a\\"b"' in query


def _cluster_tree():
    cluster = MonitorObject.objects.create(
        name="K3SCluster",
        level="base",
        default_metric='count(kube_node_info{instance_type="k3s"}) by (instance_id)',
        instance_id_keys=["instance_id"],
    )
    node = MonitorObject.objects.create(
        name="K3SNode",
        level="derivative",
        parent=cluster,
        default_metric='kube_node_info{instance_type="k3s"}',
        instance_id_keys=["instance_id", "node"],
    )
    return cluster, node


def _patch_enqueue(mocker):
    revoke = mocker.patch("apps.monitor.services.child_instance_discovery.current_app.control.revoke")
    apply_async = mocker.Mock()
    mocker.patch(
        "apps.monitor.services.child_instance_discovery._discovery_task",
        return_value=SimpleNamespace(apply_async=apply_async),
    )
    return revoke, apply_async


class TestEnqueueAndCancel:
    pytestmark = pytest.mark.django_db
    def test_skips_objects_without_children(self, mocker):
        obj = MonitorObject.objects.create(name="HostOnly", level="base")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        revoke, apply_async = _patch_enqueue(mocker)
        assert enqueue_child_instance_discovery(inst.id) is False
        apply_async.assert_not_called()
        revoke.assert_not_called()

    def test_fixed_task_id_and_immediate_first_run(self, mocker):
        cluster, _node = _cluster_tree()
        inst = MonitorInstance.objects.create(
            id="('c1',)", name="c1", monitor_object=cluster, interval=300
        )
        revoke, apply_async = _patch_enqueue(mocker)
        assert enqueue_child_instance_discovery(inst.id) is True
        revoke.assert_called_once_with(child_discovery_task_id(inst.id), terminate=False)
        kwargs = apply_async.call_args.kwargs
        assert kwargs["task_id"] == child_discovery_task_id(inst.id)
        assert kwargs["countdown"] == 0
        assert kwargs["kwargs"]["parent_instance_id"] == inst.id

    def test_skips_inactive_parent(self, mocker):
        cluster, _node = _cluster_tree()
        inst = MonitorInstance.objects.create(
            id="('c-off',)", name="c-off", monitor_object=cluster, is_active=False
        )
        _revoke, apply_async = _patch_enqueue(mocker)
        assert enqueue_child_instance_discovery(inst.id) is False
        apply_async.assert_not_called()

    def test_cancel_revokes_fixed_task_id(self, mocker):
        revoke, _apply_async = _patch_enqueue(mocker)
        assert cancel_child_instance_discovery("('c1',)") is True
        revoke.assert_called_once_with(child_discovery_task_id("('c1',)"), terminate=False)


class TestScopedSync:
    pytestmark = pytest.mark.django_db
    def test_discovers_only_this_parent_children_and_uses_collect_step(self, mocker):
        cluster, node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c1',)", name="c1", monitor_object=cluster, interval=300, auto=False
        )
        MonitorInstanceOrganization.objects.create(monitor_instance=parent, organization=7)
        query = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query")
        query.return_value = _vm_result(
            {"metric": {"instance_id": "c1", "node": "n1"}},
        )
        reconcile = mocker.patch(
            "apps.monitor.tasks.services.sync_instance.AutoDiscoveryLifecycleService.reconcile"
        )

        stats = SyncInstance(parent_instance_id=parent.id).run()

        assert stats == {"added": 1, "restored": 0}
        query.assert_called_once()
        assert query.call_args.kwargs["step"] == "300s"
        assert 'instance_id="c1"' in query.call_args.args[0]
        child = MonitorInstance.objects.get(id="('c1', 'n1')")
        assert child.monitor_object_id == node.id
        assert child.auto is True
        assert MonitorInstanceOrganization.objects.filter(
            monitor_instance_id=child.id, organization=7
        ).exists()
        reconcile.assert_not_called()

    def test_does_not_create_children_without_active_parent(self, mocker):
        cluster, node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c1',)",
            name="c1",
            monitor_object=cluster,
            is_active=False,
        )
        query = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query")
        query.return_value = _vm_result({"metric": {"instance_id": "c1", "node": "n1"}})

        SyncInstance(parent_instance_id=parent.id).run()

        query.assert_not_called()
        assert not MonitorInstance.objects.filter(monitor_object=node).exists()

    def test_warmup_path_does_not_inflate_missing_duration(self, mocker):
        cluster, node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c1',)", name="c1", monitor_object=cluster, interval=300
        )
        missing = MonitorInstance.objects.create(
            id="('c1', 'gone')",
            name="c1__gone",
            monitor_object=node,
            auto=True,
            is_active=False,
            missing_duration_seconds=120,
        )
        node.last_discovery_success_at = timezone.now() - timedelta(minutes=10)
        node.save(update_fields=["last_discovery_success_at", "updated_at"])
        query = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query")
        query.return_value = _vm_result()

        SyncInstance(parent_instance_id=parent.id).run()

        missing.refresh_from_db()
        node.refresh_from_db()
        assert missing.missing_duration_seconds == 120
        assert missing.is_active is False
        assert node.last_discovery_success_at < timezone.now() - timedelta(minutes=9)


class TestRunChildDiscoverySchedule:
    pytestmark = pytest.mark.django_db
    def test_interval_300_reschedules_warmup_countdown(self, mocker):
        cluster, _node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c1',)", name="c1", monitor_object=cluster, interval=300
        )
        mocker.patch(
            "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query",
            return_value=_vm_result(),
        )
        _revoke, apply_async = _patch_enqueue(mocker)
        started_at = int(timezone.now().timestamp())

        result = run_child_instance_discovery(parent.id, started_at=started_at)

        assert result["rescheduled"] is True
        assert result["countdown"] == 60
        assert apply_async.call_args.kwargs["countdown"] == 60

    def test_interval_600_stops_after_warmup(self, mocker):
        cluster, _node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c1',)", name="c1", monitor_object=cluster, interval=600
        )
        mocker.patch(
            "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query",
            return_value=_vm_result(),
        )
        _revoke, apply_async = _patch_enqueue(mocker)
        started_at = int(timezone.now().timestamp()) - CHILD_DISCOVERY_WARMUP_SECONDS

        result = run_child_instance_discovery(parent.id, started_at=started_at)

        assert result["rescheduled"] is False
        apply_async.assert_not_called()


class TestCreateHooksPersistIntervalAndEnqueue:
    pytestmark = pytest.mark.django_db
    def test_manual_collect_writes_interval_and_enqueues(self, mocker):
        from apps.monitor.services.manual_collect import ManualCollectService

        cluster, _node = _cluster_tree()
        enqueue = mocker.patch(
            "apps.monitor.services.manual_collect.enqueue_child_instance_discovery"
        )
        result = ManualCollectService.create_manual_collect_instance(
            {
                "id": "c-manual",
                "name": "c-manual",
                "monitor_object_id": cluster.id,
                "organizations": [1],
                "interval": 300,
            }
        )
        inst = MonitorInstance.objects.get(id=result["instance_id"])
        assert inst.interval == 300
        enqueue.assert_called_once_with(inst.id)

    def test_manual_collect_skips_enqueue_without_children(self, mocker):
        from apps.monitor.services.manual_collect import ManualCollectService

        obj = MonitorObject.objects.create(name="HostNoChild", level="base")
        enqueue = mocker.patch(
            "apps.monitor.services.manual_collect.enqueue_child_instance_discovery"
        )
        ManualCollectService.create_manual_collect_instance(
            {
                "id": "h1",
                "name": "h1",
                "monitor_object_id": obj.id,
                "organizations": [1],
            }
        )
        enqueue.assert_not_called()

    def test_k3s_create_writes_interval_and_enqueues(self, mocker, django_capture_on_commit_callbacks):
        from apps.monitor.services.k3s_onboarding import K3SOnboardingService

        cluster, _node = _cluster_tree()
        enqueue = mocker.patch(
            "apps.monitor.services.child_instance_discovery.enqueue_child_instance_discovery"
        )
        with django_capture_on_commit_callbacks(execute=True):
            created = K3SOnboardingService.create_instance(
                monitor_object_id=cluster.id,
                instance_id="edge-1",
                name="边缘 K3S",
                organizations=[10],
                interval=300,
            )
        inst = MonitorInstance.objects.get(id=created["instance_id"])
        assert inst.interval == 300
        enqueue.assert_called_once_with(inst.id)

    def test_node_mgmt_create_writes_config_interval_and_enqueues(self, mocker):
        from apps.monitor.services.node_mgmt import InstanceConfigService

        cluster, _node = _cluster_tree()
        mocker.patch(
            "apps.monitor.services.node_mgmt.Controller",
            return_value=SimpleNamespace(controller=lambda: None),
        )
        mocker.patch(
            "apps.monitor.services.node_mgmt.InstanceConfigService._validate_expected_collect_configs"
        )
        enqueue = mocker.patch(
            "apps.monitor.services.node_mgmt.enqueue_child_instance_discovery"
        )
        ids = InstanceConfigService.create_monitor_instance_by_node_mgmt(
            {
                "monitor_object_id": cluster.id,
                "collector": "Telegraf",
                "collect_type": "docker",
                "configs": [{"type": "docker", "interval": 300}],
                "instances": [
                    {
                        "instance_id": "docker-1",
                        "instance_name": "docker-1",
                        "group_ids": [1],
                    }
                ],
            }
        )
        inst = MonitorInstance.objects.get(id=ids[0])
        assert inst.interval == 300
        enqueue.assert_called_once_with(inst.id)


class TestRemovalCancelsDiscovery:
    pytestmark = pytest.mark.django_db
    def test_remove_parent_revokes_child_discovery(self, mocker):
        from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService

        cluster, _node = _cluster_tree()
        parent = MonitorInstance.objects.create(id="('c-del',)", name="c-del", monitor_object=cluster)
        mocker.patch(
            "apps.monitor.services.monitor_instance_removal.NodeMgmt",
            return_value=SimpleNamespace(delete_child_configs=lambda ids: None, delete_configs=lambda ids: None),
        )
        cancel = mocker.patch(
            "apps.monitor.services.monitor_instance_removal.cancel_child_instance_discovery"
        )
        MonitorInstanceRemovalService.remove([parent.id])
        cancel.assert_called_once_with(parent.id)


class TestChildDiscoveryLogs:
    pytestmark = pytest.mark.django_db
    def test_lifecycle_logs_use_stable_template_without_payload(self, mocker, caplog):
        cluster, _node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c-log',)", name="c-log", monitor_object=cluster, interval=300
        )
        mocker.patch(
            "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query",
            return_value=_vm_result(),
        )
        _patch_enqueue(mocker)
        sentinel = "super-secret-token-should-not-leak"
        caplog.set_level(logging.INFO, logger="monitor")

        result = run_child_instance_discovery(parent.id, started_at=int(timezone.now().timestamp()))

        started = [record for record in caplog.records if record.msg == LOG_STARTED]
        completed = [record for record in caplog.records if record.msg == LOG_COMPLETED]
        scheduled = [record for record in caplog.records if record.msg == LOG_SCHEDULED]
        assert len(started) == 1
        assert started[0].args == (parent.id,)
        assert parent.id in started[0].getMessage()
        assert len(completed) == 1
        assert completed[0].args == (parent.id, 0, 0)
        assert "added=0" in completed[0].getMessage()
        assert scheduled
        assert scheduled[0].args[0] == parent.id
        rendered = "\n".join(record.getMessage() for record in caplog.records)
        assert sentinel not in rendered
        assert result["rescheduled"] is True

    def test_skip_and_stop_log_reasons(self, mocker, caplog):
        cluster, _node = _cluster_tree()
        inactive = MonitorInstance.objects.create(
            id="('c-skip',)", name="c-skip", monitor_object=cluster, is_active=False
        )
        caplog.set_level(logging.INFO, logger="monitor")
        skipped = run_child_instance_discovery(inactive.id)
        skip_records = [record for record in caplog.records if record.msg == LOG_SKIPPED]
        assert skipped["rescheduled"] is False
        assert skip_records
        assert skip_records[0].args == (inactive.id, "parent_inactive")
        assert "reason=parent_inactive" in skip_records[0].getMessage()

        parent = MonitorInstance.objects.create(
            id="('c-stop',)", name="c-stop", monitor_object=cluster, interval=600
        )
        mocker.patch(
            "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query",
            return_value=_vm_result(),
        )
        _patch_enqueue(mocker)
        stopped = run_child_instance_discovery(
            parent.id,
            started_at=int(timezone.now().timestamp()) - CHILD_DISCOVERY_WARMUP_SECONDS,
        )
        stop_records = [record for record in caplog.records if record.msg == LOG_STOPPED]
        assert stopped["rescheduled"] is False
        assert stop_records
        assert stop_records[0].args == (parent.id, "warmup_complete")

    def test_failure_logs_single_traceback_owner_without_query(self, mocker, caplog):
        from apps.core.logger import SafeLogException

        cluster, _node = _cluster_tree()
        parent = MonitorInstance.objects.create(
            id="('c-fail',)", name="c-fail", monitor_object=cluster, interval=300
        )
        sentinel = "vm-query-secret-payload"
        original_error = RuntimeError(sentinel)
        mocker.patch(
            "apps.monitor.tasks.services.sync_instance.SyncInstance.run",
            side_effect=original_error,
        )
        caplog.set_level(logging.ERROR, logger="monitor")

        with pytest.raises(RuntimeError) as exc_info:
            run_child_instance_discovery(parent.id)

        assert exc_info.value is original_error
        errors = [record for record in caplog.records if record.msg == LOG_FAILED]
        assert len(errors) == 1
        record = errors[0]
        assert record.args == (parent.id, "sync", "RuntimeError")
        assert record.exc_info is not None
        assert record.exc_info[0] is SafeLogException
        assert record.exc_info[2] is not None
        assert record.exc_info[1] is not original_error
        assert original_error.args == (sentinel,)
        frames = traceback.extract_tb(record.exc_info[2])
        assert any(frame.name == "run_child_instance_discovery" for frame in frames)
        formatted = record.getMessage()
        assert "failed_stage=sync" in formatted
        assert "error_type=RuntimeError" in formatted
        assert sentinel not in record.msg
        assert sentinel not in str(record.args)
        assert sentinel not in formatted
        assert sentinel not in caplog.text
