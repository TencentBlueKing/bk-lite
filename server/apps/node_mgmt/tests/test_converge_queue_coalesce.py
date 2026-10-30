"""心跳收敛入队去重，以及采集器超时仍由同一次收敛结案。"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import Collector, Node
from apps.node_mgmt.services.converge_slot import action_slot_key, release_converge_slot
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.tasks import action_task as at
from apps.node_mgmt.tasks.action_task import ACTION_TASK_TIMEOUT_SECONDS
from apps.node_mgmt.tasks.installer import _save_node_pending_connectivity


@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "converge-slot-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def region(db):
    return CloudRegion.objects.create(name=f"cr-coalesce-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def node(region):
    return Node.objects.create(
        id=f"node-{uuid.uuid4().hex[:8]}",
        name="coalesce-node",
        ip="10.8.0.8",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )


@pytest.fixture
def collector(db):
    return Collector.objects.create(
        id=f"col-{uuid.uuid4().hex[:8]}",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )


def _running_action(region, collector, node, action="start"):
    task = CollectorActionTask.objects.create(
        collector=collector,
        cloud_region=region,
        action=action,
        status="running",
        total_count=1,
    )
    task_node = CollectorActionTaskNode.objects.create(
        task=task,
        node=node,
        status="running",
        result={"steps": [{"action": "consume_ack", "status": "running", "message": "wait"}]},
    )
    return task, task_node


def _age_task(task, seconds):
    CollectorActionTask.objects.filter(id=task.id).update(created_at=timezone.now() - timedelta(seconds=seconds))


def _install_node(region, *, phase, ip="10.8.0.9", install_node_id="", observed_at=None, steps=None, observed=None):
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="running",
        work_node="worker-1",
        package_version_id=1,
    )
    result = {InstallerConstants.EXECUTION_PHASE_KEY: phase}
    if install_node_id:
        result[InstallerConstants.INSTALL_NODE_ID_KEY] = install_node_id
    if steps is not None:
        result["steps"] = steps
    if observed is not None:
        result[InstallerConstants.CONNECTIVITY_OBSERVED_KEY] = observed
    return ControllerTaskNode.objects.create(
        task=task,
        ip=ip,
        node_name="install-node",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password="",
        status=InstallerConstants.STEP_STATUS_RUNNING,
        connectivity_observed_at=observed_at,
        result=result,
    )


def test_release_keeps_a_newer_converge_slot():
    key = f"node_converge_action_pending_{uuid.uuid4().hex}"
    cache.set(key, "newer", timeout=60)
    release_converge_slot(key, "older")
    assert cache.get(key) == "newer"
    cache.delete(key)


@pytest.mark.django_db
def test_running_collector_action_stays_one_queued_task_across_status_changes(region, collector, node):
    _running_action(region, collector, node)
    with patch("apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": [{"collector_id": collector.id, "status": 1}]})
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": [{"collector_id": collector.id, "status": 0}]})
    assert conv.delay.call_count == 1
    assert conv.delay.call_args.args[0] == node.id
    token = conv.delay.call_args.args[1]

    release_converge_slot(action_slot_key(node.id), token)
    with patch("apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": [{"collector_id": collector.id, "status": 2}]})
    conv.delay.assert_called_once()
    assert conv.delay.call_args.args[0] == node.id


@pytest.mark.django_db
def test_failed_action_enqueue_releases_slot(region, collector, node):
    _running_action(region, collector, node)
    with (
        patch(
            "apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node.delay",
            side_effect=RuntimeError("broker down"),
        ),
        pytest.raises(RuntimeError, match="broker down"),
    ):
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": [{"collector_id": collector.id, "status": 1}]})

    with patch("apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": [{"collector_id": collector.id, "status": 0}]})
    conv.delay.assert_called_once()


@pytest.mark.django_db
def test_direct_collector_converge_does_not_drop_heartbeat_slot(region, collector, node):
    _running_action(region, collector, node)
    token = "heartbeat-token"
    cache.set(action_slot_key(node.id), token, timeout=60)
    at.converge_collector_action_task_for_node(node.id)
    assert cache.get(action_slot_key(node.id)) == token
    at.converge_collector_action_task_for_node(node.id, token)
    assert cache.get(action_slot_key(node.id)) is None


@pytest.mark.django_db
def test_observed_bootstrap_install_does_not_enqueue(region, monkeypatch):
    _install_node(
        region,
        phase=InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING,
        ip="10.8.1.1",
        observed_at=timezone.now(),
        observed=True,
    )
    monkeypatch.setattr(Sidecar, "_is_debounce_elapsed", lambda *_args, **_kwargs: True)
    with patch("apps.node_mgmt.services.sidecar.converge_controller_install_connectivity_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed("some-node", "10.8.1.1", {})
        Sidecar.trigger_converge_tasks_if_needed("some-node", "10.8.1.1", {})
    conv.delay.assert_not_called()


@pytest.mark.django_db
def test_unobserved_bootstrap_install_enqueues_once_until_slot_releases(region, monkeypatch):
    _install_node(
        region,
        phase=InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING,
        ip="10.8.1.2",
    )
    monkeypatch.setattr(Sidecar, "_is_debounce_elapsed", lambda *_args, **_kwargs: True)
    with patch("apps.node_mgmt.services.sidecar.converge_controller_install_connectivity_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed("some-node", "10.8.1.2", {})
        Sidecar.trigger_converge_tasks_if_needed("some-node", "10.8.1.2", {})
    assert conv.delay.call_count == 1
    assert conv.delay.call_args.args[0] == "some-node"


@pytest.mark.django_db
def test_connectivity_waiting_install_still_enqueues(region, monkeypatch):
    _install_node(
        region,
        phase=InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING,
        install_node_id="waiting-node",
        ip="10.8.1.3",
        observed_at=timezone.now(),
        observed=True,
        steps=[{"action": "connectivity_check", "status": "running", "message": "wait"}],
    )
    monkeypatch.setattr(Sidecar, "_is_debounce_elapsed", lambda *_args, **_kwargs: True)
    with patch("apps.node_mgmt.services.sidecar.converge_controller_install_connectivity_for_node") as conv:
        Sidecar.trigger_converge_tasks_if_needed("waiting-node", "10.9.9.9", {})
    conv.delay.assert_called_once()
    assert conv.delay.call_args.args[0] == "waiting-node"


@pytest.mark.django_db
def test_pending_connectivity_save_converges_while_heartbeat_slot_is_held(region, node):
    task_node = _install_node(
        region,
        phase=InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING,
        install_node_id=node.id,
        ip=node.ip,
        observed_at=timezone.now(),
        observed=True,
        steps=[
            {"action": "run", "status": "running", "message": "bootstrap"},
            {"action": "connectivity_check", "status": "running", "message": "wait"},
        ],
    )
    from apps.node_mgmt.services.converge_slot import install_slot_key

    cache.set(install_slot_key(node.id), "heartbeat-token", timeout=60)
    with patch("apps.node_mgmt.tasks.installer.discover_node_versions.delay"):
        _save_node_pending_connectivity(task_node, "bootstrap finished")
    task_node.refresh_from_db()
    assert task_node.status == "success"
    assert cache.get(install_slot_key(node.id)) == "heartbeat-token"
    cache.delete(install_slot_key(node.id))


@pytest.mark.django_db
def test_converge_times_out_aged_collector_action_when_status_does_not_match(region, collector, node):
    node.status = {"collectors": [{"collector_id": collector.id, "status": 99}]}
    node.save(update_fields=["status"])
    task, task_node = _running_action(region, collector, node)
    _age_task(task, ACTION_TASK_TIMEOUT_SECONDS + 5)

    at.converge_collector_action_task_for_node(node.id)

    task_node.refresh_from_db()
    task.refresh_from_db()
    assert task_node.status == "error"
    assert task_node.result["overall_status"] == "timeout"
    assert "callback_or_timeout" in [step["action"] for step in task_node.result["steps"]]
    assert task.status == "finished"
    assert task.error_count == 1


@pytest.mark.django_db
def test_converge_keeps_young_collector_action_running_when_status_does_not_match(region, collector, node):
    node.status = {}
    node.save(update_fields=["status"])
    _task, task_node = _running_action(region, collector, node)

    at.converge_collector_action_task_for_node(node.id)

    task_node.refresh_from_db()
    assert task_node.status == "running"


@pytest.mark.django_db
def test_converge_prefers_reported_success_over_timeout(region, collector, node):
    node.status = {"collectors": [{"collector_id": collector.id, "status": 0, "message": "ok"}]}
    node.save(update_fields=["status"])
    task, task_node = _running_action(region, collector, node, action="start")
    _age_task(task, ACTION_TASK_TIMEOUT_SECONDS + 5)

    at.converge_collector_action_task_for_node(node.id)

    task_node.refresh_from_db()
    task.refresh_from_db()
    assert task_node.status == "success"
    assert task_node.result["overall_status"] == "success"
    assert "callback_or_timeout" not in [step["action"] for step in task_node.result["steps"]]
    assert task.success_count == 1


@pytest.mark.django_db
def test_converge_times_out_aged_action_when_heartbeat_has_no_collectors(region, collector, node):
    node.status = {}
    node.save(update_fields=["status"])
    task, task_node = _running_action(region, collector, node)
    _age_task(task, ACTION_TASK_TIMEOUT_SECONDS + 5)

    at.converge_collector_action_task_for_node(node.id)

    task_node.refresh_from_db()
    assert task_node.status == "error"
    assert task_node.result["overall_status"] == "timeout"
