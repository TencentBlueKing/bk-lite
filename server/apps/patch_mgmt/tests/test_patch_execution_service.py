'''补丁治理任务真实执行服务单元测试

通过 mock Executor / AnsibleExecutor 验证：
- 命令生成
- 执行器路由
- GovernanceTaskHost / GovernanceTask 状态回写
'''

import base64
from datetime import timedelta
from types import SimpleNamespace

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
from apps.patch_mgmt.services import target_execution_route as ter


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
    """Linux 安装命令只使用预先识别出的原生包管理器。"""
    p_yum = Patch.objects.create(title='yum-patch', os_type=OSType.LINUX)
    p_dnf = Patch.objects.create(title='dnf-patch', os_type=OSType.LINUX)
    p_apt = Patch.objects.create(title='apt-patch', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p_yum, pkg_name='yum-pkg')
    LinuxPatchDetail.objects.create(patch=p_dnf, pkg_name='dnf-pkg')
    LinuxPatchDetail.objects.create(patch=p_apt, pkg_name='apt-pkg')
    cmds = pes._install_commands([p_yum, p_dnf, p_apt], OSType.LINUX, linux_manager='apt')
    assert len(cmds) == 1
    cmd = cmds[0]
    assert 'apt-get install -y --no-remove' in cmd
    assert 'yum-pkg' in cmd and 'dnf-pkg' in cmd and 'apt-pkg' in cmd
    assert 'dnf ' not in cmd and 'yum install' not in cmd


def test_linux_assess_uses_rpm_native_version_comparison_not_provides_lookup():
    requirement = SimpleNamespace(
        id=17,
        patch=SimpleNamespace(
            linux_detail=SimpleNamespace(
                pkg_name='ledmon',
                pkg_version='0.95-6.el9',
            )
        ),
    )

    command = pes._assess_command(OSType.LINUX, [requirement])

    assert 'rpm.vercmp' in command
    assert 'BKPATCH_INSTALLED' in command
    assert '--whatprovides' not in command


@pytest.mark.django_db
def test_install_commands_multiple_pkgs_one_command():
    """多个补丁的包名合并到同一条安装命令。"""
    p1 = Patch.objects.create(title='apt-1', os_type=OSType.LINUX)
    p2 = Patch.objects.create(title='apt-2', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p1, pkg_name='pkg-a')
    LinuxPatchDetail.objects.create(patch=p2, pkg_name='pkg-b')
    cmds = pes._install_commands([p1, p2], OSType.LINUX, linux_manager='apt')
    assert len(cmds) == 1
    assert 'pkg-a' in cmds[0]
    assert 'pkg-b' in cmds[0]


@pytest.mark.django_db
@pytest.mark.integration
def test_install_commands_include_every_package_from_one_advisory():
    patch = Patch.objects.create(title='multi-package', os_type=OSType.LINUX)
    detail = LinuxPatchDetail.objects.create(patch=patch, pkg_name='pkg-a')
    detail.packages = [
        {'name': 'pkg-a', 'version': '1.0', 'arch': 'x86_64'},
        {'name': 'pkg-b', 'version': '1.0', 'arch': 'x86_64'},
        {'name': 'pkg-b', 'version': '1.0', 'arch': 'x86_64'},
        {'name': 'pkg with space', 'version': '1.0', 'arch': 'x86_64'},
        {'name': '', 'version': '1.0', 'arch': 'x86_64'},
    ]
    detail.save(update_fields=['packages'])

    commands = pes._install_commands([patch], OSType.LINUX, linux_manager='dnf')

    assert len(commands) == 1
    assert commands[0].count('pkg-a') == 1
    assert commands[0].count('pkg-b') == 1
    assert 'pkg with space' not in commands[0]


