from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.patch_mgmt import config as patch_config
from apps.patch_mgmt import tasks as patch_tasks
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.serializers.governance import GovernanceTaskDetailSerializer
from apps.patch_mgmt.services import patch_execution_service as execution_service


def test_stage_timeout_defaults():
    assert patch_config.DISPATCH_TIMEOUT == 300
    assert patch_config.get_stage_timeout(GovernanceTaskType.ASSESS) == 1800
    assert patch_config.get_stage_timeout(GovernanceTaskType.INSTALL) == 7200
    assert patch_config.get_stage_timeout(GovernanceTaskType.REBOOT) == 300
    assert patch_config.get_stage_timeout(GovernanceTaskType.VERIFY) == 1800
    assert patch_config.RECONCILE_TIMEOUT == 1800
    assert patch_config.CHAIN_TIMEOUT == 14400
    assert patch_config.get_host_task_limits(GovernanceTaskType.INSTALL) == (7320, 7500)


@pytest.mark.django_db
def test_governance_timeout_fields_are_serialized():
    now = timezone.now()
    task = GovernanceTask.objects.create(
        name='timeout-fields',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[1],
        chain_started_at=now,
        chain_deadline_at=now + timedelta(hours=4),
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=1,
        stage='installing',
        stage_started_at=now,
        stage_deadline_at=now + timedelta(hours=2),
        last_heartbeat_at=now,
        timeout_reason='安装超时测试',
        boot_marker_before='boot-a',
    )

    request = SimpleNamespace(user=SimpleNamespace(group_list=[]))
    data = GovernanceTaskDetailSerializer(task, context={"request": request}).data

    assert data['chain_started_at'] is not None
    assert data['chain_deadline_at'] is not None
    host = data['host_results'][0]
    assert host['stage_started_at'] is not None
    assert host['stage_deadline_at'] is not None
    assert host['last_heartbeat_at'] is not None
    assert host['timeout_reason'] == '安装超时测试'
    assert host['boot_marker_before'] == 'boot-a'


@pytest.mark.django_db
def test_parent_task_dispatches_each_host_independently(monkeypatch):
    targets = [
        PatchTarget.objects.create(name=f'host-{index}', ip=f'10.0.1.{index}', os_type=OSType.LINUX)
        for index in range(1, 4)
    ]
    task = GovernanceTask.objects.create(
        name='fan-out',
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.PENDING,
        target_list=[target.id for target in targets],
    )
    dispatched = []

    monkeypatch.setattr(
        patch_tasks.execute_governance_host,
        'apply_async',
        lambda **kwargs: dispatched.append(kwargs),
    )

    patch_tasks.execute_governance_task(task.id)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING
    assert task.host_results.count() == 3
    assert [call['args'] for call in dispatched] == [
        [task.id, target.id] for target in targets
    ]
    assert all(call['soft_time_limit'] == 1920 for call in dispatched)
    assert all(call['time_limit'] == 2100 for call in dispatched)


@pytest.mark.django_db
def test_run_governance_host_only_executes_requested_target(monkeypatch):
    targets = [
        PatchTarget.objects.create(name=f'host-{index}', ip=f'10.0.2.{index}', os_type=OSType.LINUX)
        for index in range(1, 3)
    ]
    task = GovernanceTask.objects.create(
        name='single-host',
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id for target in targets],
    )
    for target in targets:
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
        )
    executed = []

    def fake_assess(target, host, execution_id, timeout):  # noqa: ARG001
        executed.append(target.id)
        execution_service._record_host_result(
            host,
            stage='completed',
            stage_color='success',
        )

    monkeypatch.setattr(execution_service, '_execute_assess', fake_assess)

    execution_service.run_governance_host(task, targets[0].id)

    assert executed == [targets[0].id]
    assert task.host_results.get(target_id=targets[0].id).stage == 'completed'
    assert task.host_results.get(target_id=targets[1].id).stage == 'waiting'
    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING
    assert task.finished_at is None


