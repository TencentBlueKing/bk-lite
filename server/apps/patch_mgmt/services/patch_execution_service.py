'''补丁治理任务真实执行服务

负责把 GovernanceTask 拆分到每台 PatchTarget，并调用平台已有执行器：
- node_mgmt 目标 -> 节点上 nats-executor 本地执行（instance_id = node_id）
- manual Linux 目标 -> 云区域 nats-executor 代理 SSH 执行
- manual Windows 目标 -> 云区域 Ansible Executor 节点通过 WinRM 执行

当前覆盖：
- reboot：生成系统重启命令并立即下发。
- install / assess：生成对应平台的补丁命令并下发，安装时由目标主机从配置源下载。

所有执行结果回写到 GovernanceTaskHost（stage / exit_code / reason 等）。
'''

import logging
import re
import shlex
import time
import uuid
from datetime import timedelta
from typing import Any, Optional

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.mixinx import EncryptMixin
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
    PatchTargetSource,
)
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, HostBaselineBinding, HostComplianceSnapshot, Patch, PatchTarget
from apps.patch_mgmt.services.assess_parsers import assess_requirements
from apps.rpc.ansible import AnsibleExecutor
from apps.rpc.executor import Executor
from apps.rpc.node_mgmt import NodeMgmt

logger = logging.getLogger('app')

DEFAULT_TIMEOUT = 3600
WINDOWS_PATCH_STAGE_DIR = 'C:/Windows/Temp/bk-lite-patches'


def _decrypt_password(password: Optional[str]) -> Optional[str]:
    if not password:
        return None
    data = {'password': password}
    EncryptMixin.decrypt_field('password', data)
    return data.get('password')


def _read_ssh_key(target: PatchTarget) -> Optional[str]:
    if not target.ssh_key_file:
        return None
    try:
        with target.ssh_key_file.open('r') as fh:
            return fh.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取目标 %s SSH 私钥失败: %s', target.id, exc)
        return None


def _get_cloud_region_name(cloud_region_id: Optional[int]) -> str:
    from apps.node_mgmt.models import CloudRegion

    if not cloud_region_id:
        raise ValueError('目标未配置云区域')
    try:
        return CloudRegion.objects.get(pk=cloud_region_id).name
    except CloudRegion.DoesNotExist as exc:
        raise ValueError(f'云区域 {cloud_region_id} 不存在') from exc


def _get_nats_executor_instance_id(target: PatchTarget) -> str:
    '''返回可用于 Executor 的 instance_id。'''
    if target.source_type == PatchTargetSource.NODE_MGMT and target.node_id:
        return target.node_id

    if target.source_type == PatchTargetSource.MANUAL:
        from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
        from apps.node_mgmt.services.cloudregion import RegionService

        region_name = _get_cloud_region_name(target.cloud_region_id)
        return RegionService.get_region_service_instance_id(
            region_name, CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME
        )

    raise ValueError(f'目标 {target.id} 无法确定执行器实例')


def _get_ansible_executor_instance_id(cloud_region_id: Optional[int]) -> str:
    '''获取云区域内的 Ansible Executor 容器节点 ID。'''
    if not cloud_region_id:
        raise ValueError('manual Windows 目标必须配置云区域')
    node_mgmt = NodeMgmt()
    result = node_mgmt.node_list(
        {
            'cloud_region_id': cloud_region_id,
            'is_container': True,
            'page': 1,
            'page_size': 1,
            'skip_permission': True,
        }
    )
    nodes = (result or {}).get('nodes', []) if isinstance(result, dict) else []
    if not nodes:
        raise ValueError(f'云区域 {cloud_region_id} 下未找到可用的 Ansible 执行节点')
    return nodes[0]['id']


def _execute_windows_manual(
    target: PatchTarget,
    command: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    execution_id: Optional[str] = None,
    stream_log_topic: Optional[str] = None,
) -> dict[str, Any]:
    '''按显式配置执行 Windows 命令；生产不得隐式降级为直连。'''
    mode = getattr(settings, 'PATCH_MGMT_WINDOWS_EXECUTION_MODE', 'executor')
    if mode == 'direct_winrm':
        if not settings.DEBUG:
            raise RuntimeError('direct_winrm 仅允许在 DEBUG=True 的本地环境使用')
        return _execute_winrm_direct(target, command, timeout=timeout)
    if mode != 'executor':
        raise RuntimeError(f'不支持的 Windows 执行模式: {mode}')

    ansible_node_id = _get_ansible_executor_instance_id(target.cloud_region_id)
    executor = AnsibleExecutor(ansible_node_id)
    password = _decrypt_password(target.winrm_password)
    host_credentials = [
        {
            'host': target.ip,
            'port': target.winrm_port,
            'user': target.winrm_user,
            'password': password,
            'connection': 'winrm',
            'winrm_scheme': target.winrm_scheme,
            'winrm_transport': target.winrm_transport,
            'winrm_cert_validation': target.winrm_cert_validation,
        }
    ]
    return executor.adhoc(
        host_credentials=host_credentials,
        module='win_shell',
        module_args=command,
        timeout=timeout,
        execution_id=execution_id,
        stream_log_topic=stream_log_topic,
    ) or {}