@pytest.mark.django_db
@pytest.mark.integration
def test_assess_command_collects_every_package_from_one_advisory():
    baseline = PatchBaseline.objects.create(name='multi-package', os_type=OSType.LINUX)
    patch = Patch.objects.create(title='multi-package', os_type=OSType.LINUX)
    detail = LinuxPatchDetail.objects.create(patch=patch, pkg_name='pkg-a', pkg_version='1.0')
    detail.packages = [
        {'name': 'pkg-a', 'version': '1.0', 'arch': 'x86_64'},
        {'name': 'pkg-b', 'version': '2.0', 'arch': 'x86_64'},
    ]
    detail.save(update_fields=['packages'])
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    command = pes._assess_command(OSType.LINUX, [requirement])

    assert f'BKPATCH_LINUX|{requirement.id}|0|pkg-a|' in command
    assert f'BKPATCH_LINUX|{requirement.id}|1|pkg-b|' in command
    assert 'required=1.0' in command
    assert 'required=2.0' in command


@pytest.mark.unit
def test_collect_install_impact_dry_runs_each_requirement_independently(monkeypatch):
    detail = SimpleNamespace(package_names=lambda: ['pkg-a', 'pkg-b', 'pkg;rm'])
    requirement = SimpleNamespace(id=17, patch=SimpleNamespace(linux_detail=detail))
    second = SimpleNamespace(
        id=18,
        patch=SimpleNamespace(linux_detail=SimpleNamespace(package_names=lambda: ['pkg-c'])),
    )
    target = SimpleNamespace(id=23, os_type=OSType.LINUX)
    executed = []

    def execute_command(_target, command, **_kwargs):
        executed.append(command)
        return {'stdout': '2 upgraded, 0 newly installed, 0 to remove'}

    monkeypatch.setattr(pes, '_execute_command', execute_command)

    impact = pes._collect_install_impact(target, [requirement, second], 'dry-run-1', 'apt')

    assert len(executed) == 2
    assert 'pkg-a' in executed[0] and 'pkg-b' in executed[0]
    assert 'pkg;rm' not in executed[0]
    assert 'pkg-c' not in executed[0] and 'pkg-c' in executed[1]
    assert all('apt-get -s install' in command for command in executed)
    assert all('dnf' not in command and 'yum' not in command for command in executed)
    assert impact[requirement.id]['summary'] == '2 upgraded, 0 newly installed, 0 to remove'


@pytest.mark.django_db
def test_install_commands_skips_invalid_pkg_name():
    p1 = Patch.objects.create(title='apt-1', os_type=OSType.LINUX)
    p2 = Patch.objects.create(title='apt-2', os_type=OSType.LINUX)
    LinuxPatchDetail.objects.create(patch=p1, pkg_name='pkg-a')
    LinuxPatchDetail.objects.create(patch=p2, pkg_name='pkg with space')
    cmds = pes._install_commands([p1, p2], OSType.LINUX, linux_manager='apt')
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


def test_windows_assess_command_collects_offered_and_installed_wua_updates():
    command = pes._assess_command(OSType.WINDOWS)

    assert 'Get-CimInstance Win32_OperatingSystem' in command
    assert 'BKPATCH_HOST|WINDOWS|' in command
    assert '$sr.Search("IsInstalled=0")' in command
    assert '$sr.Search("IsInstalled=1")' in command
    assert '===WUA_INSTALLED===' in command
    assert '===HOTFIX===' in command


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


def test_linux_reboot_check_command_is_fixed_to_identified_manager():
    apt_command = pes._linux_reboot_check_command('apt')
    dnf_command = pes._linux_reboot_check_command('dnf')
    yum_command = pes._linux_reboot_check_command('yum')

    assert '/run/reboot-required' in apt_command and 'dnf' not in apt_command and 'yum' not in apt_command
    assert 'dnf -q needs-restarting' in dnf_command and 'yum ' not in dnf_command and 'apt-get' not in dnf_command
    assert 'yum -q needs-restarting' in yum_command and 'dnf ' not in yum_command and 'apt-get' not in yum_command


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


def _bind_missing_rpm_patch(target, patch):
    LinuxPatchDetail.objects.update_or_create(
        patch=patch,
        defaults={
            'pkg_name': 'tar',
            'pkg_version': '1.0',
            'distro_name': 'Rocky',
            'os_version_range': '9',
            'architectures': ['x86_64'],
            'repo_type': 'dnf',
        },
    )
    baseline = PatchBaseline.objects.create(
        name=f'baseline-{target.id}-{patch.id}', os_type=OSType.LINUX, team=[1]
    )
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        status='missing',
        evaluated_at=timezone.now(),
    )
    return requirement