@pytest.mark.django_db
def test_watchdog_closes_dispatch_and_scan_timeouts_but_reconciles_install(monkeypatch):
    now = timezone.now()
    dispatch_task = GovernanceTask.objects.create(
        name='dispatch-timeout',
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[101],
    )
    dispatch_host = GovernanceTaskHost.objects.create(
        task=dispatch_task,
        target_id=101,
        stage='waiting',
    )
    GovernanceTaskHost.objects.filter(pk=dispatch_host.pk).update(
        created_at=now - timedelta(seconds=patch_config.DISPATCH_TIMEOUT + 1),
    )

    assess_task = GovernanceTask.objects.create(
        name='assess-timeout',
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[102],
    )
    assess_host = GovernanceTaskHost.objects.create(
        task=assess_task,
        target_id=102,
        stage='scanning',
        stage_deadline_at=now - timedelta(seconds=1),
    )

    install_task = GovernanceTask.objects.create(
        name='install-timeout',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[103],
    )
    install_host = GovernanceTaskHost.objects.create(
        task=install_task,
        target_id=103,
        stage='installing',
        stage_deadline_at=now - timedelta(seconds=1),
    )
    reconciled = []
    monkeypatch.setattr(
        patch_tasks.reconcile_governance_host,
        'apply_async',
        lambda **kwargs: reconciled.append(kwargs),
    )

    patch_tasks.watch_governance_timeouts()

    dispatch_host.refresh_from_db()
    assert dispatch_host.stage == 'failed'
    assert dispatch_host.error_code == 'dispatch_timeout'
    assert dispatch_host.can_retry is True

    assess_host.refresh_from_db()
    assert assess_host.stage == 'failed'
    assert assess_host.error_code == 'assess_timeout'
    assert assess_host.can_retry is True

    install_host.refresh_from_db()
    assert install_host.stage == 'reconciling'
    assert install_host.error_code == 'install_timeout_unknown'
    assert install_host.can_retry is False
    assert install_host.reconcile_deadline_at is not None
    assert reconciled == [{'args': [install_task.id, install_host.target_id]}]


@pytest.mark.django_db
def test_watchdog_keeps_window_task_waiting_before_window_ends():
    """执行窗口任务可因主机互斥等待，窗口结束前不应被常规投递超时误杀。"""
    now = timezone.now()
    task = GovernanceTask.objects.create(
        name='window-waiting',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        execution_mode='window',
        execution_window_start=now - timedelta(minutes=10),
        execution_window_end=now + timedelta(minutes=10),
        target_list=[104],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=104,
        stage='waiting',
    )
    GovernanceTaskHost.objects.filter(pk=host.pk).update(
        created_at=now - timedelta(seconds=patch_config.DISPATCH_TIMEOUT + 1),
    )

    patch_tasks.watch_governance_timeouts()

    host.refresh_from_db()
    assert host.stage == 'waiting'
    assert host.error_code == ''


@pytest.mark.django_db
def test_window_task_does_not_start_after_window_ends(monkeypatch):
    now = timezone.now()
    task = GovernanceTask.objects.create(
        name='expired-window',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        execution_mode='window',
        execution_window_start=now - timedelta(minutes=20),
        execution_window_end=now - timedelta(minutes=10),
        target_list=[105],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=105,
        stage='waiting',
    )
    executed = []
    monkeypatch.setattr(
        execution_service,
        'run_governance_host',
        lambda *_args: executed.append(True),
    )

    patch_tasks.execute_governance_host(task.id, host.target_id)

    host.refresh_from_db()
    assert executed == []
    assert host.stage == 'failed'
    assert host.error_code == 'execution_window_expired'
    assert not GovernanceTask.objects.filter(parent_task=task).exists()