def _execute_winrm_direct(
    target: PatchTarget,
    command: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    '''pywinrm 直连执行 PowerShell（仅供 DEBUG 本地显式配置）。'''
    import winrm

    password = _decrypt_password(target.winrm_password)
    scheme = target.winrm_scheme or 'http'
    port = target.winrm_port or 5985
    transport = target.winrm_transport or 'basic'
    cert_validation = 'ignore' if not target.winrm_cert_validation else 'validate'

    endpoint = f'{scheme}://{target.ip}:{port}/wsman'
    session = winrm.Session(
        endpoint,
        auth=(target.winrm_user, password),
        transport=transport,
        server_cert_validation=cert_validation,
        operation_timeout_sec=min(timeout, 300),
        read_timeout_sec=min(timeout + 10, 310),
    )
    result = session.run_ps(command)
    return {
        'stdout': result.std_out.decode('utf-8', errors='replace') if result.std_out else '',
        'stderr': result.std_err.decode('utf-8', errors='replace') if result.std_err else '',
        'exit_code': result.status_code,
    }


def _windows_host_credentials(target: PatchTarget) -> list[dict[str, Any]]:
    return [{
        'host': target.ip,
        'port': target.winrm_port,
        'user': target.winrm_user,
        'password': _decrypt_password(target.winrm_password),
        'connection': 'winrm',
        'winrm_scheme': target.winrm_scheme,
        'winrm_transport': target.winrm_transport,
        'winrm_cert_validation': target.winrm_cert_validation,
    }]


def _short_lived_package_url(detail) -> str:
    storage = detail.package_file.storage
    client = storage.client if storage.same_endpoints else storage.client_external
    return client.presigned_get_object(
        bucket_name=storage.bucket,
        object_name=detail.package_file.name,
        expires=timedelta(minutes=10),
    )


def _stage_windows_package(target: PatchTarget, detail, *, timeout: int) -> str:
    """把私有桶中的手工补丁安全分发到目标机，返回目标机临时路径。"""
    from apps.patch_mgmt.models.patch import PATCH_PACKAGE_BUCKET

    filename = re.sub(r'[^A-Za-z0-9._-]', '_', detail.package_original_name or '')
    if not filename:
        filename = f'{detail.kb_number}{detail.package_extension}'
    staged_path = f'{WINDOWS_PATCH_STAGE_DIR}/{detail.patch_id}-{filename}'

    if target.source_type == PatchTargetSource.NODE_MGMT and target.node_id:
        result = Executor(target.node_id).download_to_local(
            bucket_name=PATCH_PACKAGE_BUCKET,
            file_key=detail.package_file.name,
            file_name=f'{detail.patch_id}-{filename}',
            target_path=WINDOWS_PATCH_STAGE_DIR,
            timeout=timeout,
            overwrite=True,
        )
        if not _is_success(_normalize_result(result)):
            raise RuntimeError(f'补丁文件分发失败: {_result_reason(_normalize_result(result))}')
        return staged_path

    mode = getattr(settings, 'PATCH_MGMT_WINDOWS_EXECUTION_MODE', 'executor')
    if mode == 'direct_winrm':
        if not settings.DEBUG:
            raise RuntimeError('direct_winrm 仅允许在 DEBUG=True 的本地环境使用')
        url = _short_lived_package_url(detail).replace("'", "''")
        command = (
            f"$dir='{WINDOWS_PATCH_STAGE_DIR}';$path='{staged_path}';"
            "New-Item -ItemType Directory -Path $dir -Force | Out-Null;"
            f"Invoke-WebRequest -Uri '{url}' -OutFile $path -UseBasicParsing;"
            "Write-Output 'package staged'"
        )
        result = _execute_winrm_direct(target, command, timeout=timeout)
        if not _is_success(result):
            raise RuntimeError(f'补丁文件下载失败: {_result_reason(result)}')
        return staged_path

    if mode != 'executor':
        raise RuntimeError(f'不支持的 Windows 执行模式: {mode}')
    executor = AnsibleExecutor(_get_ansible_executor_instance_id(target.cloud_region_id))
    task_id = f'patch-file-{target.id}-{uuid.uuid4().hex[:8]}'
    accepted = executor.playbook(
        host_credentials=_windows_host_credentials(target),
        files=[{'file_key': detail.package_file.name, 'name': f'{detail.patch_id}-{filename}'}],
        file_distribution={
            'bucket_name': PATCH_PACKAGE_BUCKET,
            'target_path': WINDOWS_PATCH_STAGE_DIR,
            'overwrite': True,
        },
        task_id=task_id,
        timeout=timeout,
    )
    accepted_task_id = (accepted.get('task_id') if isinstance(accepted, dict) else None) or task_id
    deadline = time.monotonic() + timeout
    while True:
        query = executor.task_query(accepted_task_id, timeout=min(timeout, 60))
        if isinstance(query, dict) and query.get('status') in {'success', 'failed', 'callback_failed'}:
            if query.get('status') != 'success':
                raise RuntimeError(f"补丁文件分发失败: {query.get('status')}")
            return staged_path
        if time.monotonic() >= deadline:
            raise TimeoutError('补丁文件分发超时')
        time.sleep(1)


def _normalize_result(result: Any) -> dict[str, Any]:
    '''把执行器返回归一化成字典。

    nats-executor 的 SSH/本地执行成功时，RPC 层可能直接返回 stdout 字符串；
    统一包装成 {'stdout': ..., 'stderr': '', 'exit_code': 0}，方便下游判断。
    '''
    if isinstance(result, dict):
        return result
    return {'stdout': str(result) if result is not None else '', 'stderr': '', 'exit_code': 0}


def _execute_command(
    target: PatchTarget,
    command: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    shell: Optional[str] = None,
    execution_id: Optional[str] = None,
    stream_log_topic: Optional[str] = None,
) -> dict[str, Any]:
    '''按目标来源和 OS 类型选择执行器并下发命令。'''
    if target.os_type == OSType.WINDOWS and target.source_type == PatchTargetSource.MANUAL:
        return _normalize_result(
            _execute_windows_manual(
                target, command, timeout=timeout, execution_id=execution_id, stream_log_topic=stream_log_topic
            )
        )

    instance_id = _get_nats_executor_instance_id(target)
    executor = Executor(instance_id)

    if target.source_type == PatchTargetSource.NODE_MGMT:
        return _normalize_result(
            executor.execute_local_stream(
                command,
                timeout=timeout,
                shell=shell,
                execution_id=execution_id,
                stream_log_topic=stream_log_topic,
            )
        )

    password = _decrypt_password(target.ssh_password)
    private_key = _read_ssh_key(target)
    passphrase = _decrypt_password(target.ssh_key_passphrase)
    return _normalize_result(
        executor.execute_ssh_stream(
            command,
            host=target.ip,
            username=target.ssh_user,
            password=password,
            private_key=private_key,
            passphrase=passphrase,
            port=target.ssh_port,
            timeout=timeout,
            execution_id=execution_id,
            stream_log_topic=stream_log_topic,
        )
    )


def _reboot_command(os_type: str) -> str:
    if os_type == OSType.WINDOWS:
        return 'shutdown /r /t 0 /f'
    return 'nohup shutdown -r +0 >/dev/null 2>&1 &'


_PKG_NAME_RE = re.compile(r'^[a-zA-Z0-9.+_-]+$')


def _manual_windows_install_command(detail, staged_path: str) -> str:
    """生成手工 MSU/CAB 的 SYSTEM 静默安装与临时文件清理命令。"""
    path = staged_path.replace("'", "''")
    expected_sha256 = (detail.package_sha256 or '').lower()
    if detail.package_extension == '.cab':
        executable = 'dism.exe'
        arguments = f'/Online /Add-Package /PackagePath:"{staged_path}" /Quiet /NoRestart'
    else:
        executable = 'wusa.exe'
        arguments = f'"{staged_path}" /quiet /norestart'
    arguments = arguments.replace("'", "''")
    job_id = uuid.uuid4().hex[:12]
    script_path = f'C:\\Windows\\Temp\\manual_patch_{job_id}.ps1'
    result_path = f'C:\\Windows\\Temp\\manual_patch_{job_id}.txt'
    task_name = f'Manual_Patch_{job_id}'
    inner_script = (
        "$ErrorActionPreference='Stop';"
        f"$path='{path}';"
        "try{"
        f"$actual=(Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower();"
        f"if($actual -ne '{expected_sha256}'){{throw 'SHA256 mismatch'}};"
        f"$proc=Start-Process -FilePath '{executable}' -ArgumentList '{arguments}' -Wait -PassThru;"
        "$code=$proc.ExitCode;"
        "$pending=(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') -or "
        "(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired');"
        "if($code -in @(0,3010,1641,2359301,2359302)){"
        "$rr=($code -in @(3010,1641,2359301)) -or (($code -eq 2359302) -and $pending);"
        '("InstallResult=2 RebootRequired={0}" -f $rr) | Out-File -FilePath \'__RP__\' -Encoding ascii -Force'
        "}else{(\"InstallError=installer exit code {0}\" -f $code) | Out-File -FilePath '__RP__' -Encoding ascii -Force}"
        "}catch{(\"InstallError={0}\" -f $_.Exception.Message) | Out-File -FilePath '__RP__' -Encoding ascii -Force}"
        "finally{Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue}"
    )
    return (
        "$ProgressPreference='SilentlyContinue';"
        f"$sp='{script_path}';"
        f"$rp='{result_path}';"
        f"$tn='{task_name}';"
        f"$pkg='{path}';"
        "if(Test-Path $rp){Remove-Item $rp -Force};"
        f"@'\n{inner_script}\n'@ -replace '__RP__',$rp | Out-File $sp -Encoding utf8 -Force;"
        "$action=New-ScheduledTaskAction -Execute 'powershell.exe' "
        "-Argument ('-NoProfile -ExecutionPolicy Bypass -File \"{0}\"' -f $sp);"
        "$trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(1);"
        "$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;"
        "Register-ScheduledTask -TaskName $tn -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null;"
        "Start-ScheduledTask -TaskName $tn;"
        "$w=0;while($w -lt 300 -and -not (Test-Path $rp)){Start-Sleep -Seconds 2;$w++};"
        "Unregister-ScheduledTask -TaskName $tn -Confirm:$false -ErrorAction SilentlyContinue;"
        "if(Test-Path $rp){Get-Content $rp;Remove-Item $rp -Force}else{Write-Output 'InstallResult= RebootRequired='};"
        "Remove-Item $sp,$pkg -Force -ErrorAction SilentlyContinue"
    )


def _install_commands(
    patches: list[Patch],
    os_type: str,
    *,
    manual_paths: Optional[dict[int, str]] = None,
) -> list[str]:
    '''根据目标主机包管理器和包名生成安装命令。

    Linux 安装命令不依赖补丁的 source_type，而是在目标主机上运行时检测
    可用的包管理器（dnf > yum > apt-get），生成一条自适应命令。
    这与 _dry_run_command / _assess_command 的检测模式一致。

    Windows 同步补丁与手工补丁都通过 Task Scheduler 以 SYSTEM 身份执行，
    避免 WinRM admin token 调用 WUA/WUSA 时被拒绝。
    '''
    if os_type == OSType.WINDOWS:
        manual_paths = manual_paths or {}
        manual_commands: list[str] = []
        kb_list = []
        for p in patches:
            try:
                detail = p.windows_detail
                if detail.package_file:
                    staged_path = manual_paths.get(p.pk)
                    if staged_path:
                        manual_commands.append(
                            _manual_windows_install_command(detail, staged_path)
                        )
                    continue
                kb = (detail.kb_number or '').strip()
                if kb:
                    kb_list.append(kb)
            except Exception:
                pass
        if not kb_list:
            return manual_commands or ['Write-Output no KB to install']
        kb_filter = ','.join([f"'{kb}'" for kb in kb_list])
        job_id = uuid.uuid4().hex[:12]
        # SYSTEM 任务和外层 PowerShell 都需要能访问这些路径
        script_path = f"C:\\Windows\\Temp\\wua_install_{job_id}.ps1"
        result_path = f"C:\\Windows\\Temp\\wua_install_{job_id}.txt"
        task_name = f"WUA_Install_{job_id}"

        # 内层脚本：在 SYSTEM 身份下运行 WUA 安装，结果写入 result_path
        inner_script = (
            "$ErrorActionPreference='Stop';"
            "$ProgressPreference='SilentlyContinue';"
            "try{"
            "$s=New-Object -ComObject Microsoft.Update.Session;"
            "$sr=$s.CreateUpdateSearcher();"
            '$r=$sr.Search("IsInstalled=0");'
            "$c=New-Object -ComObject Microsoft.Update.UpdateColl;"
            f"$kbs=@({kb_filter});"
            "foreach($u in $r.Updates){"
            "$matched=$false;"
            "foreach($kb in $u.KBArticleNumbers){if($kbs -contains $kb){$matched=$true;break}};"
            'if(-not $matched -and $u.Title -match "KB(\\d+)"){if($kbs -contains ("KB"+$matches[1])){$matched=$true}};'
            "if($matched){[void]$c.Add($u)}"
            "}"
            "if($c.Count -gt 0){"
            "$d=$s.CreateUpdateDownloader();$d.Updates=$c;$d.Download();"
            "$i=$s.CreateUpdateInstaller();$i.Updates=$c;"
            "$res=$i.Install();"
            "\"InstallResult={0} RebootRequired={1}\" -f $res.ResultCode,$res.RebootRequired | Out-File -FilePath '__RP__' -Encoding utf8 -Force"
            "}else{"
            "\"No matching updates found\" | Out-File -FilePath '__RP__' -Encoding utf8 -Force"
            "}"
            "}catch{"
            "\"InstallError=$($_.Exception.Message)\" | Out-File -FilePath '__RP__' -Encoding utf8 -Force"
            "}"
        )

        # 外层脚本：用 here-string 写脚本文件 -> 创建 SYSTEM 任务 -> 运行 -> 等待 -> 读结果 -> 清理
        # 不用 base64 编码，避免 pywinrm run_ps 二次编码后超过 Windows 命令行 8191 字符限制
        wua_command = (
            "$ProgressPreference='SilentlyContinue';"
            f"$sp='{script_path}';"
            f"$rp='{result_path}';"
            f"$tn='{task_name}';"
            "if(Test-Path $rp){Remove-Item $rp -Force};"
            # 用单引号 here-string 写脚本（字面量，不解析变量），替换结果路径占位符
            f"@'\n{inner_script}\n'@ -replace '__RP__',$rp | Out-File $sp -Encoding utf8 -Force;"
            # 创建并立即运行 SYSTEM 任务
            "schtasks /create /ru SYSTEM /tn $tn /tr \"powershell.exe -NoProfile -ExecutionPolicy Bypass -File $sp\" /sc once /st 00:00 /f 2>&1;"
            "schtasks /run /tn $tn 2>&1;"
            # 轮询等待任务完成，最多 10 分钟
            "$w=0;while($w -lt 300){Start-Sleep -Seconds 2;$q=schtasks /query /tn $tn /fo list /v;if($q -match 'Status\\s*:\\s*Ready'){break};$w++};"
            # 删除任务
            "schtasks /delete /tn $tn /f 2>&1;"
            # 输出结果；若结果文件不存在表示 SYSTEM 任务异常或超时
            "if(Test-Path $rp){Get-Content $rp;Remove-Item $rp -Force}else{Write-Output 'InstallResult= RebootRequired='};"
            # 清理脚本文件
            "Remove-Item $sp -Force -ErrorAction SilentlyContinue"
        )
        return [wua_command, *manual_commands]

    pkg_names: list[str] = []
    for p in patches:
        pkg_name = ''
        try:
            pkg_name = (p.linux_detail.pkg_name or '').strip()
        except Exception:
            pass
        if not pkg_name or not _PKG_NAME_RE.match(pkg_name):
            continue
        pkg_names.append(pkg_name)

    if not pkg_names:
        return ['echo no installable package mapped']

    quoted = ' '.join(shlex.quote(p) for p in pkg_names)
    return [
        f'if command -v dnf &>/dev/null; then dnf install -y {quoted}; '
        f'elif command -v yum &>/dev/null; then yum install -y {quoted}; '
        f'elif command -v apt-get &>/dev/null; then '
        f'DEBIAN_FRONTEND=noninteractive apt-get install -y {quoted}; '
        f'else echo "no supported package manager"; fi'
    ]


def _assess_command(os_type: str) -> str:
    if os_type == OSType.WINDOWS:
        return (
            '$ProgressPreference="SilentlyContinue";'
            '$s=New-Object -ComObject Microsoft.Update.Session;'
            '$sr=$s.CreateUpdateSearcher();'
            '$r=$sr.Search("IsInstalled=0");'
            '"===WUA===";'
            'foreach($u in $r.Updates){'
            '$kb=($u.KBArticleNumbers | Select-Object -First 1);'
            'if(-not $kb -and $u.Title -match "KB(\\d+)"){$kb="KB"+$matches[1]};'
            '"{0}|{1}|{2}" -f $kb,$u.MsrcSeverity,$u.Title'
            '}'
            '"===HOTFIX===";'
            'Get-HotFix | ForEach-Object { $_.HotFixID }'
        )
    return (
        'if command -v dnf &>/dev/null; then dnf --security check-update; '
        'elif command -v yum &>/dev/null; then yum --security check-update; '
        'elif command -v apt-get &>/dev/null; then apt-get -s upgrade; '
        'else echo "unsupported package manager"; fi || true'
    )


def _dry_run_command(os_type: str, pkg_names: list[str]) -> str:
    '''生成 dry-run 安装模拟命令，预览安装影响。'''
    if not pkg_names:
        return ''
    if os_type == OSType.WINDOWS:
        return ''  # Windows WUA 原子安装，不需要 dry-run
    pkgs = ' '.join(pkg_names)
    # 用 if/elif 检测包管理器，避免 || 链导致 dnf --assumeno (exit 1) 触发 fallback
    # dnf/yum --assumeno 退出码 1 表示用户取消，属于正常行为；追加 || true 确保退出码 0
    return (
        f'if command -v dnf &>/dev/null; then dnf update --assumeno {pkgs}; '
        f'elif command -v yum &>/dev/null; then yum update --assumeno {pkgs}; '
        f'elif command -v apt-get &>/dev/null; then apt-get -s install {pkgs}; '
        f'fi || true'
    )


def _parse_dry_run_output(stdout: str) -> dict:
    '''解析 dry-run 输出，提取安装影响信息。

    支持两种格式：
    - apt-get -s install: 含 "Inst pkg (new_ver)" 行和 "N upgraded, M newly installed" 摘要
    - dnf/yum update --assumeno: 含 "Upgrading:" / "Installing:" 段落和 "Upgrade N Package" 摘要
    '''
    upgrade = []
    install = []
    remove = []
    summary = ''

    lines = stdout.splitlines()

    # 优先尝试 apt 格式：Inst 行
    apt_inst_pattern = re.compile(r'^Inst\s+(\S+)\s+\[?([^\s\]]*)\]?\s*\(([^)]+)\)')
    apt_summary_pattern = re.compile(r'(\d+)\s+upgraded.*?(\d+)\s+newly installed.*?(\d+)\s+to remove')
    has_apt = False
    for line in lines:
        m = apt_inst_pattern.match(line)
        if m:
            has_apt = True
            pkg = m.group(1)
            old_ver = m.group(2).strip()
            new_ver = m.group(3).strip()
            if old_ver:
                upgrade.append(f'{pkg} ({old_ver} -> {new_ver})')
            else:
                install.append(f'{pkg} ({new_ver})')
        m2 = apt_summary_pattern.search(line)
        if m2:
            summary = line.strip()
            has_apt = True

    if has_apt:
        return {
            'upgrade': upgrade,
            'install': install,
            'remove': remove,
            'summary': summary or f'{len(upgrade)} 个升级, {len(install)} 个新安装, {len(remove)} 个移除',
            'raw_output': stdout[:2000],
        }

    # 尝试 yum/dnf 格式：段落式
    current_section = None
    yum_pkg_pattern = re.compile(r'^\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)')
    for line in lines:
        low = line.strip().lower()
        if low == 'upgrading:':
            current_section = 'upgrade'
            continue
        elif low == 'installing:':
            current_section = 'install'
            continue
        elif low == 'removing:':
            current_section = 'remove'
            continue
        elif low.startswith('transaction summary'):
            current_section = None
            continue

        if current_section and not line.startswith('='):
            m = yum_pkg_pattern.match(line)
            if m:
                pkg_name = m.group(1)
                version = m.group(3)
                if current_section == 'upgrade':
                    upgrade.append(f'{pkg_name} ({version})')
                elif current_section == 'install':
                    install.append(f'{pkg_name} ({version})')
                elif current_section == 'remove':
                    remove.append(f'{pkg_name} ({version})')

        if 'upgrade' in low and 'package' in low:
            summary = line.strip()
        elif 'install' in low and 'package' in low:
            summary = line.strip()

    if upgrade or install or remove:
        if not summary:
            summary = f'{len(upgrade)} 个升级, {len(install)} 个新安装, {len(remove)} 个移除'
        return {
            'upgrade': upgrade,
            'install': install,
            'remove': remove,
            'summary': summary,
            'raw_output': stdout[:2000],
        }

    # 无法解析时返回原始输出
    return {
        'upgrade': [],
        'install': [],
        'remove': [],
        'summary': '',
        'raw_output': stdout[:2000],
    }


def _collect_install_impact(
    target: PatchTarget,
    missing_requirements: list,
    execution_id: str,
) -> dict[int, dict]:
    '''对缺失的补丁跑 dry-run，收集安装影响信息。

    Returns: {requirement_id: install_impact_dict}
    '''
    if target.os_type == OSType.WINDOWS:
        return {}

    # 收集所有缺失补丁的包名，批量跑一次 dry-run
    pkg_names = []
    for req in missing_requirements:
        try:
            pkg_name = req.patch.linux_detail.pkg_name
            if pkg_name:
                pkg_names.append(pkg_name)
        except Exception:
            pass

    if not pkg_names:
        return {}

    # 批量跑一次 dry-run
    command = _dry_run_command(target.os_type, pkg_names)
    if not command:
        return {}

    try:
        result = _execute_command(target, command, timeout=30, execution_id=execution_id)
        stdout = result.get('stdout') or ''
        impact = _parse_dry_run_output(stdout)
    except Exception as exc:  # noqa: BLE001
        logger.warning('dry-run 失败 target=%s: %s', target.id, exc)
        impact = {'raw_output': '', 'summary': '', 'error': str(exc)[:200]}

    # 所有缺失补丁共享同一个 dry-run 结果
    return {req.id: impact for req in missing_requirements}


def _record_host_start(host: GovernanceTaskHost, stage: str) -> None:
    from apps.patch_mgmt.config import get_stage_timeout

    now = timezone.now()
    host.stage = stage
    host.stage_color = 'processing'
    host.started_at = host.started_at or now
    host.stage_started_at = now
    host.stage_deadline_at = now + timedelta(seconds=get_stage_timeout(host.task.task_type))
    host.last_heartbeat_at = now
    host.save(update_fields=[
        'stage', 'stage_color', 'started_at', 'stage_started_at',
        'stage_deadline_at', 'last_heartbeat_at', 'updated_at',
    ])


def _claim_waiting_host(host: GovernanceTaskHost, stage: str) -> bool:
    '''原子领取待执行主机，避免与取消操作竞态。'''
    from apps.patch_mgmt.config import get_stage_timeout

    now = timezone.now()
    claimed = GovernanceTaskHost.objects.filter(pk=host.pk, stage='waiting').update(
        stage=stage,
        stage_color='processing',
        started_at=now,
        stage_started_at=now,
        stage_deadline_at=now + timedelta(seconds=get_stage_timeout(host.task.task_type)),
        last_heartbeat_at=now,
        updated_at=now,
    )
    if claimed:
        host.refresh_from_db()
    return bool(claimed)


def _record_host_result(
    host: GovernanceTaskHost,
    *,
    stage: str,
    stage_color: str,
    exit_code: Optional[int] = None,
    reason: str = '',
    failed_stage: str = '',
    error_code: str = '',
    can_retry: bool = False,
) -> None:
    host.stage = stage
    host.stage_color = stage_color
    host.exit_code = exit_code
    host.reason = reason
    host.failed_stage = failed_stage
    host.error_code = error_code
    host.can_retry = can_retry
    host.save(update_fields=[
        'stage', 'stage_color', 'exit_code', 'reason',
        'failed_stage', 'error_code', 'can_retry', 'updated_at',
    ])


def _format_log_entry(command: str, result: Any) -> str:
    '''把单条命令及其执行结果格式化成文本日志。'''
    ts = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = [f'[{ts}] $ {command}']
    if isinstance(result, dict):
        if result.get('stdout'):
            lines.append(f'[{ts}] stdout:\n{result["stdout"]}')
        if result.get('stderr'):
            lines.append(f'[{ts}] stderr:\n{result["stderr"]}')
        if result.get('error'):
            lines.append(f'[{ts}] error: {result["error"]}')
        lines.append(f'[{ts}] exit_code: {result.get("exit_code")}')
    else:
        lines.append(f'[{ts}] result:\n{str(result)}')
    return '\n'.join(lines) + '\n'


def _append_host_log(host: GovernanceTaskHost, command: str, result: Any) -> None:
    '''追加命令执行日志到 GovernanceTaskHost.log。'''
    entry = _format_log_entry(command, result)
    host.log = f'{host.log}\n{entry}'.strip()
    host.save(update_fields=['log', 'updated_at'])


def _is_assess_success(result: dict[str, Any]) -> bool:
    '''判断 assess 命令是否成功。

    yum/dnf check-update 在有可用更新时返回 100，这属于正常结果而非失败；
    apt-get -s upgrade 成功返回 0。因此 exit_code 为 0 或 100 均视为成功，
    前提是没有执行器层面的 error。
    '''
    if not isinstance(result, dict):
        return False
    if result.get('error'):
        return False
    code = result.get('exit_code')
    if code is not None and int(code) not in (0, 100):
        return False
    return True


def _update_binding_after_assess(
    target: PatchTarget,
    success: bool,
    result: dict[str, Any],
    execution_id: str = '',
) -> None:
    '''评估完成后把结果写回 HostBaselineBinding 与 HostComplianceSnapshot。'''
    binding = getattr(target, 'baseline_binding', None)
    if binding is None:
        return
    try:
        task_id = int(str(execution_id).split(':', 1)[0])
    except (TypeError, ValueError):
        task_id = 0
    task = GovernanceTask.objects.filter(pk=task_id).first() if task_id else None
    if task and task.status == GovernanceTaskStatus.CANCELLED:
        logger.info('忽略已取消评估结果 task=%s target=%s', task.id, target.id)
        return
    if task and task.task_type == GovernanceTaskType.ASSESS and task.risk_snapshot:
        snapshot = task.risk_snapshot[0]
        expected_baseline_id = int(snapshot.get('baseline_id') or 0)
        expected_signature = str(snapshot.get('requirements_signature') or '')
        expected_bindings_signature = str(snapshot.get('bindings_signature') or '')
        binding.refresh_from_db(fields=['baseline_id'])
        current_requirements = binding.baseline.requirements.order_by('id').values_list(
            'id', 'patch_id', 'updated_at'
        )
        current_signature = '|'.join(
            f'{requirement_id}:{patch_id}:{updated_at.isoformat()}'
            for requirement_id, patch_id, updated_at in current_requirements
        )
        current_bindings_signature = '|'.join(
            f'{binding_id}:{target_id}'
            for binding_id, target_id in binding.baseline.host_bindings.order_by('id').values_list(
                'id', 'target_id'
            )
        )
        if (
            binding.baseline_id != expected_baseline_id
            or (expected_signature and current_signature != expected_signature)
            or (
                expected_bindings_signature
                and current_bindings_signature != expected_bindings_signature
            )
        ):
            logger.info(
                '忽略已失效评估结果 task=%s target=%s baseline=%s',
                task.id,
                target.id,
                expected_baseline_id,
            )
            return
    now = timezone.now()
    binding.last_evaluated_at = now

    if not success:
        binding.compliance_status = ComplianceStatus.FAILED
        binding.missing_count = 0
        binding.save(update_fields=['compliance_status', 'missing_count', 'last_evaluated_at', 'updated_at'])
        return

    stdout = result.get('stdout') or '' if isinstance(result, dict) else str(result)
    try:
        requirements = list(
            binding.baseline.requirements.select_related('patch__linux_detail', 'patch__windows_detail')
        )
        assessments = assess_requirements(target.os_type, stdout, requirements)
    except Exception as exc:  # noqa: BLE001
        logger.exception('解析目标 %s 评估输出失败: %s', target.id, exc)
        binding.compliance_status = ComplianceStatus.FAILED
        binding.missing_count = 0
        binding.save(update_fields=['compliance_status', 'missing_count', 'last_evaluated_at', 'updated_at'])
        return

    HostComplianceSnapshot.objects.filter(binding=binding).delete()
    snapshots = []
    missing_count = 0
    missing_reqs = []
    for req in requirements:
        assessment = assessments.get(req.id)
        if assessment is None:
            continue
        if not assessment.satisfied:
            missing_count += 1
            missing_reqs.append(req)

    # 对缺失补丁跑 dry-run，收集安装影响
    install_impacts = {}
    if missing_reqs and success:
        try:
            install_impacts = _collect_install_impact(target, missing_reqs, execution_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning('收集安装影响失败 target=%s: %s', target.id, exc)

    for req in requirements:
        assessment = assessments.get(req.id)
        if assessment is None:
            continue
        evidence = dict(assessment.evidence) if assessment.evidence else {}
        if req.id in install_impacts:
            evidence['install_impact'] = install_impacts[req.id]
        snapshots.append(
            HostComplianceSnapshot(
                binding=binding,
                requirement=req,
                satisfied=assessment.satisfied,
                evidence=evidence,
                reason=assessment.reason,
                evaluated_at=now,
            )
        )
    HostComplianceSnapshot.objects.bulk_create(snapshots)

    binding.missing_count = missing_count
    binding.compliance_status = (
        ComplianceStatus.COMPLIANT if missing_count == 0 else ComplianceStatus.NON_COMPLIANT
    )
    binding.save(update_fields=['compliance_status', 'missing_count', 'last_evaluated_at', 'updated_at'])


def _is_success(result: dict[str, Any]) -> bool:
    '''粗略判断执行器返回是否成功。'''
    if not isinstance(result, dict):
        return False
    if result.get('error'):
        return False
    code = result.get('exit_code')
    if code is not None and int(code) != 0:
        return False
    return True


def _result_reason(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result)[:512]
    if result.get('error'):
        return str(result['error'])[:512]
    stderr = result.get('stderr') or ''
    stdout = result.get('stdout') or ''
    return (stderr or stdout or str(result))[:512]


def _is_timeout_value(value: Any) -> bool:
    text = str(value or '').lower()
    return any(hint in text for hint in ('timed out', 'timeout', 'time limit exceeded'))


def _is_timeout_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return any(
        _is_timeout_value(result.get(key))
        for key in ('error', 'stderr', 'stdout')
    )


_INSTALL_RESULT_RE = re.compile(r'InstallResult=(\d)')
_REBOOT_REQUIRED_RE = re.compile(r'RebootRequired=(True|False)')
_LINUX_REBOOT_REQUIRED_RE = re.compile(r'RebootRequired=(True|False|Unknown)')
_REBOOT_METHOD_RE = re.compile(r'RebootMethod=([^\r\n]+)')
_REBOOT_DETAIL_RE = re.compile(r'RebootDetail=([^\r\n]+)')

_INSTALL_RESULT_MESSAGES = {
    '0': '安装未启动',
    '1': '安装进行中（未完成）',
    '4': 'WUA 安装失败',
    '5': 'WUA 安装已中止',
}


def _parse_windows_install_result(result: dict[str, Any]) -> tuple[bool, str, Optional[bool]]:
    '''解析 Windows WUA 安装命令输出。

    返回 (是否成功, 原因, 是否需要重启)。
    仅当 InstallResult 为 2 或 3 时认为安装成功；其它码值、空值、
    stderr 异常或无法识别的输出均视为失败。
    '''
    if not isinstance(result, dict):
        return False, str(result)[:512], False

    stdout = str(result.get('stdout') or '')
    stderr = str(result.get('stderr') or '')

    if 'No matching updates found' in stdout:
        return False, '未找到匹配的更新，KB 号可能不存在于 Windows Update', False

    install_error_match = re.search(r'InstallError=(.+)', stdout)
    if install_error_match:
        return False, f'WUA 安装异常：{install_error_match.group(1)[:256]}', False

    # stdout 有明确 InstallResult 码值时以 stdout 为准（schtasks 的 WARNING 不影响判断）
    match = _INSTALL_RESULT_RE.search(stdout)
    if match:
        code = match.group(1)
        if code in ('2', '3'):
            reboot_match = _REBOOT_REQUIRED_RE.search(stdout)
            reboot_required = None if reboot_match is None else reboot_match.group(1) == 'True'
            reason = '安装成功完成' if code == '2' else '安装完成（含非关键错误）'
            return True, reason, reboot_required
        reason = _INSTALL_RESULT_MESSAGES.get(code, f'WUA 返回未知结果码 {code}')
        return False, reason, False

    # stdout 没有明确 InstallResult，回退到 stderr 检查
    if 'Access is denied' in stderr:
        return False, f'权限不足：{stderr[:256]}', False

    if stderr.strip():
        return False, f'安装异常：{stderr[:256]}', False

    return False, f'WUA 输出异常，无法解析 InstallResult：{stdout[:256]}', False


def _linux_reboot_check_command() -> str:
    '''生成 Linux 安装后重启需求探测命令。

    输出统一的 RebootRequired/RebootMethod/RebootDetail 三行协议，并始终以
    退出码 0 返回，避免把“需要重启”(needs-restarting rc=1)误判为执行失败。
    '''
    return (
        'if command -v dnf >/dev/null 2>&1; then '
        'if ! dnf -q needs-restarting --help >/dev/null 2>&1; then '
        'printf "RebootRequired=Unknown\\nRebootMethod=dnf\\nRebootDetail=needs-restarting unavailable\\n"; '
        'else out="$(dnf -q needs-restarting -r 2>&1)"; rc=$?; '
        'printf "%s\\n" "$out"; '
        'if [ "$rc" -eq 0 ]; then printf "RebootRequired=False\\nRebootMethod=dnf\\n"; '
        'elif [ "$rc" -eq 1 ]; then printf "RebootRequired=True\\nRebootMethod=dnf\\n"; '
        'else printf "RebootRequired=Unknown\\nRebootMethod=dnf\\nRebootDetail=exit code %s\\n" "$rc"; fi; fi; '
        'elif command -v yum >/dev/null 2>&1; then '
        'if command -v needs-restarting >/dev/null 2>&1; then '
        'out="$(needs-restarting -r 2>&1)"; rc=$?; '
        'elif yum -q needs-restarting --help >/dev/null 2>&1; then '
        'out="$(yum -q needs-restarting -r 2>&1)"; rc=$?; '
        'else printf "RebootRequired=Unknown\\nRebootMethod=yum\\nRebootDetail=needs-restarting unavailable\\n"; exit 0; fi; '
        'printf "%s\\n" "$out"; '
        'if [ "$rc" -eq 0 ]; then printf "RebootRequired=False\\nRebootMethod=yum\\n"; '
        'elif [ "$rc" -eq 1 ]; then printf "RebootRequired=True\\nRebootMethod=yum\\n"; '
        'else printf "RebootRequired=Unknown\\nRebootMethod=yum\\nRebootDetail=exit code %s\\n" "$rc"; fi; '
        'elif command -v apt-get >/dev/null 2>&1; then '
        'if [ -e /run/reboot-required ] || [ -e /var/run/reboot-required ]; then '
        'printf "RebootRequired=True\\nRebootMethod=apt\\n"; '
        'elif [ -x /usr/share/update-notifier/notify-reboot-required ]; then '
        'printf "RebootRequired=False\\nRebootMethod=apt\\n"; '
        'else printf "RebootRequired=Unknown\\nRebootMethod=apt\\nRebootDetail=update-notifier unavailable\\n"; fi; '
        'else printf "RebootRequired=Unknown\\nRebootMethod=unknown\\nRebootDetail=unsupported package manager\\n"; fi; '
        'exit 0'
    )


def _windows_reboot_check_command() -> str:
    '''生成 Windows 只读重启需求探测命令。'''
    return (
        '$p=$false;'
        'if(Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending"){$p=$true};'
        'if(Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired"){$p=$true};'
        '$s=Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager" '
        '-Name PendingFileRenameOperations -ErrorAction SilentlyContinue;'
        'if($null -ne $s){$p=$true};'
        '"RebootRequired={0}`nRebootMethod=windows" -f $p'
    )


def _install_activity_command(os_type: str) -> str:
    '''返回仅查询安装进程状态的只读命令。'''
    if os_type == OSType.WINDOWS:
        return (
            '$running=Get-ScheduledTask -TaskName "WUA_Install_*" -ErrorAction SilentlyContinue '
            '| Where-Object {$_.State -eq "Running"};'
            '"InstallProcessRunning={0}" -f [bool]$running'
        )
    return (
        'if pgrep -x dnf >/dev/null || pgrep -x yum >/dev/null || '
        'pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null || '
        'pgrep -x rpm >/dev/null; then echo InstallProcessRunning=True; '
        'else echo InstallProcessRunning=False; fi'
    )


def _parse_install_activity(result: dict[str, Any]) -> Optional[bool]:
    if not _is_success(result):
        return None
    match = re.search(r'InstallProcessRunning=(True|False)', str(result.get('stdout') or ''))
    return None if match is None else match.group(1) == 'True'


def _boot_marker_command(os_type: str) -> str:
    if os_type == OSType.WINDOWS:
        return '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString("o")'
    return 'cat /proc/sys/kernel/random/boot_id'


def _read_boot_marker(
    target: PatchTarget,
    execution_id: str,
    timeout: int = 30,
) -> str:
    '''读取目标机当前启动标识；失败返回空串，不执行任何写操作。'''
    command = _boot_marker_command(target.os_type)
    try:
        result = _execute_command(
            target,
            command,
            timeout=timeout,
            execution_id=execution_id,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, SoftTimeLimitExceeded):
            raise
        logger.warning('读取启动标识失败 target=%s: %s', target.id, exc)
        return ''
    if not _is_success(result):
        return ''
    lines = str(result.get('stdout') or '').strip().splitlines()
    return lines[0][:128] if lines else ''


def _parse_linux_reboot_check_result(result: dict[str, Any]) -> tuple[Optional[bool], str]:
    '''解析 Linux 重启探测协议，返回 (是否需要重启, 说明)。'''
    if not isinstance(result, dict):
        return None, str(result)[:512]
    if result.get('error') or int(result.get('exit_code') or 0) != 0:
        return None, _result_reason(result)

    stdout = str(result.get('stdout') or '')
    match = _LINUX_REBOOT_REQUIRED_RE.search(stdout)
    method_match = _REBOOT_METHOD_RE.search(stdout)
    detail_match = _REBOOT_DETAIL_RE.search(stdout)
    method = method_match.group(1).strip() if method_match else 'unknown'
    detail = detail_match.group(1).strip() if detail_match else ''
    if not match:
        return None, f'{method} 重启探测输出无法解析：{stdout[:256]}'

    value = match.group(1)
    reason = f'{method}: {detail}' if detail else method
    if value == 'True':
        return True, reason
    if value == 'False':
        return False, reason
    return None, reason


def _execute_reboot(target: PatchTarget, host: GovernanceTaskHost, execution_id: str, timeout: int) -> None:
    _record_host_start(host, 'rebooting')
    host.boot_marker_before = _read_boot_marker(target, execution_id)
    host.save(update_fields=['boot_marker_before', 'updated_at'])
    command = _reboot_command(target.os_type)
    try:
        result = _execute_command(
            target,
            command,
            timeout=timeout,
            execution_id=execution_id,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, SoftTimeLimitExceeded):
            raise
        if _is_timeout_value(exc):
            handle_host_execution_timeout(host.task_id, target.id)
            _append_host_log(host, command, {'error': str(exc), 'exit_code': None})
            return
        logger.exception('任务 %s 目标 %s 重启执行异常', host.task_id, target.id)
        _record_host_result(
            host,
            stage='reboot_failed',
            stage_color='error',
            reason=f'执行器调用异常: {exc}',
            failed_stage='reboot',
            can_retry=True,
        )
        _append_host_log(host, command, {'error': str(exc), 'exit_code': None})
        return

    _append_host_log(host, command, result)

    if _is_timeout_result(result):
        handle_host_execution_timeout(host.task_id, target.id)
        return

    if _is_success(result):
        _record_host_result(
            host,
            stage='pending_reboot',
            stage_color='warning',
            exit_code=result.get('exit_code') or 0,
            reason='重启命令已下发，等待主机恢复',
        )
    else:
        _record_host_result(
            host,
            stage='reboot_failed',
            stage_color='error',
            exit_code=result.get('exit_code'),
            reason=_result_reason(result),
            failed_stage='reboot',
            can_retry=True,
        )


def _execute_install(
    target: PatchTarget,
    host: GovernanceTaskHost,
    patch_ids: list[int],
    execution_id: str,
    timeout: int,
) -> None:
    _record_host_start(host, 'installing')
    patches = list(
        Patch.objects.filter(pk__in=patch_ids).select_related('windows_detail', 'linux_detail')
    )
    manual_paths: dict[int, str] = {}
    staging_errors: list[str] = []
    if target.os_type == OSType.WINDOWS:
        for patch in patches:
            try:
                detail = patch.windows_detail
                if detail.package_file:
                    manual_paths[patch.id] = _stage_windows_package(
                        target, detail, timeout=timeout
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    '任务 %s 目标 %s 手工补丁 %s 分发失败',
                    host.task_id,
                    target.id,
                    patch.id,
                )
                reason = f'{patch.title} 分发失败: {exc}'
                staging_errors.append(reason)
                _append_host_log(
                    host,
                    f'分发手工补丁 {patch.title}',
                    {'error': str(exc), 'exit_code': None},
                )
    commands = _install_commands(
        patches,
        target.os_type,
        manual_paths=manual_paths if target.os_type == OSType.WINDOWS else None,
    )
    if staging_errors and commands == ['Write-Output no KB to install']:
        commands = []
    if staging_errors and not commands:
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            reason='; '.join(staging_errors)[:1024],
            failed_stage='install',
            can_retry=True,
        )
        return

    last_result = {}
    overall_reasons: list[str] = list(staging_errors)
    windows_results: list[tuple[bool, str, Optional[bool]]] = []
    execution_failed = bool(staging_errors)
    for command in commands:
        try:
            last_result = _execute_command(
                target,
                command,
                timeout=timeout,
                execution_id=execution_id,
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, SoftTimeLimitExceeded):
                raise
            if _is_timeout_value(exc):
                handle_host_execution_timeout(host.task_id, target.id)
                _append_host_log(host, command, {'error': str(exc), 'exit_code': None})
                return
            logger.exception('任务 %s 目标 %s 安装执行异常', host.task_id, target.id)
            overall_reasons.append(f'执行器异常: {exc}')
            execution_failed = True
            _append_host_log(host, command, {'error': str(exc), 'exit_code': None})
            continue
        _append_host_log(host, command, last_result)
        if _is_timeout_result(last_result):
            handle_host_execution_timeout(host.task_id, target.id)
            return
        overall_reasons.append(_result_reason(last_result))
        if target.os_type == OSType.WINDOWS:
            # SYSTEM 计划任务的安装结果由 stdout 协议返回；外层 WinRM
            # 可能保留非零退出码，不能先于协议结果判定失败。
            parsed_result = _parse_windows_install_result(last_result)
            windows_results.append(parsed_result)
            if not parsed_result[0]:
                execution_failed = True
            continue
        if not _is_success(last_result):
            execution_failed = True
            break

    if target.os_type == OSType.WINDOWS:
        failed_results = [item for item in windows_results if not item[0]]
        if execution_failed or failed_results or not windows_results:
            reasons = [item[1] for item in failed_results] or overall_reasons
            reason = '; '.join(reasons)[:1024] or 'Windows 补丁安装失败'
            _record_host_result(
                host,
                stage='failed',
                stage_color='error',
                exit_code=last_result.get('exit_code') if isinstance(last_result, dict) else None,
                reason=reason,
                failed_stage='install',
                can_retry='未找到匹配的更新' not in reason,
            )
            return
        reboot_values = [item[2] for item in windows_results]
        reboot_required = True if True in reboot_values else (None if None in reboot_values else False)
        _record_install_reboot_result(
            host,
            reboot_required,
            '; '.join(item[1] for item in windows_results),
            0,
        )
        return

    if _is_success(last_result):
        if target.os_type != OSType.WINDOWS:
            check_command = _linux_reboot_check_command()
            try:
                check_result = _execute_command(
                    target,
                    check_command,
                    timeout=min(timeout, 300),
                    execution_id=execution_id,
                )
                _append_host_log(host, check_command, check_result)
                reboot_required, check_reason = _parse_linux_reboot_check_result(check_result)
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, SoftTimeLimitExceeded):
                    raise
                logger.exception('任务 %s 目标 %s 重启需求探测异常', host.task_id, target.id)
                _append_host_log(host, check_command, {'error': str(exc), 'exit_code': None})
                reboot_required, check_reason = None, f'执行器调用异常: {exc}'
            _record_install_reboot_result(
                host, reboot_required, check_reason, last_result.get('exit_code') or 0,
            )
    else:
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            exit_code=last_result.get('exit_code') if isinstance(last_result, dict) else None,
            reason='; '.join(overall_reasons)[:1024],
            failed_stage='install',
            can_retry=True,
        )