def _bind_missing_apt_patch(target, patch):
    LinuxPatchDetail.objects.update_or_create(
        patch=patch,
        defaults={
            'pkg_name': 'hello',
            'pkg_version': '2.10',
            'distro_name': 'Ubuntu',
            'os_version_range': '24.04',
            'architectures': ['x86_64'],
            'repo_type': 'apt',
        },
    )
    baseline = PatchBaseline.objects.create(
        name=f'apt-baseline-{target.id}-{patch.id}', os_type=OSType.LINUX, team=[1]
    )
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        status='missing',
        evaluated_at=timezone.now(),
    )
    return requirement


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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            calls.append(kwargs)
            return {'exit_code': 0}

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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
    from apps.patch_mgmt.exceptions import PatchBusinessError
    from apps.patch_mgmt.services import governance_service

    Patch.objects.create(id=20, title="retry patch", os_type=OSType.LINUX)
    target = _make_node_mgmt_target()
    original_task = _make_task(GovernanceTaskType.INSTALL, [target.id], [20])
    risk_item_id = f"{target.id}:20:30"
    original_task.risk_snapshot = [{
        "id": risk_item_id,
        "host_id": target.id,
        "patch_id": 20,
    }]
    original_task.save(update_fields=["risk_snapshot", "updated_at"])
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

    with pytest.raises(PatchBusinessError) as exc_info:
        governance_service.create_retry_task(
            RequestFactory().post('/'),
            original_task,
            risk_item_id,
        )
    assert exc_info.value.code == 'target_deleted'

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
    LinuxPatchDetail.objects.create(
        patch=patch, pkg_name='gzip', pkg_version='1.10', distro_name='Ubuntu',
        os_version_range='24.04', architectures=['x86_64'], repo_type='apt',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {
                'exit_code': 0,
                'stdout': '\n'.join([
                    'BKPATCH_HOST|LINUX|ubuntu|debian|24.04|x86_64|apt',
                    f'BKPATCH_LINUX|{requirement.id}|gzip|installed|1.10|0|',
                ]),
            }

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
def test_run_assess_batches_large_multi_package_dnf_advisory(monkeypatch):
    baseline = PatchBaseline.objects.create(
        name='large-dnf-advisory', os_type=OSType.LINUX, team=[1]
    )
    target = _make_node_mgmt_target()
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='large dnf advisory', os_type=OSType.LINUX, team=[1])
    packages = [
        {'name': f'pkg-{index}', 'version': '1.0-1.el9', 'arch': 'x86_64'}
        for index in range(100)
    ]
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name=packages[0]['name'],
        pkg_version=packages[0]['version'],
        packages=packages,
        distro_name='Rocky Linux',
        os_version_range='9',
        architectures=['x86_64'],
        repo_type='dnf',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])
    executed_commands = []

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):  # noqa: ARG002
            executed_commands.append(command)
            output = ['BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf']
            for index, package in enumerate(packages):
                marker = f'BKPATCH_LINUX|{requirement.id}|{index}|{package["name"]}|'
                if marker in command:
                    output.append(f'{marker}installed|{package["version"]}|0|')
            return {'exit_code': 0, 'stdout': '\n'.join(output)}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())

    pes.run_governance_task(task)

    assert len(executed_commands) > 1
    assert all(len(command.encode('utf-8')) <= 64 * 1024 for command in executed_commands)
    binding.refresh_from_db()
    assert binding.compliance_status == ComplianceStatus.COMPLIANT
    assert binding.missing_count == 0


@pytest.mark.django_db
def test_run_assess_fails_whole_host_when_linux_facts_are_missing(monkeypatch):
    baseline = PatchBaseline.objects.create(name='facts-required', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='gzip update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch, pkg_name='gzip', pkg_version='1.10', distro_name='Ubuntu',
        os_version_range='24.04', architectures=['x86_64'], repo_type='apt',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):  # noqa: ARG002
            return {
                'exit_code': 0,
                'stdout': f'BKPATCH_LINUX|{requirement.id}|0|gzip|installed|1.10|0|',
            }

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    binding.refresh_from_db()
    assert host.stage == 'failed'
    assert host.error_code == 'linux_host_facts_unavailable'
    assert binding.compliance_status == ComplianceStatus.FAILED
    assert not HostComplianceSnapshot.objects.filter(binding=binding).exists()