@pytest.mark.django_db
def test_install_reconciliation_detects_installed_without_reinstall(monkeypatch):
    target = PatchTarget.objects.create(name='apt-host', ip='10.0.3.1', os_type=OSType.LINUX)
    patch = Patch.objects.create(title='openssl update', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='openssl')
    baseline = PatchBaseline.objects.create(name='apt-baseline')
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = GovernanceTask.objects.create(
        name='reconcile-installed',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        patch_list=[patch.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        stage='reconciling',
        reconcile_deadline_at=timezone.now() + timedelta(minutes=30),
    )
    commands = []

    def fake_execute(target, command, timeout, execution_id):  # noqa: ARG001
        commands.append(command)
        if 'RebootRequired=' in command:
            return {'exit_code': 0, 'stdout': 'RebootRequired=False\nRebootMethod=apt'}
        return {'exit_code': 0, 'stdout': '0 upgraded, 0 newly installed, 0 to remove'}

    monkeypatch.setattr(execution_service, '_execute_command', fake_execute)

    result = execution_service.reconcile_install_host(task, host, target)

    host.refresh_from_db()
    assert result == 'installed'
    assert host.stage == 'completed'
    assert all('apt-get install -y' not in command for command in commands)


@pytest.mark.django_db
def test_reconciliation_reschedules_running_and_expires_unknown(monkeypatch):
    target = PatchTarget.objects.create(name='reconcile-host', ip='10.0.3.2', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='reconcile-running',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        stage='reconciling',
        reconcile_deadline_at=timezone.now() + timedelta(minutes=5),
    )
    scheduled = []
    monkeypatch.setattr(execution_service, 'reconcile_install_host', lambda *args: 'running')
    monkeypatch.setattr(
        patch_tasks.reconcile_governance_host,
        'apply_async',
        lambda **kwargs: scheduled.append(kwargs),
    )

    execution_service.reconcile_host_result(task.id, target.id)

    assert scheduled == [{
        'args': [task.id, target.id],
        'countdown': patch_config.RECONCILE_INTERVAL,
    }]
    host.refresh_from_db()
    assert host.stage == 'reconciling'
    assert host.reconcile_attempts == 1

    host.reconcile_deadline_at = timezone.now() - timedelta(seconds=1)
    host.save(update_fields=['reconcile_deadline_at'])
    monkeypatch.setattr(execution_service, 'reconcile_install_host', lambda *args: 'unknown')

    execution_service.reconcile_host_result(task.id, target.id)

    host.refresh_from_db()
    assert host.stage == 'pending_confirmation'
    assert host.can_retry is False
    assert scheduled == [{
        'args': [task.id, target.id],
        'countdown': patch_config.RECONCILE_INTERVAL,
    }]


@pytest.mark.django_db
def test_reboot_records_boot_marker_before_command(monkeypatch):
    target = PatchTarget.objects.create(name='reboot-host', ip='10.0.4.1', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='reboot-marker',
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(task=task, target_id=target.id)
    monkeypatch.setattr(execution_service, '_read_boot_marker', lambda *args, **kwargs: 'boot-a')
    monkeypatch.setattr(
        execution_service,
        '_execute_command',
        lambda *args, **kwargs: {'exit_code': 0},
    )

    execution_service._execute_reboot(target, host, 'exec-1', 300)

    host.refresh_from_db()
    assert host.boot_marker_before == 'boot-a'
    assert host.stage == 'pending_reboot'


@pytest.mark.django_db
def test_reboot_recovery_requires_boot_marker_change(monkeypatch):
    target = PatchTarget.objects.create(name='recover-host', ip='10.0.4.2', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='recover-marker',
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='pending_reboot',
        boot_marker_before='boot-a',
    )
    GovernanceTaskHost.objects.filter(pk=host.pk).update(
        updated_at=timezone.now() - timedelta(minutes=2),
    )
    monkeypatch.setattr(execution_service, '_check_host_reachable', lambda target: True)
    monkeypatch.setattr(execution_service, '_read_boot_marker', lambda *args, **kwargs: 'boot-a')
    monkeypatch.setattr(patch_tasks.execute_governance_task, 'delay', lambda task_id: None)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    assert host.stage == 'pending_reboot'
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.VERIFY).exists()

    monkeypatch.setattr(execution_service, '_read_boot_marker', lambda *args, **kwargs: 'boot-b')
    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    assert host.stage == 'completed'
    assert GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.VERIFY,
        target_list=[target.id],
    ).count() == 1


@pytest.mark.django_db
def test_reboot_recovery_timeout_finalizes_parent_task(monkeypatch):
    target = PatchTarget.objects.create(name='timeout-host', ip='10.0.4.3', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='reboot-timeout',
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='pending_reboot',
        boot_marker_before='boot-a',
    )
    GovernanceTaskHost.objects.filter(pk=host.pk).update(
        updated_at=timezone.now() - timedelta(seconds=patch_config.REBOOT_VERIFY_MAX_WAIT + 1),
    )

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    task.refresh_from_db()
    assert host.stage == 'reboot_failed'
    assert task.status == GovernanceTaskStatus.FAILED
    assert task.finished_at is not None


