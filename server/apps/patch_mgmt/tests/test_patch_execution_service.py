'''补丁治理任务真实执行服务单元测试

通过 mock Executor / AnsibleExecutor 验证：
- 命令生成
- 执行器路由
- GovernanceTaskHost / GovernanceTask 状态回写
'''

import base64
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.node_mgmt.models import CloudRegion
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
    PatchSourceType,
    PatchTargetSource,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchSource,
    PatchTarget,
    WindowsPatchDetail,
)
from apps.patch_mgmt.services import patch_execution_service as pes


APT_SAMPLE = """
The following packages will be upgraded:
  perl-base
1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""


def test_reboot_command():
    assert 'shutdown' in pes._reboot_command(OSType.WINDOWS)
    assert pes._reboot_command(OSType.LINUX).startswith('nohup')


@pytest.mark.django_db
def test_install_commands_linux():
    """Linux 安装命令根据目标主机包管理器自适应，不按补丁 source_type 分组。"""
    p_yum = Patch.objects.create(title='yum-patch', os_type=OSType.LINUX)
    p_dnf = Patch.objects.create(title='dnf-patch', os_type=OSType.LINUX)
    p_apt = Patch.objects.create(title='apt-patch', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p_yum, pkg_name='yum-pkg')
    LinuxPatchDetail.objects.create(patch=p_dnf, pkg_name='dnf-pkg')
    LinuxPatchDetail.objects.create(patch=p_apt, pkg_name='apt-pkg')
    cmds = pes._install_commands([p_yum, p_dnf, p_apt], OSType.LINUX)
    # 所有包名都在同一条自适应命令里，包含三种包管理器分支
    assert len(cmds) == 1
    cmd = cmds[0]
    assert 'command -v dnf' in cmd
    assert 'dnf install -y' in cmd and 'yum-pkg' in cmd
    assert 'yum install -y' in cmd and 'dnf-pkg' in cmd
    assert 'apt-get install -y' in cmd and 'apt-pkg' in cmd


@pytest.mark.django_db
def test_install_commands_multiple_pkgs_one_command():
    """多个补丁的包名合并到同一条安装命令。"""
    p1 = Patch.objects.create(title='apt-1', os_type=OSType.LINUX)
    p2 = Patch.objects.create(title='apt-2', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p1, pkg_name='pkg-a')
    LinuxPatchDetail.objects.create(patch=p2, pkg_name='pkg-b')
    cmds = pes._install_commands([p1, p2], OSType.LINUX)
    assert len(cmds) == 1
    assert 'pkg-a' in cmds[0]
    assert 'pkg-b' in cmds[0]


@pytest.mark.django_db
def test_install_commands_skips_invalid_pkg_name():
    p1 = Patch.objects.create(title='apt-1', os_type=OSType.LINUX)
    p2 = Patch.objects.create(title='apt-2', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p1, pkg_name='pkg-a')
    LinuxPatchDetail.objects.create(patch=p2, pkg_name='pkg with space')
    cmds = pes._install_commands([p1, p2], OSType.LINUX)
    assert len(cmds) == 1
    assert 'pkg-a' in cmds[0]
    assert 'pkg with space' not in cmds[0]


def test_install_commands_empty():
    cmds = pes._install_commands([], OSType.LINUX)
    assert cmds == ['echo no installable package mapped']


@pytest.mark.django_db
def test_install_commands_windows_uses_scheduled_task():
    """Windows 安装命令应通过 Task Scheduler 以 SYSTEM 身份执行 WUA 安装。"""
    patch = Patch.objects.create(title='KB5072653', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB5072653')
    cmds = pes._install_commands([patch], OSType.WINDOWS)
    assert len(cmds) == 1
    cmd = cmds[0]
    assert 'schtasks' in cmd
    assert 'SYSTEM' in cmd
    assert 'KB5072653' in cmd
    # 内层 WUA 脚本通过 here-string 写入文件
    assert 'Microsoft.Update.Session' in cmd
    assert 'InstallResult' in cmd
    # 不应使用 base64 编码（避免命令行过长）
    assert 'FromBase64String' not in cmd


@pytest.mark.django_db
def test_manual_windows_package_uses_staged_file_instead_of_wua():
    patch = Patch.objects.create(title='KB6000003', os_type=OSType.WINDOWS)
    detail = WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number='KB6000003',
        package_file='windows/1/hash/update.msu',
        package_original_name='update.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )

    commands = pes._install_commands(
        [patch],
        OSType.WINDOWS,
        manual_paths={detail.patch_id: 'C:/Windows/Temp/bk-lite-patches/update.msu'},
    )

    assert len(commands) == 1
    assert 'Microsoft.Update.Session' not in commands[0]
    assert 'Get-FileHash' in commands[0]
    assert 'wusa.exe' in commands[0]
    assert 'Remove-Item' in commands[0]


@pytest.mark.django_db
def test_manual_windows_package_treats_already_installed_as_idempotent_success():
    """WUSA 已安装成功码需要结合系统待重启标记收口，重试不能假失败。"""
    patch = Patch.objects.create(title='KB6000007', os_type=OSType.WINDOWS)
    detail = WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number='KB6000007',
        package_file='windows/1/hash/update.msu',
        package_original_name='update.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )

    command = pes._manual_windows_install_command(
        detail,
        'C:/Windows/Temp/bk-lite-patches/update.msu',
    )

    assert '2359302' in command
    assert 'RebootPending' in command


@pytest.mark.django_db
def test_manual_windows_package_does_not_create_task_with_expired_start_time():
    """SYSTEM 任务不能使用已过期的 00:00，否则 schtasks 警告会被 WinRM 判为失败。"""
    patch = Patch.objects.create(title='KB6000008', os_type=OSType.WINDOWS)
    detail = WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number='KB6000008',
        package_file='windows/1/hash/update.msu',
        package_original_name='update.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )

    command = pes._manual_windows_install_command(
        detail,
        'C:/Windows/Temp/bk-lite-patches/update.msu',
    )

    assert '/sc once /st 00:00' not in command.lower()


@pytest.mark.django_db
def test_run_install_executes_manual_windows_package_as_system(monkeypatch):
    """手工 MSU 必须通过 SYSTEM 任务安装，避免 WinRM 令牌令 WUSA 返回 5。"""
    cloud_region = CloudRegion.objects.create(name='region-win-manual-system')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB6000006', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number='KB6000006',
        package_file='windows/1/hash/update.msu',
        package_original_name='update.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )
    task = _make_task(
        GovernanceTaskType.INSTALL,
        [target.id],
        patch_ids=[patch.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='waiting',
    )

    monkeypatch.setattr(
        pes,
        '_stage_windows_package',
        lambda *_args, **_kwargs: 'C:/Windows/Temp/bk-lite-patches/update.msu',
    )

    def execute_command(_target, command, **_kwargs):
        assert 'Register-ScheduledTask' in command
        assert "New-ScheduledTaskPrincipal -UserId 'SYSTEM'" in command
        assert 'wusa.exe' in command
        return {'exit_code': 1, 'stdout': 'InstallResult=2 RebootRequired=True'}

    monkeypatch.setattr(pes, '_execute_command', execute_command)

    pes._execute_install(
        target,
        host,
        [patch.id],
        execution_id='manual-system',
        timeout=300,
    )

    host.refresh_from_db()
    assert host.stage == 'pending_reboot'


def test_parse_windows_install_result_success_with_reboot():
    """InstallResult=2 且需要重启 -> 成功。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=True'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is True
    assert reboot_required is True
    assert '成功' in reason