def _record_install_reboot_result(
    host: GovernanceTaskHost,
    reboot_required: Optional[bool],
    check_reason: str,
    exit_code: int,
) -> None:
    '''按安装后的重启探测三态回写主机阶段。'''
    if reboot_required is True:
        _record_host_result(
            host,
            stage='pending_reboot',
            stage_color='warning',
            exit_code=exit_code,
            reason=f'安装完成，检测到需要重启（{check_reason}）',
        )
        return
    if reboot_required is False:
        _record_host_result(
            host,
            stage='completed',
            stage_color='success',
            exit_code=exit_code,
            reason=f'安装完成，无需重启（{check_reason}）',
        )
        return
    _record_host_result(
        host,
        stage='pending_reboot',
        stage_color='warning',
        exit_code=exit_code,
        reason=f'安装完成，但无法判断是否需要重启，已转为待重启（{check_reason}）',
        failed_stage='reboot_check',
        error_code='reboot_requirement_unknown',
    )


def _execute_assess(target: PatchTarget, host: GovernanceTaskHost, execution_id: str, timeout: int) -> None:
    _record_host_start(host, 'scanning')
    command = _assess_command(target.os_type)
    try:
        result = _execute_command(
            target,
            command,
            timeout=timeout,
            execution_id=execution_id,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, SoftTimeLimitExceeded):
            raise
        logger.exception('任务 %s 目标 %s 评估执行异常', host.task_id, target.id)
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            reason=f'执行器调用异常: {exc}',
            failed_stage='assess',
            can_retry=True,
        )
        _append_host_log(host, command, {'error': str(exc), 'exit_code': None})
        _update_binding_after_assess(target, success=False, result={}, execution_id=execution_id)
        return

    _append_host_log(host, command, result)

    if _is_assess_success(result):
        _record_host_result(
            host,
            stage='completed',
            stage_color='success',
            exit_code=result.get('exit_code') or 0,
            reason=_result_reason(result),
        )
        _update_binding_after_assess(target, success=True, result=result, execution_id=execution_id)
    else:
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            exit_code=result.get('exit_code'),
            reason=_result_reason(result),
            failed_stage='assess',
            can_retry=True,
        )
        _update_binding_after_assess(target, success=False, result=result, execution_id=execution_id)