@pytest.mark.django_db
def test_install_chain_is_propagated_and_overdue_blocks_auto_reboot(monkeypatch):
    target = PatchTarget.objects.create(name='chain-host', ip='10.0.5.1', os_type=OSType.LINUX)
    install_task = GovernanceTask.objects.create(
        name='chain-install',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.PENDING,
        target_list=[target.id],
        auto_reboot=True,
    )
    GovernanceTaskHost.objects.create(
        task=install_task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='waiting',
    )
    monkeypatch.setattr(patch_tasks.execute_governance_host, 'apply_async', lambda **kwargs: None)

    patch_tasks.execute_governance_task(install_task.id)

    install_task.refresh_from_db()
    assert install_task.chain_started_at is not None
    assert install_task.chain_deadline_at is not None

    install_task.host_results.update(stage='pending_reboot')
    monkeypatch.setattr(patch_tasks.execute_governance_task, 'delay', lambda task_id: None)
    execution_service._schedule_auto_reboot(install_task)
    reboot_task = GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.REBOOT,
        parent_task=install_task,
    ).get()
    assert reboot_task.chain_started_at == install_task.chain_started_at
    assert reboot_task.chain_deadline_at == install_task.chain_deadline_at

    overdue_task = GovernanceTask.objects.create(
        name='overdue-install',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        auto_reboot=True,
        chain_started_at=timezone.now() - timedelta(hours=5),
        chain_deadline_at=timezone.now() - timedelta(hours=1),
    )
    GovernanceTaskHost.objects.create(
        task=overdue_task,
        target_id=target.id,
        stage='pending_reboot',
    )

    execution_service._schedule_auto_reboot(overdue_task)

    overdue_task.refresh_from_db()
    assert overdue_task.overdue_at is not None
    assert not GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.REBOOT,
        parent_task=overdue_task,
    ).exists()


@pytest.mark.django_db
def test_reboot_timeout_reconciliation_only_checks_boot_marker(monkeypatch):
    target = PatchTarget.objects.create(name='reboot-reconcile', ip='10.0.6.1', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='reboot-reconcile',
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        stage='reconciling',
        boot_marker_before='boot-before',
        reconcile_deadline_at=timezone.now() + timedelta(minutes=30),
    )
    monkeypatch.setattr(execution_service, '_check_host_reachable', lambda target: True)
    monkeypatch.setattr(execution_service, '_read_boot_marker', lambda *args, **kwargs: 'boot-after')
    monkeypatch.setattr(
        execution_service,
        '_execute_command',
        lambda *args, **kwargs: pytest.fail('重启核验不得再次执行重启命令'),
    )

    execution_service.reconcile_host_result(task.id, target.id)

    host.refresh_from_db()
    assert host.stage == 'pending_reboot'
    assert '启动标识已变化' in host.reason


@pytest.mark.django_db
def test_soft_timeout_fails_assess_but_reconciles_install(monkeypatch):
    assess_task = GovernanceTask.objects.create(
        name='soft-assess',
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[201],
    )
    assess_host = GovernanceTaskHost.objects.create(
        task=assess_task,
        target_id=201,
        stage='scanning',
    )
    install_task = GovernanceTask.objects.create(
        name='soft-install',
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[202],
    )
    install_host = GovernanceTaskHost.objects.create(
        task=install_task,
        target_id=202,
        stage='installing',
    )
    reconciled = []
    monkeypatch.setattr(
        patch_tasks.reconcile_governance_host,
        'apply_async',
        lambda **kwargs: reconciled.append(kwargs),
    )

    execution_service.handle_host_execution_timeout(assess_task.id, assess_host.target_id)
    execution_service.handle_host_execution_timeout(install_task.id, install_host.target_id)

    assess_host.refresh_from_db()
    assert assess_host.stage == 'failed'
    assert assess_host.error_code == 'assess_timeout'
    assert assess_host.can_retry is True
    install_host.refresh_from_db()
    assert install_host.stage == 'reconciling'
    assert install_host.can_retry is False
    assert reconciled == [{'args': [install_task.id, install_host.target_id]}]


@pytest.mark.django_db
def test_reboot_transport_timeout_enters_reconciliation(monkeypatch):
    target = PatchTarget.objects.create(name='timeout-reboot', ip='10.0.7.1', os_type=OSType.LINUX)
    task = GovernanceTask.objects.create(
        name='timeout-reboot',
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
    )
    host = GovernanceTaskHost.objects.create(task=task, target_id=target.id)
    reconciled = []
    monkeypatch.setattr(execution_service, '_read_boot_marker', lambda *args, **kwargs: 'boot-before')
    monkeypatch.setattr(
        execution_service,
        '_execute_command',
        lambda *args, **kwargs: {'exit_code': None, 'error': 'Read timed out'},
    )
    monkeypatch.setattr(
        patch_tasks.reconcile_governance_host,
        'apply_async',
        lambda **kwargs: reconciled.append(kwargs),
    )

    execution_service._execute_reboot(target, host, 'timeout-exec', 300)

    host.refresh_from_db()
    assert host.stage == 'reconciling'
    assert host.error_code == 'reboot_timeout_unknown'
    assert host.can_retry is False
    assert reconciled == [{'args': [task.id, target.id]}]
