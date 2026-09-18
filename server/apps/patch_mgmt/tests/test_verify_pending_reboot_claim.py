"""verify_pending_reboot_hosts 探测前认领：重叠巡检不得重复创建 VERIFY。"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.node_mgmt.models import CloudRegion  # noqa: F401  # INSTALL_APPS 需含 node_mgmt
from apps.patch_mgmt import config as patch_config
from apps.patch_mgmt import tasks as patch_tasks
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, PatchTarget
from apps.patch_mgmt.services import patch_execution_service as pes


def _make_reboot_host(*, stage="pending_reboot", wait=timedelta(minutes=2), **extra):
    target = PatchTarget.objects.create(
        name="reboot-claim-host",
        ip="10.0.54.45",
        os_type=OSType.LINUX,
    )
    task = GovernanceTask.objects.create(
        name="reboot-claim",
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        risk_snapshot=[{"host_id": target.id, "patch_id": 7}],
        team=[1],
        created_by="tester",
        timeout=3600,
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage=stage,
        stage_color="warning",
        boot_marker_before="boot-before",
        **extra,
    )
    GovernanceTaskHost.objects.filter(pk=host.pk).update(updated_at=timezone.now() - wait)
    host.refresh_from_db()
    return target, task, host


def _patch_recovery(monkeypatch, *, reachable=True, marker="boot-after", on_reachable=None):
    def _reachable(target):
        if on_reachable is not None:
            on_reachable(target)
        return reachable

    monkeypatch.setattr(pes, "_check_host_reachable", _reachable)
    monkeypatch.setattr(pes, "_read_boot_marker", lambda *args, **kwargs: marker)
    monkeypatch.setattr(patch_tasks.execute_governance_task, "delay", lambda task_id: None)


def _verify_qs(task, target):
    return GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.VERIFY,
        parent_task=task,
        host_results__target_id=target.id,
    )


@pytest.mark.django_db
def test_overlapping_scan_creates_single_verify_and_completes_host(monkeypatch):
    target, task, host = _make_reboot_host()
    reentered = {"done": False}

    def on_reachable(_target):
        if not reentered["done"]:
            reentered["done"] = True
            patch_tasks.verify_pending_reboot_hosts()

    _patch_recovery(monkeypatch, on_reachable=on_reachable)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    task.refresh_from_db()
    assert reentered["done"] is True
    assert _verify_qs(task, target).count() == 1
    assert host.stage == "completed"
    assert host.stage_color == "success"
    assert task.status == GovernanceTaskStatus.COMPLETED


@pytest.mark.django_db
def test_probe_failure_releases_claim_without_verify_or_updated_at_refresh(monkeypatch):
    _target, _task, host = _make_reboot_host()
    clock = host.updated_at
    _patch_recovery(monkeypatch, reachable=False)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    assert host.stage == "pending_reboot"
    assert host.updated_at == clock
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.VERIFY).exists()


@pytest.mark.django_db
def test_timeout_still_marks_reboot_failed(monkeypatch):
    target, task, host = _make_reboot_host(
        wait=timedelta(seconds=patch_config.REBOOT_VERIFY_MAX_WAIT + 1),
    )
    _patch_recovery(monkeypatch)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    task.refresh_from_db()
    assert host.stage == "reboot_failed"
    assert host.can_retry is True
    assert task.status == GovernanceTaskStatus.FAILED
    assert not _verify_qs(task, target).exists()


@pytest.mark.django_db
def test_expired_recovering_lease_is_released_back_to_pending_reboot(monkeypatch):
    _target, _task, host = _make_reboot_host(
        stage="reboot_recovering",
        last_heartbeat_at=timezone.now() - timedelta(hours=1),
    )
    clock = host.updated_at
    _patch_recovery(monkeypatch, reachable=False)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    assert host.stage == "pending_reboot"
    assert host.updated_at == clock
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.VERIFY).exists()


@pytest.mark.django_db
def test_existing_verify_for_parent_and_target_is_not_duplicated(monkeypatch):
    target, task, host = _make_reboot_host()
    existing = GovernanceTask.objects.create(
        name="existing-verify",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.PENDING,
        target_list=[target.id],
        parent_task=task,
    )
    GovernanceTaskHost.objects.create(
        task=existing,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage="waiting",
    )
    _patch_recovery(monkeypatch)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    assert _verify_qs(task, target).count() == 1
    assert host.stage == "completed"