@pytest.mark.django_db
def test_run_windows_assess_keeps_missing_risk_when_another_requirement_is_unknown(monkeypatch):
    cloud_region = CloudRegion.objects.create(name='region-win-mixed-assessment')
    target = _make_manual_windows_target(cloud_region)
    baseline = PatchBaseline.objects.create(name='windows-mixed-baseline', os_type=OSType.WINDOWS, team=[1])
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    missing_patch = Patch.objects.create(title='applicable update', os_type=OSType.WINDOWS, team=[1])
    unknown_patch = Patch.objects.create(title='catalog invisible update', os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=missing_patch, kb_number='KB5000003')
    WindowsPatchDetail.objects.create(patch=unknown_patch, kb_number='KB9999999')
    missing_requirement = BaselineRequirement.objects.create(baseline=baseline, patch=missing_patch)
    unknown_requirement = BaselineRequirement.objects.create(baseline=baseline, patch=unknown_patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])
    stdout = '\n'.join(
        [
            'BKPATCH_HOST|WINDOWS|Microsoft Windows Server 2022 Standard|10.0|20348|AMD64',
            '===WUA===',
            'KB5000003|Important|Applicable update',
            '===WUA_INSTALLED===',
            '===HOTFIX===',
        ]
    )

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):  # noqa: ARG002
            return {'exit_code': 0, 'stdout': stdout}

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
    monkeypatch.setattr(pes, 'AnsibleExecutor', lambda instance_id: FakeAnsibleExecutor())

    pes.run_governance_task(task)

    binding.refresh_from_db()
    assert binding.compliance_status == ComplianceStatus.NON_COMPLIANT
    assert binding.missing_count == 1
    assert HostComplianceSnapshot.objects.get(
        binding=binding,
        requirement=missing_requirement,
    ).status == 'missing'
    assert HostComplianceSnapshot.objects.get(
        binding=binding,
        requirement=unknown_requirement,
    ).status == 'unknown'