def reconcile_install_host(
    task: GovernanceTask,
    host: GovernanceTaskHost,
    target: PatchTarget,
) -> str:
    '''只读核验安装结果，返回 installed/running/not_installed/unknown。'''
    execution_id = f'reconcile:{task.id}:{target.id}'
    assess_command = _assess_command(target.os_type)
    try:
        assess_result = _execute_command(
            target,
            assess_command,
            timeout=300,
            execution_id=execution_id,
        )
        _append_host_log(host, assess_command, assess_result)
    except Exception as exc:  # noqa: BLE001
        logger.warning('安装结果核验评估失败 task=%s target=%s: %s', task.id, target.id, exc)
        return 'unknown'

    if not _is_assess_success(assess_result):
        return 'unknown'

    binding = getattr(target, 'baseline_binding', None)
    if binding is None:
        return 'unknown'
    requirements = list(
        binding.baseline.requirements.filter(patch_id__in=task.patch_list or [])
        .select_related('patch__linux_detail', 'patch__windows_detail')
    )
    if not requirements:
        return 'unknown'

    try:
        assessments = assess_requirements(
            target.os_type,
            str(assess_result.get('stdout') or ''),
            requirements,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('安装结果核验解析失败 task=%s target=%s: %s', task.id, target.id, exc)
        return 'unknown'

    if all(assessments.get(req.id) and assessments[req.id].satisfied for req in requirements):
        reboot_command = (
            _windows_reboot_check_command()
            if target.os_type == OSType.WINDOWS
            else _linux_reboot_check_command()
        )
        try:
            reboot_result = _execute_command(
                target,
                reboot_command,
                timeout=300,
                execution_id=execution_id,
            )
            _append_host_log(host, reboot_command, reboot_result)
            reboot_required, reboot_reason = _parse_linux_reboot_check_result(reboot_result)
        except Exception as exc:  # noqa: BLE001
            logger.warning('安装结果核验重启判断失败 task=%s target=%s: %s', task.id, target.id, exc)
            reboot_required, reboot_reason = None, f'执行器调用异常: {exc}'
        _record_install_reboot_result(host, reboot_required, reboot_reason, 0)
        return 'installed'

    activity_command = _install_activity_command(target.os_type)
    try:
        activity_result = _execute_command(
            target,
            activity_command,
            timeout=30,
            execution_id=execution_id,
        )
        _append_host_log(host, activity_command, activity_result)
        activity = _parse_install_activity(activity_result)
    except Exception as exc:  # noqa: BLE001
        logger.warning('安装进程核验失败 task=%s target=%s: %s', task.id, target.id, exc)
        activity = None

    if activity is True:
        return 'running'
    if activity is False:
        return 'not_installed'
    return 'unknown'


def reconcile_reboot_host(
    task: GovernanceTask,
    host: GovernanceTaskHost,
    target: PatchTarget,
) -> str:
    '''只读核验重启结果，绝不再次下发重启命令。'''
    if not _check_host_reachable(target):
        return 'running'
    current_marker = _read_boot_marker(
        target,
        execution_id=f'reconcile-reboot:{task.id}:{target.id}',
    )
    if not host.boot_marker_before or not current_marker:
        return 'unknown'
    if current_marker == host.boot_marker_before:
        return 'running'
    _record_host_result(
        host,
        stage='pending_reboot',
        stage_color='warning',
        reason='重启超时核验确认启动标识已变化，等待自动验证',
        can_retry=False,
    )
    return 'rebooted'


def reconcile_host_result(task_id: int, target_id: int) -> None:
    '''编排单台主机超时结果核验；只读探测，不重复安装或重启。'''
    from apps.patch_mgmt.config import RECONCILE_INTERVAL
    from apps.patch_mgmt.tasks import reconcile_governance_host

    try:
        task = GovernanceTask.objects.get(pk=task_id)
        target = PatchTarget.objects.get(pk=target_id)
    except (GovernanceTask.DoesNotExist, PatchTarget.DoesNotExist):
        logger.warning('结果核验对象不存在 task=%s target=%s', task_id, target_id)
        return

    with transaction.atomic():
        host = GovernanceTaskHost.objects.select_for_update().filter(
            task=task,
            target_id=target_id,
        ).first()
        if host is None or host.stage != 'reconciling':
            return
        host.reconcile_attempts += 1
        host.last_heartbeat_at = timezone.now()
        host.save(update_fields=['reconcile_attempts', 'last_heartbeat_at', 'updated_at'])

    if task.task_type == GovernanceTaskType.INSTALL:
        result = reconcile_install_host(task, host, target)
    elif task.task_type == GovernanceTaskType.REBOOT:
        result = reconcile_reboot_host(task, host, target)
    else:
        result = 'unknown'

    host.refresh_from_db()
    if host.stage != 'reconciling':
        if _finalize_task_status(task):
            _run_terminal_followups(task)
        return

    now = timezone.now()
    if result == 'not_installed':
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            reason='超时核验确认补丁未安装，且未检测到安装进程',
            failed_stage='install',
            error_code='install_not_completed',
            can_retry=True,
        )
    elif result in {'running', 'unknown'} and host.reconcile_deadline_at and now < host.reconcile_deadline_at:
        reconcile_governance_host.apply_async(
            args=[task.id, target_id],
            countdown=RECONCILE_INTERVAL,
        )
        return
    else:
        _record_host_result(
            host,
            stage='pending_confirmation',
            stage_color='warning',
            reason='结果核验窗口已结束，仍无法确认实际执行结果，请人工确认',
            failed_stage=task.task_type,
            error_code=f'{task.task_type}_result_unknown',
            can_retry=False,
        )

    if _finalize_task_status(task):
        _run_terminal_followups(task)