def test_parse_windows_install_result_success_without_reboot():
    """InstallResult=2 且不需要重启 -> 成功。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=False'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is True
    assert reboot_required is False


def test_parse_windows_install_result_success_without_reboot_field_is_unknown():
    """安装成功但 WUA 未返回 RebootRequired 时不能误判为无需重启。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult=2'}

    is_success, reason, reboot_required = pes._parse_windows_install_result(result)

    assert is_success is True
    assert reboot_required is None
    assert '成功' in reason


def test_parse_windows_install_result_success_with_errors():
    """InstallResult=3 表示成功但有错误 -> 仍算成功。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult=3 RebootRequired=True'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is True
    assert reboot_required is True


def test_parse_windows_install_result_failure_code_4():
    """InstallResult=4 表示安装失败。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult=4 RebootRequired=False'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert '失败' in reason


def test_parse_windows_install_result_empty_code():
    """InstallResult= 为空（COM 异常）-> 失败。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult= RebootRequired='}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert '输出异常' in reason


def test_parse_windows_install_result_access_denied():
    """stderr 含 Access is denied -> 权限不足失败。"""
    result = {'exit_code': 0, 'stdout': 'InstallResult= RebootRequired=', 'stderr': 'Access is denied. (Exception from HRESULT: 0x80070005)'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert '权限' in reason


def test_parse_windows_install_result_success_with_schtasks_warning():
    """stdout 有 InstallResult=2 时，即使 stderr 有 schtasks WARNING 也判成功。"""
    result = {
        'exit_code': 0,
        'stdout': 'InstallResult=2 RebootRequired=True',
        'stderr': 'schtasks : WARNING: Task may not run because /ST is earlier than current time.',
    }
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is True
    assert reboot_required is True
    assert '成功' in reason


def test_parse_windows_install_result_no_matching():
    """No matching updates found -> 失败且不可重试（KB 不存在）。"""
    result = {'exit_code': 0, 'stdout': 'No matching updates found'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert '未找到' in reason


def test_parse_windows_install_result_unknown_output():
    """无法识别的输出 -> 失败。"""
    result = {'exit_code': 0, 'stdout': 'some unexpected output'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert '输出异常' in reason


def test_parse_windows_install_result_install_error():
    """InstallError= 表示 SYSTEM 任务内部捕获到异常 -> 失败。"""
    result = {'exit_code': 0, 'stdout': 'InstallError=Exception from HRESULT: 0x80070005'}
    is_success, reason, reboot_required = pes._parse_windows_install_result(result)
    assert is_success is False
    assert 'WUA 安装异常' in reason
    assert '0x80070005' in reason


def test_linux_reboot_check_command_covers_apt_dnf_and_yum():
    command = pes._linux_reboot_check_command()

    assert '/run/reboot-required' in command
    assert 'update-notifier' in command
    assert 'dnf' in command and 'needs-restarting' in command
    assert 'yum' in command and 'needs-restarting' in command
    assert 'RebootRequired=True' in command
    assert 'RebootRequired=False' in command
    assert 'RebootRequired=Unknown' in command


@pytest.mark.parametrize(
    ('stdout', 'expected', 'reason_fragment'),
    [
        ('RebootRequired=True\nRebootMethod=apt', True, 'apt'),
        ('RebootRequired=False\nRebootMethod=dnf', False, 'dnf'),
        (
            'RebootRequired=Unknown\nRebootMethod=yum\nRebootDetail=needs-restarting unavailable',
            None,
            'needs-restarting unavailable',
        ),
    ],
)
def test_parse_linux_reboot_check_result(stdout, expected, reason_fragment):
    reboot_required, reason = pes._parse_linux_reboot_check_result(
        {'exit_code': 0, 'stdout': stdout},
    )

    assert reboot_required is expected
    assert reason_fragment in reason


def test_parse_linux_reboot_check_failure_is_unknown():
    reboot_required, reason = pes._parse_linux_reboot_check_result(
        {'exit_code': 2, 'stderr': 'probe failed'},
    )

    assert reboot_required is None
    assert 'probe failed' in reason


def test_is_success():
    assert pes._is_success({'exit_code': 0}) is True
    assert pes._is_success({'exit_code': '0'}) is True
    assert pes._is_success({'exit_code': 1}) is False
    assert pes._is_success({'error': 'boom'}) is False
    assert pes._is_success(None) is False


def _make_node_mgmt_target():
    return PatchTarget.objects.create(
        name='node-target',
        ip='10.0.0.1',
        os_type=OSType.LINUX,
        source_type=PatchTargetSource.NODE_MGMT,
        node_id='node-1',
        cloud_region_id=1,
        team=[1],
    )


def _make_manual_linux_target(cloud_region):
    return PatchTarget.objects.create(
        name='manual-linux',
        ip='10.0.0.2',
        os_type=OSType.LINUX,
        source_type=PatchTargetSource.MANUAL,
        cloud_region_id=cloud_region.id,
        ssh_user='root',
        ssh_password='plain-password',
        ssh_port=22,
        team=[1],
    )


def _make_manual_windows_target(cloud_region):
    return PatchTarget.objects.create(
        name='manual-win',
        ip='10.0.0.3',
        os_type=OSType.WINDOWS,
        source_type=PatchTargetSource.MANUAL,
        cloud_region_id=cloud_region.id,
        winrm_user='Administrator',
        winrm_password='plain-password',
        winrm_port=5986,
        winrm_scheme='https',
        winrm_transport='ntlm',
        team=[1],
    )


def _make_task(task_type, target_ids, patch_ids=None):
    return GovernanceTask.objects.create(
        name='test-task',
        task_type=task_type,
        target_list=list(target_ids),
        patch_list=list(patch_ids or []),
    )


def _make_task_hosts(task, targets, stages):
    return [
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage=stage,
        )
        for target, stage in zip(targets, stages)
    ]


@pytest.mark.django_db
def test_windows_direct_winrm_requires_explicit_local_mode(monkeypatch):
    monkeypatch.setattr(pes.settings, 'DEBUG', True)
    monkeypatch.setattr(pes.settings, 'PATCH_MGMT_WINDOWS_EXECUTION_MODE', 'direct_winrm')
    cloud_region = CloudRegion.objects.create(name='local-winrm-region')
    target = _make_manual_windows_target(cloud_region)
    monkeypatch.setattr(
        pes,
        '_execute_winrm_direct',
        lambda *_args, **_kwargs: {'exit_code': 0, 'stdout': 'local-real-winrm'},
    )

    result = pes._execute_windows_manual(target, 'Get-Date')

    assert result['stdout'] == 'local-real-winrm'


@pytest.mark.django_db
def test_windows_direct_winrm_is_rejected_outside_debug(monkeypatch):
    monkeypatch.setattr(pes.settings, 'DEBUG', False)
    monkeypatch.setattr(pes.settings, 'PATCH_MGMT_WINDOWS_EXECUTION_MODE', 'direct_winrm')
    cloud_region = CloudRegion.objects.create(name='production-region')
    target = _make_manual_windows_target(cloud_region)
    monkeypatch.setattr(
        pes,
        '_execute_winrm_direct',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('不应发起 WinRM')),
    )

    with pytest.raises(RuntimeError, match='仅允许在 DEBUG'):
        pes._execute_windows_manual(target, 'Get-Date')


@pytest.mark.django_db
def test_async_dispatch_failure_is_explicitly_persisted(monkeypatch):
    from apps.patch_mgmt.services import governance_service
    from apps.patch_mgmt import tasks as patch_tasks

    task = _make_task(GovernanceTaskType.ASSESS, [999])
    host = GovernanceTaskHost.objects.create(task=task, target_id=999, stage='waiting')
    monkeypatch.setattr(
        patch_tasks.execute_governance_task,
        'delay',
        lambda _task_id: (_ for _ in ()).throw(ConnectionError('broker unavailable')),
    )

    with pytest.raises(RuntimeError, match='异步任务投递失败'):
        governance_service._trigger_async(task.id)

    task.refresh_from_db()
    host.refresh_from_db()
    assert task.status == GovernanceTaskStatus.FAILED
    assert host.stage == 'failed'
    assert 'broker unavailable' in host.reason


@pytest.mark.django_db
def test_claim_waiting_host_rejects_cancelled_host():
    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])
    host = _make_task_hosts(task, [target], ["cancelled"])[0]

    assert pes._claim_waiting_host(host, "scanning") is False
    host.refresh_from_db()
    assert host.stage == "cancelled"


@pytest.mark.django_db
def test_run_governance_task_skips_cancelled_host(monkeypatch):
    targets = [_make_node_mgmt_target(), _make_node_mgmt_target()]
    task = _make_task(GovernanceTaskType.ASSESS, [target.id for target in targets])
    _make_task_hosts(task, targets, ["cancelled", "waiting"])
    executed_target_ids = []

    def fake_execute(target, host, execution_id, timeout):
        executed_target_ids.append(target.id)
        pes._record_host_result(host, stage="completed", stage_color="success")

    monkeypatch.setattr(pes, "_execute_assess", fake_execute)

    pes.run_governance_task(task)

    assert executed_target_ids == [targets[1].id]
    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.PARTIAL_CANCELLED


@pytest.mark.django_db
def test_finalize_all_cancelled_hosts_marks_task_cancelled():
    targets = [_make_node_mgmt_target(), _make_node_mgmt_target()]
    task = _make_task(GovernanceTaskType.ASSESS, [target.id for target in targets])
    _make_task_hosts(task, targets, ["cancelled", "cancelled"])

    pes._finalize_task_status(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.CANCELLED


@pytest.mark.django_db
def test_finalize_mixed_cancelled_hosts_marks_task_partial_cancelled():
    targets = [_make_node_mgmt_target(), _make_node_mgmt_target(), _make_node_mgmt_target()]
    task = _make_task(GovernanceTaskType.ASSESS, [target.id for target in targets])
    _make_task_hosts(task, targets, ["cancelled", "completed", "failed"])

    pes._finalize_task_status(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.PARTIAL_CANCELLED


@pytest.mark.django_db
def test_finalize_reboot_pending_host_keeps_task_running():
    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    _make_task_hosts(task, [target], ["pending_reboot"])

    pes._finalize_task_status(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING
    assert task.finished_at is None


@pytest.mark.django_db
def test_run_reboot_node_mgmt_target(monkeypatch):
    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    calls = []

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            calls.append(('local', command))
            return {'exit_code': 0}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    task.refresh_from_db()
    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'
    assert task.status == GovernanceTaskStatus.RUNNING
    assert any(c[0] == 'local' and 'shutdown' in c[1] for c in calls)


@pytest.mark.django_db
def test_run_reboot_manual_linux_target(monkeypatch):
    cloud_region = CloudRegion.objects.create(name='region-a')
    target = _make_manual_linux_target(cloud_region)
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    calls = []

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):
            calls.append(('ssh', kwargs.get('host'), command))
            return {'exit_code': 0}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'
    assert calls[0][0] == 'ssh'


@pytest.mark.django_db
def test_run_reboot_manual_windows_target(monkeypatch):
    cloud_region = CloudRegion.objects.create(name='region-b')
    target = _make_manual_windows_target(cloud_region)
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    calls = []

    class FakeNodeMgmt:
        def node_list(self, query):
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            calls.append(kwargs)
            return {'exit_code': 0}

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())
    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'
    assert calls[0]['module'] == 'win_shell'
    assert calls[0]['host_credentials'][0]['connection'] == 'winrm'


@pytest.mark.django_db
def test_run_assess_failure_records_reason(monkeypatch):
    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {'exit_code': 1, 'stderr': 'check failed'}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'failed'
    assert 'check failed' in host.reason
    assert host.can_retry is True
    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.FAILED


@pytest.mark.django_db
def test_run_missing_target_marks_host_and_task_failed():
    task = _make_task(GovernanceTaskType.ASSESS, [99999])
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=99999,
        target_name='已删除目标',
        target_ip='192.0.2.1',
        stage='waiting',
    )

    pes.run_governance_task(task)

    host.refresh_from_db()
    task.refresh_from_db()
    assert host.stage == 'failed'
    assert host.failed_stage == 'dispatch'
    assert host.can_retry is False
    assert '不存在或已删除' in host.reason
    assert task.status == GovernanceTaskStatus.FAILED


@pytest.mark.django_db
def test_retry_deleted_target_is_rejected_without_consuming_retry(monkeypatch):
    from apps.patch_mgmt.services import governance_service

    target = _make_node_mgmt_target()
    original_task = _make_task(GovernanceTaskType.ASSESS, [target.id])
    original_host = GovernanceTaskHost.objects.create(
        task=original_task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='failed',
        can_retry=True,
    )
    target_id = target.id
    target.delete()
    monkeypatch.setattr(governance_service, '_trigger_async', lambda task_id: None)

    with pytest.raises(ValueError, match='目标不存在或已删除'):
        governance_service.create_retry_task(
            RequestFactory().post('/'),
            original_task,
            target_id,
        )

    original_host.refresh_from_db()
    assert original_host.can_retry is True
    assert GovernanceTask.objects.count() == 1


@pytest.mark.django_db
def test_recovered_reboot_host_is_completed_when_verify_task_is_created(monkeypatch):
    from apps.patch_mgmt import tasks as patch_tasks

    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    task.status = GovernanceTaskStatus.COMPLETED
    task.save(update_fields=['status'])
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='pending_reboot',
        reason='重启命令已下发，等待主机恢复',
        boot_marker_before='boot-before',
    )
    GovernanceTaskHost.objects.filter(pk=host.pk).update(
        updated_at=timezone.now() - timedelta(minutes=2),
    )

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(pes, '_check_host_reachable', lambda target: True)
    monkeypatch.setattr(pes, '_read_boot_marker', lambda *args, **kwargs: 'boot-after')
    monkeypatch.setattr(patch_tasks, 'execute_governance_task', FakeCeleryTask)

    patch_tasks.verify_pending_reboot_hosts()

    host.refresh_from_db()
    task.refresh_from_db()
    assert host.stage == 'completed'
    assert host.stage_color == 'success'
    assert '主机已恢复' in host.reason
    assert task.status == GovernanceTaskStatus.COMPLETED
    assert GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.VERIFY,
        target_list=[target.id],
    ).exists()


@pytest.mark.django_db
def test_run_mixed_reboot_results_stays_running_while_host_is_pending(monkeypatch):
    targets = [_make_node_mgmt_target(), _make_node_mgmt_target()]
    task = _make_task(GovernanceTaskType.REBOOT, [t.id for t in targets])

    call_count = {'n': 0}

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            if 'boot_id' in command:
                return {'exit_code': 0, 'stdout': 'boot-before'}
            call_count['n'] += 1
            return {'exit_code': 0 if call_count['n'] == 1 else 1, 'stderr': 'err'}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING
    hosts = list(GovernanceTaskHost.objects.filter(task=task))
    assert any(h.stage == 'pending_reboot' for h in hosts)
    assert any(h.stage == 'reboot_failed' for h in hosts)


@pytest.mark.django_db
def test_run_assess_success_parses_output_and_writes_snapshot(monkeypatch):
    baseline = PatchBaseline.objects.create(name='baseline', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='gzip update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='gzip')
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {'exit_code': 0, 'stdout': APT_SAMPLE}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'completed'

    binding = HostBaselineBinding.objects.get(target=target)
    assert binding.compliance_status == ComplianceStatus.COMPLIANT
    assert binding.missing_count == 0
    assert binding.last_evaluated_at is not None
    assert HostComplianceSnapshot.objects.filter(binding=binding).count() == 1


@pytest.mark.django_db
def test_run_assess_yum_exit_100_treated_as_success(monkeypatch):
    baseline = PatchBaseline.objects.create(name='baseline-yum', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='gzip update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='gzip')
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    stdout = 'Available Upgrades\ngzip.x86_64     1.10-10ubuntu4.1     noble-updates\n'

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {'exit_code': 100, 'stdout': stdout}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'completed'

    binding = HostBaselineBinding.objects.get(target=target)
    assert binding.compliance_status == ComplianceStatus.NON_COMPLIANT
    assert binding.missing_count == 1


@pytest.mark.django_db
def test_reboot_task_leaves_host_pending_reboot(monkeypatch):
    """reboot 任务成功后，主机保持 pending_reboot，不立即创建 verify 任务（由定时任务处理）。"""
    target = _make_node_mgmt_target()
    task = _make_task(GovernanceTaskType.REBOOT, [target.id])
    task.team = [1]
    task.save(update_fields=['team'])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {'exit_code': 0}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    monkeypatch.setattr('apps.patch_mgmt.tasks.execute_governance_task', FakeCeleryTask)

    pes.run_governance_task(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.RUNNING

    # 主机保持 pending_reboot，等待定时任务探测恢复后创建 verify
    host = task.host_results.first()
    assert host.stage == 'pending_reboot'

    # 不应立即创建 verify 任务
    verify_task = GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.VERIFY,
    ).first()
    assert verify_task is None


@pytest.mark.django_db
def test_install_task_with_auto_reboot_creates_reboot_task(monkeypatch):
    """install 任务开启 auto_reboot 时，应自动创建 reboot 任务。"""
    cloud_region = CloudRegion.objects.create(name='region-auto-reboot')
    target = _make_manual_linux_target(cloud_region)

    patch = Patch.objects.create(title='tar update', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='tar')

    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.team = [1]
    task.save(update_fields=['auto_reboot', 'team'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):
            if 'needs-restarting' in command:
                return {
                    'exit_code': 0,
                    'stdout': 'RebootRequired=True\nRebootMethod=dnf',
                }
            return {'exit_code': 0}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    monkeypatch.setattr('apps.patch_mgmt.tasks.execute_governance_task', FakeCeleryTask)

    pes.run_governance_task(task)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.COMPLETED

    reboot_task = GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.REBOOT,
    ).first()
    assert reboot_task is not None
    assert reboot_task.target_list == [target.id]
    assert reboot_task.team == [1]
    assert reboot_task.name.startswith('自动重启')


@pytest.mark.django_db
def test_run_install_windows_success_creates_reboot_task(monkeypatch):
    """Windows install 成功（InstallResult=2）后标 pending_reboot 并按策略创建 reboot 任务。"""
    cloud_region = CloudRegion.objects.create(name='region-win-install-ok')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB5072653', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB5072653')

    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.team = [1]
    task.save(update_fields=['auto_reboot', 'team'])

    class FakeNodeMgmt:
        def node_list(self, query):  # noqa: ARG002
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=True'}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())
    monkeypatch.setattr('apps.patch_mgmt.tasks.execute_governance_task', FakeCeleryTask)

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'

    reboot_task = GovernanceTask.objects.filter(task_type=GovernanceTaskType.REBOOT).first()
    assert reboot_task is not None


@pytest.mark.django_db
def test_run_install_windows_without_reboot_creates_verify_only(monkeypatch):
    """WUA 明确无需重启时应跳过重启并自动验证。"""
    cloud_region = CloudRegion.objects.create(name='region-win-no-reboot')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB-NO-REBOOT', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB-NO-REBOOT')
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])
    delayed_ids = []

    class FakeNodeMgmt:
        def node_list(self, query):  # noqa: ARG002
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):  # noqa: ARG002
            return {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=False'}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):
            delayed_ids.append(task_id)

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())
    monkeypatch.setattr('apps.patch_mgmt.tasks.execute_governance_task', FakeCeleryTask)

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'completed'
    assert '无需重启' in host.reason
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.REBOOT).exists()
    verify_task = GovernanceTask.objects.get(task_type=GovernanceTaskType.VERIFY)
    assert verify_task.target_list == [target.id]
    assert verify_task.patch_list == [patch.id]
    assert delayed_ids == [verify_task.id]


@pytest.mark.django_db
def test_run_install_windows_unknown_reboot_stays_pending_without_auto_reboot(monkeypatch):
    """WUA 安装成功但未返回重启字段时安全降级为待重启。"""
    cloud_region = CloudRegion.objects.create(name='region-win-reboot-unknown')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB-UNKNOWN', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB-UNKNOWN')
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])

    class FakeNodeMgmt:
        def node_list(self, query):  # noqa: ARG002
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):  # noqa: ARG002
            return {'exit_code': 0, 'stdout': 'InstallResult=2'}

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'
    assert host.failed_stage == 'reboot_check'
    assert host.error_code == 'reboot_requirement_unknown'
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.REBOOT).exists()
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.VERIFY).exists()


@pytest.mark.django_db
def test_run_install_linux_without_reboot_creates_verify_only(monkeypatch):
    cloud_region = CloudRegion.objects.create(name='region-linux-no-reboot')
    target = _make_manual_linux_target(cloud_region)
    patch = Patch.objects.create(title='tar update', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='tar')
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):  # noqa: ARG002
            if 'needs-restarting' in command:
                return {'exit_code': 0, 'stdout': 'RebootRequired=False\nRebootMethod=dnf'}
            return {'exit_code': 0}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    monkeypatch.setattr('apps.patch_mgmt.tasks.execute_governance_task', FakeCeleryTask)

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'completed'
    assert GovernanceTask.objects.filter(task_type=GovernanceTaskType.VERIFY).exists()
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.REBOOT).exists()


@pytest.mark.django_db
def test_run_install_linux_unknown_reboot_is_not_auto_rebooted(monkeypatch):
    cloud_region = CloudRegion.objects.create(name='region-linux-reboot-unknown')
    target = _make_manual_linux_target(cloud_region)
    patch = Patch.objects.create(title='tar update', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='tar')
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):  # noqa: ARG002
            if 'needs-restarting' in command:
                return {
                    'exit_code': 0,
                    'stdout': (
                        'RebootRequired=Unknown\nRebootMethod=dnf\n'
                        'RebootDetail=needs-restarting unavailable'
                    ),
                }
            return {'exit_code': 0}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'pending_reboot'
    assert host.error_code == 'reboot_requirement_unknown'
    assert not GovernanceTask.objects.filter(task_type=GovernanceTaskType.REBOOT).exists()


@pytest.mark.django_db
def test_run_install_windows_failure_marks_failed_can_retry(monkeypatch):
    """Windows install 失败（InstallResult=4）后标 failed 且可重试。"""
    cloud_region = CloudRegion.objects.create(name='region-win-install-fail')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB5072653', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB5072653')

    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.team = [1]
    task.save(update_fields=['team'])

    class FakeNodeMgmt:
        def node_list(self, query):  # noqa: ARG002
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'InstallResult=4 RebootRequired=False'}

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'failed'
    assert host.failed_stage == 'install'
    assert host.can_retry is True
    assert '失败' in host.reason


@pytest.mark.django_db
def test_run_install_windows_no_matching_marks_failed_no_retry(monkeypatch):
    """Windows install 未找到更新时标 failed 且不可重试。"""
    cloud_region = CloudRegion.objects.create(name='region-win-install-none')
    target = _make_manual_windows_target(cloud_region)
    patch = Patch.objects.create(title='KB5072653', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(patch=patch, kb_number='KB5072653')

    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.team = [1]
    task.save(update_fields=['team'])

    class FakeNodeMgmt:
        def node_list(self, query):  # noqa: ARG002
            return {'nodes': [{'id': 'ansible-node-1'}]}

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'No matching updates found'}

    monkeypatch.setattr(pes, 'NodeMgmt', FakeNodeMgmt)
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert host.stage == 'failed'
    assert host.failed_stage == 'install'
    assert host.can_retry is False
    assert '未找到' in host.reason


@pytest.mark.django_db
def test_run_install_continues_remaining_manual_windows_packages_after_failure(monkeypatch):
    """手工 Windows 补丁逐包安装时，单包失败不能阻断后续补丁。"""
    cloud_region = CloudRegion.objects.create(name='region-win-manual-batch')
    target = _make_manual_windows_target(cloud_region)
    failed_patch = Patch.objects.create(title='KB6000101', os_type=OSType.WINDOWS)
    failed_detail = WindowsPatchDetail.objects.create(
        patch=failed_patch,
        kb_number='KB6000101',
        package_file='windows/1/failed.msu',
        package_original_name='failed.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )
    success_patch = Patch.objects.create(title='KB6000102', os_type=OSType.WINDOWS)
    success_detail = WindowsPatchDetail.objects.create(
        patch=success_patch,
        kb_number='KB6000102',
        package_file='windows/1/success.msu',
        package_original_name='success.msu',
        package_sha256='b' * 64,
        package_extension='.msu',
    )
    task = _make_task(
        GovernanceTaskType.INSTALL,
        [target.id],
        patch_ids=[failed_patch.id, success_patch.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='waiting',
    )
    executed_commands = []

    monkeypatch.setattr(
        pes,
        '_stage_windows_package',
        lambda _target, detail, **kwargs: f'C:/staged/{detail.package_original_name}',
    )

    def execute_command(_target, command, **kwargs):
        executed_commands.append(command)
        if len(executed_commands) == 1:
            return {'exit_code': 1, 'stderr': 'first package failed'}
        assert success_detail.package_original_name in command or failed_detail.package_original_name in command
        return {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=False'}

    monkeypatch.setattr(pes, '_execute_command', execute_command)

    pes._execute_install(
        target,
        host,
        [failed_patch.id, success_patch.id],
        execution_id='manual-batch',
        timeout=300,
    )

    host.refresh_from_db()
    assert len(executed_commands) == 2
    assert host.stage == 'failed'
    assert 'first package failed' in host.reason


@pytest.mark.django_db
def test_run_install_continues_after_manual_windows_package_staging_failure(monkeypatch):
    """一个手工包分发失败时仍安装同批其余包，最终汇总为失败。"""
    cloud_region = CloudRegion.objects.create(name='region-win-manual-stage-fail')
    target = _make_manual_windows_target(cloud_region)
    failed_patch = Patch.objects.create(title='KB6000111', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(
        patch=failed_patch,
        kb_number='KB6000111',
        package_file='windows/1/stage-failed.msu',
        package_original_name='stage-failed.msu',
        package_sha256='a' * 64,
        package_extension='.msu',
    )
    success_patch = Patch.objects.create(title='KB6000112', os_type=OSType.WINDOWS)
    WindowsPatchDetail.objects.create(
        patch=success_patch,
        kb_number='KB6000112',
        package_file='windows/1/stage-success.msu',
        package_original_name='stage-success.msu',
        package_sha256='b' * 64,
        package_extension='.msu',
    )
    task = _make_task(
        GovernanceTaskType.INSTALL,
        [target.id],
        patch_ids=[failed_patch.id, success_patch.id],
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='waiting',
    )
    executed_commands = []

    def stage_package(_target, detail, **kwargs):
        if detail.package_original_name == 'stage-failed.msu':
            raise RuntimeError('distribution failed')
        return f'C:/staged/{detail.package_original_name}'

    monkeypatch.setattr(pes, '_stage_windows_package', stage_package)
    monkeypatch.setattr(
        pes,
        '_execute_command',
        lambda _target, command, **kwargs: (
            executed_commands.append(command)
            or {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=False'}
        ),
    )

    pes._execute_install(
        target,
        host,
        [failed_patch.id, success_patch.id],
        execution_id='manual-stage-fail',
        timeout=300,
    )

    host.refresh_from_db()
    assert len(executed_commands) == 1
    assert 'stage-success.msu' in executed_commands[0]
    assert host.stage == 'failed'
    assert 'distribution failed' in host.reason