@pytest.mark.django_db
def test_run_verify_freezes_pair_result_snapshot(monkeypatch):
    baseline = PatchBaseline.objects.create(name='verify-baseline', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='gzip update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch, pkg_name='gzip', pkg_version='1.10', distro_name='Ubuntu',
        os_version_range='24.04', architectures=['x86_64'], repo_type='apt',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    risk_item_id = f'{target.id}:{patch.id}:{baseline.id}'
    task = _make_task(GovernanceTaskType.VERIFY, [target.id], [patch.id])
    task.risk_snapshot = [{
        'id': risk_item_id,
        'host_id': target.id,
        'patch_id': patch.id,
        'baseline_id': baseline.id,
    }]
    task.save(update_fields=['risk_snapshot', 'updated_at'])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            return {
                'exit_code': 0,
                'stdout': '\n'.join([
                    'BKPATCH_HOST|LINUX|ubuntu|debian|24.04|x86_64|apt',
                    f'BKPATCH_LINUX|{requirement.id}|gzip|installed|1.10|0|',
                ]),
            }

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    task.refresh_from_db()
    assert len(task.result_snapshot) == 1
    result = task.result_snapshot[0]
    assert result['risk_item_id'] == risk_item_id
    assert result['host_id'] == target.id
    assert result['patch_id'] == patch.id
    assert result['status'] == 'completed'
    assert result['satisfied'] is True
    assert result['reason']
    assert result['evidence']
    assert result['evaluated_at']


@pytest.mark.django_db
def test_run_assess_yum_exit_100_treated_as_success(monkeypatch):
    baseline = PatchBaseline.objects.create(name='baseline-yum', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='gzip update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch, pkg_name='gzip', pkg_version='1.10', distro_name='Rocky',
        os_version_range='9', architectures=['x86_64'], repo_type='yum',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    stdout = '\n'.join([
        'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
        f'BKPATCH_LINUX|{requirement.id}|gzip|installed|1.9|-1|',
    ])

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
@pytest.mark.parametrize('package_manager', ['dnf', 'yum'])
def test_run_assess_accepts_rpm_assumeno_abort_as_successful_preview(monkeypatch, package_manager):
    baseline = PatchBaseline.objects.create(name=f'baseline-{package_manager}-preview', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='libmbim update', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name='libmbim',
        pkg_version='1.26.0-2.el9',
        distro_name='Rocky Linux',
        os_version_range='9',
        architectures=['x86_64'],
        repo_type=package_manager,
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])

    assessment_stdout = '\n'.join([
        f'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|{package_manager}',
        f'BKPATCH_LINUX|{requirement.id}|0|libmbim|absent|||',
    ])
    expected_abort = '\n'.join([
        'Command execution failed: Process exited with status 1 | Output: Last metadata expiration check: 1:00:00 ago.',
        'Dependencies resolved.',
        '================================================================================',
        ' Package       Architecture   Version         Repository   Size',
        '================================================================================',
        'Installing:',
        ' libmbim       x86_64         1.32.0-1.el9    baseos       252 k',
        '',
        'Transaction Summary',
        '================================================================================',
        'Install  1 Package',
        '',
        'Operation aborted.',
    ])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            if f'{package_manager} install --assumeno' in command:
                raise RuntimeError(expected_abort)
            return {'exit_code': 0, 'stdout': assessment_stdout}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    snapshot = HostComplianceSnapshot.objects.get(binding=binding, requirement=requirement)
    impact = snapshot.evidence['install_impact']
    assert impact['summary'] == 'Install  1 Package'
    assert impact['install'] == ['libmbim (1.32.0-1.el9)']
    assert 'error' not in impact


@pytest.mark.django_db
def test_run_assess_keeps_unresolved_dnf_transaction_as_preview_error(monkeypatch):
    baseline = PatchBaseline.objects.create(name='baseline-dnf-error', os_type=OSType.LINUX, team=[1])
    target = _make_node_mgmt_target()
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    patch = Patch.objects.create(title='missing package', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name='not-in-repository',
        pkg_version='1.0-1.el9',
        distro_name='Rocky Linux',
        os_version_range='9',
        architectures=['x86_64'],
        repo_type='dnf',
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    task = _make_task(GovernanceTaskType.ASSESS, [target.id])
    assessment_stdout = '\n'.join([
        'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
        f'BKPATCH_LINUX|{requirement.id}|0|not-in-repository|absent|||',
    ])

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):
            if 'dnf install --assumeno' in command:
                raise RuntimeError(
                    'Command execution failed: Process exited with status 1 | Output: '
                    'No match for argument: not-in-repository\nError: Unable to find a match'
                )
            return {'exit_code': 0, 'stdout': assessment_stdout}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())
    pes.run_governance_task(task)

    snapshot = HostComplianceSnapshot.objects.get(binding=binding, requirement=requirement)
    impact = snapshot.evidence['install_impact']
    assert impact['summary'] == ''
    assert 'Unable to find a match' in impact['error']