def handle_host_execution_timeout(task_id: int, target_id: int) -> None:
    '''收口 Celery soft limit；有副作用阶段转核验，无副作用阶段转可重试失败。'''
    from apps.patch_mgmt.config import RECONCILE_TIMEOUT
    from apps.patch_mgmt.tasks import reconcile_governance_host

    now = timezone.now()
    with transaction.atomic():
        host = GovernanceTaskHost.objects.select_for_update().select_related('task').filter(
            task_id=task_id,
            target_id=target_id,
        ).first()
        if host is None or host.stage not in {'scanning', 'installing', 'rebooting'}:
            return
        task = host.task
        host.timeout_reason = f'{task.get_task_type_display()}任务触发执行器软超时'
        host.reason = host.timeout_reason
        host.last_heartbeat_at = now
        if task.task_type in (GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT):
            host.stage = 'reconciling'
            host.stage_color = 'processing'
            host.error_code = f'{task.task_type}_timeout_unknown'
            host.reconcile_deadline_at = now + timedelta(seconds=RECONCILE_TIMEOUT)
            host.can_retry = False
            should_reconcile = True
        else:
            host.stage = 'failed'
            host.stage_color = 'error'
            host.error_code = f'{task.task_type}_timeout'
            host.can_retry = True
            should_reconcile = False
        host.failed_stage = task.task_type
        host.save(update_fields=[
            'stage', 'stage_color', 'error_code', 'failed_stage', 'reason',
            'timeout_reason', 'reconcile_deadline_at', 'can_retry',
            'last_heartbeat_at', 'updated_at',
        ])

    if should_reconcile:
        reconcile_governance_host.apply_async(args=[task_id, target_id])
    _finalize_task_status(task)