@pytest.mark.django_db
def test_run_install_rejects_patch_that_is_no_longer_missing(monkeypatch):
    target = _make_node_mgmt_target()
    baseline = PatchBaseline.objects.create(name='stale-install-baseline', os_type=OSType.LINUX, team=[1])
    binding = HostBaselineBinding.objects.create(
        target=target,
        baseline=baseline,
        compliance_status=ComplianceStatus.NOT_APPLICABLE,
    )
    patch = Patch.objects.create(title='foreign package', os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name='foreign-package', pkg_version='1.0')
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        status='not_applicable',
        reason='不适用于当前主机',
        evaluated_at=timezone.now(),
    )
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], [patch.id])
    task.risk_snapshot = [
        {
            'host_id': target.id,
            'patch_id': patch.id,
            'baseline_id': baseline.id,
        }
    ]
    task.save(update_fields=['risk_snapshot', 'updated_at'])
    calls = []

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):  # noqa: ARG002
            calls.append(command)
            return {'exit_code': 0}

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert calls == []
    assert host.stage == 'failed'
    assert host.error_code == 'assessment_stale'
    assert '最新评估' in host.reason


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
    _bind_missing_rpm_patch(target, patch)

    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.team = [1]
    task.save(update_fields=['auto_reboot', 'team'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):
            if 'BKPATCH_HOST|LINUX' in command:
                return {
                    'exit_code': 0,
                    'stdout': 'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
                }
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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=True'}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):  # noqa: ARG004
            pass

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):  # noqa: ARG002
            return {'exit_code': 0, 'stdout': 'InstallResult=2 RebootRequired=False'}

    class FakeCeleryTask:
        @staticmethod
        def delay(task_id):
            delayed_ids.append(task_id)

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):  # noqa: ARG002
            return {'exit_code': 0, 'stdout': 'InstallResult=2'}

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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
    _bind_missing_rpm_patch(target, patch)
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):  # noqa: ARG002
            if 'BKPATCH_HOST|LINUX' in command:
                return {
                    'exit_code': 0,
                    'stdout': 'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
                }
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
    _bind_missing_rpm_patch(target, patch)
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.auto_reboot = True
    task.save(update_fields=['auto_reboot'])

    class FakeExecutor:
        def execute_ssh_stream(self, command, **kwargs):  # noqa: ARG002
            if 'BKPATCH_HOST|LINUX' in command:
                return {
                    'exit_code': 0,
                    'stdout': 'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
                }
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
def test_run_install_rejects_apt_patch_on_rpm_host_before_install(monkeypatch):
    target = _make_node_mgmt_target()
    patch = Patch.objects.create(title='apt-only patch', os_type=OSType.LINUX)
    _bind_missing_apt_patch(target, patch)
    binding = HostBaselineBinding.objects.get(target=target)
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    task.risk_snapshot = [{
        'host_id': target.id,
        'patch_id': patch.id,
        'baseline_id': binding.baseline_id,
    }]
    task.save(update_fields=['risk_snapshot', 'updated_at'])
    commands = []

    class FakeExecutor:
        def execute_local_stream(self, command, **kwargs):  # noqa: ARG002
            commands.append(command)
            return {
                'exit_code': 0,
                'stdout': 'BKPATCH_HOST|LINUX|rocky|rhel|9.6|x86_64|dnf',
            }

    monkeypatch.setattr(pes, 'Executor', lambda instance_id: FakeExecutor())

    pes.run_governance_task(task)

    host = GovernanceTaskHost.objects.get(task=task, target_id=target.id)
    assert len(commands) == 1
    assert 'has_dpkg' in commands[0]
    assert host.stage == 'failed'
    assert host.failed_stage == 'install_preflight'
    assert host.error_code == 'linux_patch_not_applicable'


@pytest.mark.django_db
def test_execute_install_on_apt_host_never_falls_back_to_dnf_or_yum(monkeypatch):
    target = _make_node_mgmt_target()
    patch = Patch.objects.create(title='apt native patch', os_type=OSType.LINUX)
    _bind_missing_apt_patch(target, patch)
    task = _make_task(GovernanceTaskType.INSTALL, [target.id], patch_ids=[patch.id])
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage='waiting',
    )
    commands = []

    def execute_command(_target, command, **kwargs):  # noqa: ARG001
        commands.append(command)
        if 'BKPATCH_HOST|LINUX' in command:
            return {
                'exit_code': 0,
                'stdout': 'BKPATCH_HOST|LINUX|ubuntu|debian|24.04|x86_64|apt',
            }
        if 'reboot-required' in command:
            return {'exit_code': 0, 'stdout': 'RebootRequired=False\nRebootMethod=apt'}
        return {'exit_code': 0, 'stdout': 'apt install completed'}

    monkeypatch.setattr(pes, '_execute_command', execute_command)

    pes._execute_install(target, host, [patch.id], execution_id='apt-native', timeout=300)

    host.refresh_from_db()
    install_commands = [command for command in commands if ' install ' in command]
    assert len(install_commands) == 1
    assert 'apt-get install -y --no-remove' in install_commands[0]
    assert 'dnf ' not in install_commands[0]
    assert 'yum ' not in install_commands[0]
    assert host.stage == 'completed'


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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'InstallResult=4 RebootRequired=False'}

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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

    class FakeAnsibleExecutor:
        def adhoc(self, **kwargs):
            return {'exit_code': 0, 'stdout': 'No matching updates found'}

    monkeypatch.setattr(ter.AnsibleExecutorResolver, 'resolve', lambda cloud_region_id: 'ansible-node-1')
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