def _finalize_task_status(task: GovernanceTask) -> bool:
    '''根据所有主机结果汇总任务状态，返回是否首次进入终态。'''
    failure_stages = {'failed', 'reboot_failed'}

    with transaction.atomic():
        locked_task = GovernanceTask.objects.select_for_update().get(pk=task.pk)
        if locked_task.status in GovernanceTaskStatus.TERMINAL_STATES:
            task.refresh_from_db()
            return False

        success_stages = {'completed', 'reboot_scheduled'}
        if locked_task.task_type != GovernanceTaskType.REBOOT:
            success_stages.add('pending_reboot')
        terminal_host_stages = success_stages | failure_stages | {'cancelled', 'pending_confirmation'}

        hosts = list(locked_task.host_results.all())
        if not hosts:
            final_status = GovernanceTaskStatus.COMPLETED
        elif any(host.stage not in terminal_host_stages for host in hosts):
            locked_task.status = GovernanceTaskStatus.RUNNING
            locked_task.finished_at = None
            locked_task.save(update_fields=['status', 'finished_at', 'updated_at'])
            task.refresh_from_db()
            return False
        else:
            cancelled_hosts = [host for host in hosts if host.stage == 'cancelled']
            if len(cancelled_hosts) == len(hosts):
                final_status = GovernanceTaskStatus.CANCELLED
            elif cancelled_hosts:
                final_status = GovernanceTaskStatus.PARTIAL_CANCELLED
            elif all(host.stage == 'completed' for host in hosts):
                final_status = GovernanceTaskStatus.COMPLETED
            elif any(host.stage in success_stages for host in hosts) and not any(
                host.stage in failure_stages for host in hosts
            ):
                final_status = GovernanceTaskStatus.COMPLETED
            elif any(host.stage in success_stages for host in hosts) and any(
                host.stage in failure_stages for host in hosts
            ):
                final_status = GovernanceTaskStatus.PARTIAL_SUCCESS
            else:
                final_status = GovernanceTaskStatus.FAILED

        locked_task.status = final_status
        locked_task.finished_at = timezone.now()
        locked_task.save(update_fields=['status', 'finished_at', 'updated_at'])

    task.refresh_from_db()
    return True


def _schedule_post_reboot_verify(reboot_task: GovernanceTask) -> None:
    '''重启任务成功后，不立即创建验证任务。

    主机保持 pending_reboot 状态，由 verify_pending_reboot_hosts 定时任务
    探测主机恢复后自动创建验证任务。
    '''
    pending_count = reboot_task.host_results.filter(stage='pending_reboot').count()
    if pending_count:
        logger.info(
            '[post_reboot_verify] reboot_task=%s %s 台主机等待恢复，由定时任务自动验证',
            reboot_task.id, pending_count,
        )


def is_chain_overdue(task: GovernanceTask, now=None) -> bool:
    '''判断连续治理链路是否超期，并首次记录超期时间。'''
    if task.chain_deadline_at is None:
        return False
    current = now or timezone.now()
    if current <= task.chain_deadline_at:
        return False
    if task.overdue_at is None:
        GovernanceTask.objects.filter(pk=task.pk, overdue_at__isnull=True).update(
            overdue_at=current,
            updated_at=current,
        )
        task.overdue_at = current
    return True


def _schedule_auto_reboot(install_task: GovernanceTask) -> None:
    '''install 任务开启自动重启时，为安装成功的主机创建 reboot 任务。'''
    if is_chain_overdue(install_task):
        logger.warning(
            '[auto_reboot] install_task=%s 治理链路已超期，不再创建新的自动重启任务',
            install_task.id,
        )
        return
    successful_target_ids = [
        h.target_id
        for h in install_task.host_results.filter(stage='pending_reboot').exclude(
            error_code='reboot_requirement_unknown',
        )
    ]
    if not successful_target_ids:
        return

    reboot_task = GovernanceTask.objects.create(
        name=f"自动重启 · {len(successful_target_ids)} 台 · {timezone.now().strftime('%m-%d %H:%M')}",
        task_type=GovernanceTaskType.REBOOT,
        execution_mode='now',
        status=GovernanceTaskStatus.PENDING,
        target_list=successful_target_ids,
        patch_list=[],
        risk_snapshot=[
            item
            for item in (install_task.risk_snapshot or [])
            if int(item.get('host_id') or 0) in successful_target_ids
        ],
        team=install_task.team or [],
        created_by=install_task.created_by,
        timeout=install_task.timeout or DEFAULT_TIMEOUT,
        parent_task=install_task,
        chain_started_at=install_task.chain_started_at,
        chain_deadline_at=install_task.chain_deadline_at,
    )

    targets = {t.id: t for t in PatchTarget.objects.filter(pk__in=successful_target_ids)}
    for tid in successful_target_ids:
        target = targets.get(tid)
        GovernanceTaskHost.objects.create(
            task=reboot_task,
            target_id=tid,
            target_name=target.name if target else '',
            target_ip=target.ip if target else '',
            stage='waiting',
            stage_color='default',
        )

    try:
        from apps.patch_mgmt.tasks import execute_governance_task
        execute_governance_task.delay(reboot_task.id)
        logger.info(
            '[auto_reboot] install_task=%s 已创建自动重启任务 reboot_task=%s targets=%s',
            install_task.id, reboot_task.id, successful_target_ids,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            '[auto_reboot] 触发自动重启任务失败 install_task=%s reboot_task=%s: %s',
            install_task.id, reboot_task.id, exc,
        )


def _schedule_post_install_verify(install_task: GovernanceTask) -> None:
    '''无需重启或安装失败的主机进入验证，以最终合规结果作为业务事实。'''
    verify_hosts = list(
        install_task.host_results.filter(stage__in=('completed', 'failed'))
        .exclude(failed_stage='dispatch')
    )
    if not verify_hosts:
        return

    target_ids = [host.target_id for host in verify_hosts]
    verify_task = GovernanceTask.objects.create(
        name=f"安装后自动验证 · {len(target_ids)} 台 · {timezone.now().strftime('%m-%d %H:%M')}",
        task_type=GovernanceTaskType.VERIFY,
        execution_mode='now',
        status=GovernanceTaskStatus.PENDING,
        target_list=target_ids,
        patch_list=install_task.patch_list or [],
        risk_snapshot=[
            item
            for item in (install_task.risk_snapshot or [])
            if int(item.get('host_id') or 0) in target_ids
        ],
        team=install_task.team or [],
        created_by=install_task.created_by,
        timeout=install_task.timeout or DEFAULT_TIMEOUT,
        parent_task=install_task,
        chain_started_at=install_task.chain_started_at,
        chain_deadline_at=install_task.chain_deadline_at,
    )
    for host in verify_hosts:
        GovernanceTaskHost.objects.create(
            task=verify_task,
            target_id=host.target_id,
            target_name=host.target_name,
            target_ip=host.target_ip,
            stage='waiting',
            stage_color='default',
        )

    try:
        from apps.patch_mgmt.tasks import execute_governance_task
        execute_governance_task.delay(verify_task.id)
        logger.info(
            '[post_install_verify] install_task=%s 已创建验证任务 verify_task=%s targets=%s',
            install_task.id, verify_task.id, target_ids,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            '[post_install_verify] 触发验证任务失败 install_task=%s verify_task=%s: %s',
            install_task.id, verify_task.id, exc,
        )


def _run_terminal_followups(task: GovernanceTask) -> None:
    '''任务首次进入终态后触发后续治理链路。'''
    if task.task_type == GovernanceTaskType.INSTALL and task.auto_reboot:
        _schedule_auto_reboot(task)

    if task.task_type == GovernanceTaskType.INSTALL:
        _schedule_post_install_verify(task)

    if task.task_type == GovernanceTaskType.REBOOT and task.status in (
        GovernanceTaskStatus.COMPLETED,
        GovernanceTaskStatus.PARTIAL_SUCCESS,
        GovernanceTaskStatus.PARTIAL_CANCELLED,
    ):
        _schedule_post_reboot_verify(task)


def finalize_governance_task(task_id: int) -> None:
    '''幂等汇总父任务；用于主机子任务 finally 兜底。'''
    task = GovernanceTask.objects.filter(pk=task_id).first()
    if task is not None and _finalize_task_status(task):
        _run_terminal_followups(task)


def run_governance_host(task: GovernanceTask, target_id: int) -> None:
    '''只执行治理任务中的一台主机，并并发安全地汇总父任务状态。'''
    target = PatchTarget.objects.filter(pk=target_id).first()
    host = GovernanceTaskHost.objects.filter(task=task, target_id=target_id).first()

    if host is None:
        host = GovernanceTaskHost.objects.create(
            task=task,
            target_id=target_id,
            target_name=target.name if target else '',
            target_ip=target.ip if target else '',
            stage='waiting',
            stage_color='default',
        )

    if target is None:
        if host.stage == 'waiting':
            _record_host_result(
                host,
                stage='failed',
                stage_color='error',
                reason='目标不存在或已删除',
                failed_stage='dispatch',
                can_retry=False,
            )
        if _finalize_task_status(task):
            _run_terminal_followups(task)
        logger.warning('[run_governance_host] 目标 %s 不存在，已标记主机失败', target_id)
        return

    running_stage = {
        GovernanceTaskType.REBOOT: 'rebooting',
        GovernanceTaskType.INSTALL: 'installing',
        GovernanceTaskType.ASSESS: 'scanning',
        GovernanceTaskType.VERIFY: 'scanning',
    }.get(task.task_type, 'running')
    if not _claim_waiting_host(host, running_stage):
        host.refresh_from_db()
        logger.info(
            '[run_governance_host] 跳过非等待主机 task_id=%s target_id=%s stage=%s',
            task.id, target_id, host.stage,
        )
        return

    from apps.patch_mgmt.config import get_stage_timeout

    execution_id = f'{task.id}:{target_id}'
    timeout = get_stage_timeout(task.task_type)
    if task.task_type == GovernanceTaskType.REBOOT:
        _execute_reboot(target, host, execution_id, timeout)
    elif task.task_type == GovernanceTaskType.INSTALL:
        selected_patch_ids = [
            int(item["patch_id"])
            for item in (task.risk_snapshot or [])
            if int(item.get("host_id") or 0) == target_id and item.get("patch_id")
        ]
        _execute_install(
            target,
            host,
            list(dict.fromkeys(selected_patch_ids)) if selected_patch_ids else task.patch_list or [],
            execution_id,
            timeout,
        )
    elif task.task_type in (GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY):
        _execute_assess(target, host, execution_id, timeout)
    else:
        _record_host_result(
            host,
            stage='failed',
            stage_color='error',
            reason=f'暂不支持的任务类型: {task.task_type}',
            failed_stage='dispatch',
        )

    if _finalize_task_status(task):
        _run_terminal_followups(task)


def run_governance_task(task: GovernanceTask) -> None:
    '''兼容同步调用：逐台调用主机执行入口；Celery 生产入口按主机拆分。'''
    logger.info(
        '[run_governance_task] 开始 task_id=%s type=%s targets=%s',
        task.id, task.task_type, len(task.target_list or []),
    )
    targets = {
        target.id: target
        for target in PatchTarget.objects.filter(pk__in=task.target_list or [])
    }
    existing_target_ids = set(
        GovernanceTaskHost.objects.filter(task=task).values_list('target_id', flat=True)
    )
    GovernanceTaskHost.objects.bulk_create([
        GovernanceTaskHost(
            task=task,
            target_id=target_id,
            target_name=targets[target_id].name if target_id in targets else '',
            target_ip=targets[target_id].ip if target_id in targets else '',
            stage='waiting',
            stage_color='default',
        )
        for target_id in task.target_list or []
        if target_id not in existing_target_ids
    ])
    for target_id in task.target_list or []:
        run_governance_host(task, target_id)

    if not (task.target_list or []) and _finalize_task_status(task):
        _run_terminal_followups(task)

    logger.info(
        '[run_governance_task] 结束 task_id=%s status=%s',
        task.id, task.status,
    )


def _check_host_reachable(target: PatchTarget) -> bool:
    '''快速 TCP 端口探测，判断主机是否可达（不认证）。'''
    import socket

    if target.os_type == OSType.WINDOWS:
        port = target.winrm_port or 5985
    else:
        port = target.ssh_port or 22

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((target.ip, port))
        s.close()
        return True
    except Exception:
        return False
