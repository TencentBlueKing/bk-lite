import json
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import yaml

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Node
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.rpc.ansible import AnsibleExecutor
from config.components.nats import NATS_NAMESPACE


ANSIBLE_EXECUTOR_COLLECTOR_ID = "ansibleexecutor_linux"
ANSIBLE_COLLECTOR_NORMAL_STATUS = 0
ANSIBLE_TASK_POLL_INTERVAL_SECONDS = 1
WINRM_CONNECTION_TIMEOUT_SECONDS = 60
WINRM_CLEANUP_TIMEOUT_SECONDS = 90

_ANSIBLE_MSG_PATTERN = re.compile(r'"msg"\s*:\s*"(?P<msg>(?:\\.|[^"\\])*)"')
_WINRM_CERTIFICATE_MARKERS = (
    "certificate_verify_failed",
    "certificate verify failed",
    "unable to get local issuer certificate",
    "sslcerverificationerror",
    "hostname mismatch",
    "certificate has expired",
)
_WINRM_AUTH_MARKERS = (
    "authentication failed",
    "access is denied",
    "access denied",
    "invalid credentials",
    "unauthorized",
    "login failure",
)
_WINRM_BUSY_MARKERS = (
    "wsman operationtimeout during send input",
    "winrm send_input failed",
    "wsmanfault_code': 170",
    "wsmanfault_code': '170'",
    "请求的资源在使用中",
    "error_busy",
)


@dataclass(frozen=True)
class WindowsBootstrapTarget:
    host: str
    port: int
    user: str
    password: str
    scheme: str = "https"
    transport: str = "ntlm"
    validate_certificate: bool = True


class AnsibleExecutorResolver:
    @classmethod
    def resolve(cls, cloud_region_id: int) -> str:
        candidates = Node.objects.filter(
            cloud_region_id=cloud_region_id,
            node_type=ControllerConstants.NODE_TYPE_CONTAINER,
            operating_system=NodeConstants.LINUX_OS,
        ).order_by("id")
        for node in candidates.iterator():
            collectors = (node.status or {}).get("collectors", [])
            if any(
                isinstance(item, dict)
                and item.get("collector_id") == ANSIBLE_EXECUTOR_COLLECTOR_ID
                and item.get("status") == ANSIBLE_COLLECTOR_NORMAL_STATUS
                for item in collectors
            ):
                return str(node.id)
        raise BaseAppException(f"No healthy Ansible Executor found in cloud region {cloud_region_id}")


class WindowsRemoteBootstrapService:
    def __init__(self, executor_factory=AnsibleExecutor, resolver=AnsibleExecutorResolver):
        self.executor_factory = executor_factory
        self.resolver = resolver

    @staticmethod
    def _host_credentials(target: WindowsBootstrapTarget) -> list[dict]:
        return [
            {
                "host": target.host,
                "port": target.port,
                "user": target.user,
                "password": target.password,
                "connection": "winrm",
                "winrm_scheme": target.scheme,
                "winrm_transport": target.transport,
                "winrm_cert_validation": target.validate_certificate,
            }
        ]

    @staticmethod
    def _validate_target(target: WindowsBootstrapTarget) -> None:
        if target.scheme != "https" or not 1 <= target.port <= 65535 or target.transport != "ntlm":
            raise BaseAppException("Windows remote operation requires HTTPS, NTLM, and a valid port")

    @staticmethod
    def _winrm_extra_vars() -> dict[str, int]:
        return {"ansible_winrm_connection_timeout": WINRM_CONNECTION_TIMEOUT_SECONDS}

    @staticmethod
    def _collect_ansible_failure_text(result: dict) -> str:
        chunks: list[str] = []

        for key in ("error", "status"):
            value = result.get(key)
            if value not in (None, ""):
                chunks.append(str(value))

        task_result = result.get("result")
        if isinstance(task_result, dict):
            for key in ("error", "error_message", "status"):
                value = task_result.get(key)
                if value not in (None, ""):
                    chunks.append(str(value))

            summary = task_result.get("result_summary")
            if isinstance(summary, dict):
                combined = summary.get("stdout_combined")
                if combined:
                    chunks.append(str(combined))

            host_results = task_result.get("result")
            if isinstance(host_results, list):
                for item in host_results:
                    if not isinstance(item, dict):
                        continue
                    for key in ("error_message", "stderr", "stdout", "status", "raw_status"):
                        value = item.get(key)
                        if value not in (None, ""):
                            chunks.append(str(value))
            elif host_results not in (None, ""):
                chunks.append(str(host_results))
        elif task_result not in (None, ""):
            chunks.append(str(task_result))

        return "\n".join(chunks)

    @staticmethod
    def _extract_ansible_msg(text: str) -> str | None:
        match = _ANSIBLE_MSG_PATTERN.search(text)
        if not match:
            return None
        raw_msg = match.group("msg")
        try:
            return str(json.loads(f'"{raw_msg}"')).strip() or None
        except (json.JSONDecodeError, TypeError):
            return raw_msg.replace('\\"', '"').strip() or None

    @classmethod
    def _describe_ansible_failure(cls, result: dict) -> str:
        text = cls._collect_ansible_failure_text(result)
        normalized = text.lower()
        ansible_msg = cls._extract_ansible_msg(text)

        if any(marker in normalized for marker in _WINRM_CERTIFICATE_MARKERS):
            detail = ansible_msg or "unable to verify the target WinRM HTTPS certificate"
            return (
                "WinRM HTTPS certificate validation failed: the Ansible Executor does not trust "
                f"the target host certificate ({detail}). Import the WinRM issuing CA into the "
                "Executor trust store, confirm the certificate matches the target host/IP, then retry. "
                "For trusted private networks, certificate validation can be disabled explicitly in the install configuration."
            )

        if any(marker in normalized for marker in _WINRM_BUSY_MARKERS):
            return (
                "WinRM session is busy or stalled (WSMan fault 170 while sending module input). "
                "The target accepted the WinRM connection but could not accept this operation. "
                "Wait for the current WinRM operation to finish, restart the WinRM service if safe, "
                "and check the WinRS per-user shell and concurrent-operation quotas before retrying."
            )

        if any(marker in normalized for marker in _WINRM_AUTH_MARKERS):
            detail = ansible_msg or "invalid WinRM credentials"
            return f"WinRM authentication failed ({detail}). Check the username and password, then retry."

        if "unreachable" in normalized or "establish winrm connection" in normalized:
            detail = ansible_msg or "the target host did not accept the WinRM HTTPS connection"
            return (
                f"Target host is unreachable over WinRM HTTPS ({detail}). "
                "Check TCP/5986 connectivity, firewall rules, and the HTTPS WinRM listener."
            )

        if ansible_msg:
            return f"Ansible task failed: {ansible_msg}"

        compact_error = result.get("error")
        if isinstance(compact_error, str) and compact_error.strip():
            return f"Ansible task failed: {compact_error.strip()}"

        return "Ansible task failed during Windows remote bootstrap"

    @staticmethod
    def _wait_for_task(executor: AnsibleExecutor, task_id: str, timeout: int, terminal_callback=None) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            result = executor.task_query(task_id, timeout=min(timeout, 30))
            if not isinstance(result, dict):
                raise BaseAppException("Ansible task returned an invalid result")
            status = result.get("status")
            if status in {"success", "failed", "callback_failed"}:
                if terminal_callback is not None:
                    try:
                        terminal_callback(result)
                    except Exception:
                        logger.exception("Failed to persist terminal Windows bootstrap events: task_id=%s", task_id)
                if status != "success":
                    raise BaseAppException(WindowsRemoteBootstrapService._describe_ansible_failure(result))
                return result
            if time.monotonic() >= deadline:
                raise BaseAppException("Ansible task timed out")
            time.sleep(ANSIBLE_TASK_POLL_INTERVAL_SECONDS)

    @staticmethod
    def _accepted_task_id(response: dict, fallback: str) -> str:
        if not isinstance(response, dict):
            raise BaseAppException("Ansible task submission returned an invalid result")
        return str(response.get("task_id") or fallback)

    @staticmethod
    def _extract_stdout(result: dict) -> str:
        task_result = result.get("result") if isinstance(result, dict) else None
        if not isinstance(task_result, dict):
            return ""
        event_output = WindowsRemoteBootstrapService._extract_installer_events(task_result)
        if event_output:
            return event_output
        host_results = task_result.get("result")
        if not isinstance(host_results, list):
            return str(host_results or "")
        outputs = []
        for item in host_results:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "success":
                raise BaseAppException(str(item.get("error_message") or item.get("stderr") or "Windows bootstrap failed"))
            output = item.get("stdout")
            if output:
                outputs.append(str(output))
        return "\n".join(outputs)

    @staticmethod
    def _extract_installer_events(task_result: dict) -> str:
        candidates = []
        host_results = task_result.get("result")
        if isinstance(host_results, list):
            candidates.extend(str(item.get("stdout") or "") for item in host_results if isinstance(item, dict))
        result_summary = task_result.get("result_summary")
        if isinstance(result_summary, dict):
            candidates.append(str(result_summary.get("stdout_combined") or ""))

        event_pattern = re.compile(r"BKINSTALL_EVENT\s+(\{(?:\\.|[^{}])*\})")
        events = []
        seen = set()
        for candidate in candidates:
            for payload in event_pattern.findall(candidate):
                try:
                    decoded_payload = json.loads(f'"{payload}"')
                    event = json.loads(decoded_payload)
                except (json.JSONDecodeError, TypeError):
                    try:
                        event = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        continue
                canonical_payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                if canonical_payload in seen:
                    continue
                seen.add(canonical_payload)
                events.append(f"BKINSTALL_EVENT {canonical_payload}")
        return "\n".join(events)

    @staticmethod
    def _execution_playbook(*, validate_certificate: bool = True) -> str:
        bootstrap_argv = [
            "{{ bklite_bootstrap_path }}",
            "--url-file",
            "{{ bklite_session_file }}",
            "--require-https",
        ]
        if not validate_certificate:
            # The user-facing trusted-network opt-out covers both WinRM and
            # the bootstrap's HTTPS requests while still forbidding HTTP.
            bootstrap_argv.append("--skip-tls")
        bootstrap_argv.extend(
            [
                "--install-dir",
                r"C:\fusion-collectors",
                "--execution-id",
                "{{ bklite_execution_id }}",
                "--task-node-id",
                "{{ bklite_task_node_id }}",
                "--attempt",
                "{{ bklite_execution_attempt }}",
                "--deadline-unix",
                "{{ bklite_execution_deadline_unix }}",
                "--progress-subject",
                "{{ bklite_progress_subject }}",
            ]
        )
        playbook = [
            {
                "hosts": "all",
                "gather_facts": False,
                "tasks": [
                    {
                        "name": "Install BK-Lite controller",
                        "block": [
                            {
                                "name": "Verify supported Windows and PowerShell version",
                                # Use win_shell instead of nested powershell.exe -Command via raw.
                                # WinRM pipelining already executes inside PowerShell; an outer
                                # double-quoted -Command layer expands $os/$ps before assignment.
                                "ansible.windows.win_shell": (
                                    "$ErrorActionPreference = 'Stop'\n"
                                    "$os = [Environment]::OSVersion.Version\n"
                                    "$ps = $PSVersionTable.PSVersion\n"
                                    "if ($os.Major -lt 10 -or $ps -lt [Version]'5.1') {\n"
                                    "  Write-Error 'BK-Lite remote installation requires Windows 10/Server 2016 and PowerShell 5.1 or newer'\n"
                                    "  exit 42\n"
                                    "}\n"
                                    "Write-Output ('Windows ' + $os.ToString() + '; PowerShell ' + $ps.ToString())\n"
                                ),
                                "changed_when": False,
                            },
                            {
                                "name": "Remove any colliding installer session directory",
                                "ansible.windows.win_file": {
                                    "path": "{{ bklite_session_dir }}",
                                    "state": "absent",
                                },
                                "no_log": True,
                            },
                            {
                                "name": "Create protected installer session directory",
                                "ansible.windows.win_file": {
                                    "path": "{{ bklite_session_dir }}",
                                    "state": "directory",
                                },
                            },
                            {
                                "name": "Grant installer account access to protected session directory",
                                "ansible.windows.win_acl": {
                                    "path": "{{ bklite_session_dir }}",
                                    "user": "{{ bklite_session_user }}",
                                    "rights": "FullControl",
                                    "type": "allow",
                                    "state": "present",
                                },
                                "no_log": True,
                            },
                            {
                                "name": "Grant SYSTEM access to protected session directory",
                                "ansible.windows.win_acl": {
                                    "path": "{{ bklite_session_dir }}",
                                    "user": "SYSTEM",
                                    "rights": "FullControl",
                                    "type": "allow",
                                    "state": "present",
                                },
                                "no_log": True,
                            },
                            {
                                "name": "Remove inherited access from protected session directory",
                                "ansible.windows.win_acl_inheritance": {
                                    "path": "{{ bklite_session_dir }}",
                                    "state": "absent",
                                },
                                "no_log": True,
                            },
                            {
                                "name": "Write protected installer session",
                                "ansible.windows.win_copy": {
                                    "content": "{{ bklite_session_url }}",
                                    "dest": "{{ bklite_session_file }}",
                                    "force": True,
                                },
                                "no_log": True,
                            },
                            {
                                "name": "Run BK-Lite controller bootstrap",
                                "ansible.windows.win_command": {
                                    "argv": bootstrap_argv
                                },
                                "register": "bklite_bootstrap_result",
                            },
                            {
                                "name": "Print BK-Lite bootstrap events",
                                "ansible.builtin.debug": {"var": "bklite_bootstrap_result.stdout"},
                            },
                        ],
                        "always": [
                            {
                                "name": "Remove protected installer session directory",
                                "ansible.windows.win_file": {"path": "{{ bklite_session_dir }}", "state": "absent"},
                                "no_log": True,
                                "register": "bklite_session_cleanup",
                                "ignore_errors": True,
                            },
                            {
                                "name": "Remove BK-Lite bootstrap",
                                "ansible.windows.win_file": {"path": "{{ bklite_bootstrap_path }}", "state": "absent"},
                                "register": "bklite_bootstrap_cleanup",
                                "ignore_errors": True,
                            },
                            {
                                "name": "Verify BK-Lite temporary files were removed",
                                "ansible.builtin.fail": {"msg": "BK-Lite temporary file cleanup failed"},
                                "when": (
                                    "bklite_session_cleanup is failed or "
                                    "bklite_bootstrap_cleanup is failed"
                                ),
                            },
                        ],
                    }
                ],
            }
        ]
        return yaml.safe_dump(playbook, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _cleanup_playbook(remote_path: str, session_dir: str) -> str:
        playbook = [
            {
                "hosts": "all",
                "gather_facts": False,
                "tasks": [
                    {
                        "name": "Remove protected installer session directory",
                        "ansible.windows.win_file": {"path": session_dir, "state": "absent"},
                        "no_log": True,
                        "register": "bklite_session_cleanup",
                        "ignore_errors": True,
                    },
                    {
                        "name": "Remove BK-Lite bootstrap",
                        "ansible.windows.win_file": {"path": remote_path, "state": "absent"},
                        "register": "bklite_bootstrap_cleanup",
                        "ignore_errors": True,
                    },
                    {
                        "name": "Verify BK-Lite temporary files were removed",
                        "ansible.builtin.fail": {"msg": "BK-Lite temporary file cleanup failed"},
                        "when": "bklite_session_cleanup is failed or bklite_bootstrap_cleanup is failed",
                    },
                ],
            }
        ]
        return yaml.safe_dump(playbook, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _uninstall_playbook() -> str:
        command = r"""
$ErrorActionPreference = 'Stop'
$changed = $false
$service = Get-Service -Name 'sidecar' -ErrorAction SilentlyContinue
if ($null -ne $service) {
  if ($service.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Stopped) {
    Stop-Service -Name 'sidecar' -Force
    $service.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(30))
    $changed = $true
  }
  $service.Close()
  & sc.exe delete sidecar | Out-Null
  if ($LASTEXITCODE -notin @(0, 1060, 1072)) {
    throw "Delete sidecar service failed with exit code $LASTEXITCODE"
  }
  $changed = $true
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($null -eq (Get-Service -Name 'sidecar' -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 1
  }
  if ($null -ne (Get-Service -Name 'sidecar' -ErrorAction SilentlyContinue)) {
    throw 'Timed out waiting for sidecar service deletion'
  }
}

$ownedPaths = @(
  'C:\fusion-collectors',
  'C:\fusion-collectors.bklite-staging',
  'C:\fusion-collectors.bklite-backup',
  'C:\fusion-collectors.bklite-install.fence',
  'C:\fusion-collectors.bklite-install.lock'
)
foreach ($ownedPath in $ownedPaths) {
  if (Test-Path -LiteralPath $ownedPath) {
    Remove-Item -LiteralPath $ownedPath -Recurse -Force
    $changed = $true
  }
}

Get-ChildItem -LiteralPath 'C:\' -Filter 'fusion-collectors.bklite-backup-retained-*' -Directory -ErrorAction SilentlyContinue |
  ForEach-Object {
    if ($_.FullName -notlike 'C:\fusion-collectors.bklite-backup-retained-*') {
      throw "Refusing to remove unexpected path: $($_.FullName)"
    }
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
    $changed = $true
  }

Write-Output ('BKUNINSTALL_CHANGED=' + $changed.ToString().ToLowerInvariant())
""".strip()
        playbook = [
            {
                "name": "Uninstall BK-Lite Windows controller",
                "hosts": "all",
                "gather_facts": False,
                "tasks": [
                    {
                        "name": "Stop and remove the controller within its owned paths",
                        "ansible.windows.win_shell": {"_raw_params": command},
                        "register": "bklite_uninstall",
                        "changed_when": "'BKUNINSTALL_CHANGED=true' in bklite_uninstall.stdout",
                    }
                ],
            }
        ]
        return yaml.safe_dump(playbook, allow_unicode=True, sort_keys=False)

    def uninstall(
        self,
        *,
        cloud_region_id: int,
        task_node_id: int,
        target: WindowsBootstrapTarget,
        timeout: int,
    ) -> str:
        self._validate_target(target)
        executor_id = self.resolver.resolve(cloud_region_id)
        executor = self.executor_factory(executor_id)
        task_id = f"controller-uninstall-{task_node_id}-{uuid.uuid4().hex}"
        accepted = executor.playbook(
            host_credentials=self._host_credentials(target),
            playbook_content=self._uninstall_playbook(),
            extra_vars=self._winrm_extra_vars(),
            task_id=task_id,
            timeout=timeout,
        )
        result = self._wait_for_task(executor, self._accepted_task_id(accepted, task_id), timeout)
        return self._extract_stdout(result)

    def _cleanup_remote_files(
        self,
        executor: AnsibleExecutor,
        credentials: list[dict],
        task_node_id: int,
        attempt: int,
        remote_path: str,
        session_dir: str,
        timeout: int,
    ) -> None:
        cleanup_timeout = min(timeout, WINRM_CLEANUP_TIMEOUT_SECONDS)
        cleanup_task_id = f"controller-bootstrap-cleanup-{task_node_id}-{attempt}"
        accepted = executor.playbook(
            host_credentials=credentials,
            playbook_content=self._cleanup_playbook(remote_path, session_dir),
            extra_vars=self._winrm_extra_vars(),
            task_id=cleanup_task_id,
            timeout=cleanup_timeout,
        )
        self._wait_for_task(executor, self._accepted_task_id(accepted, cleanup_task_id), cleanup_timeout)

    def run(
        self,
        *,
        cloud_region_id: int,
        task_node_id: int,
        attempt: int,
        cpu_architecture: str,
        session_url: str,
        target: WindowsBootstrapTarget,
        timeout: int,
        execution_id: str = "",
        progress_subject: str = "",
        event_callback=None,
        ownership_validator=None,
        execution_deadline_unix: int = 0,
    ) -> str:
        self._validate_target(target)
        parsed_session_url = urlparse(session_url)
        if parsed_session_url.scheme.lower() != "https" or not parsed_session_url.hostname:
            raise BaseAppException("Windows remote installation requires an HTTPS installer session URL")
        executor_id = self.resolver.resolve(cloud_region_id)
        executor = self.executor_factory(executor_id)
        credentials = self._host_credentials(target)
        artifact = InstallerSessionService.windows_bootstrap_artifact(cpu_architecture)
        remote_name = f"bklite-controller-bootstrap-{task_node_id}-{attempt}.exe"
        remote_path = f"C:/Windows/Temp/{remote_name}"
        session_nonce = execution_id or uuid.uuid4().hex
        session_dir = f"C:/Windows/Temp/bklite-controller-session-{session_nonce}"
        session_file = f"{session_dir}/session.url"

        primary_error = None
        try:
            stage_task_id = f"controller-bootstrap-stage-{task_node_id}-{attempt}"
            accepted = executor.playbook(
                host_credentials=credentials,
                files=[{"name": remote_name, "file_key": artifact["object_key"]}],
                file_distribution={
                    "bucket_name": NATS_NAMESPACE,
                    "target_path": "C:/Windows/Temp",
                    "overwrite": True,
                },
                extra_vars=self._winrm_extra_vars(),
                task_id=stage_task_id,
                timeout=timeout,
            )
            self._wait_for_task(executor, self._accepted_task_id(accepted, stage_task_id), timeout)
            if ownership_validator is not None and not ownership_validator():
                raise BaseAppException("Windows remote installation was cancelled before execution")

            run_task_id = f"controller-bootstrap-run-{task_node_id}-{attempt}"
            accepted = executor.playbook(
                host_credentials=credentials,
                playbook_content=self._execution_playbook(
                    validate_certificate=target.validate_certificate,
                ),
                extra_vars={
                    **self._winrm_extra_vars(),
                    "bklite_session_url": session_url,
                    "bklite_session_dir": session_dir,
                    "bklite_session_file": session_file,
                    "bklite_session_user": target.user,
                    "bklite_bootstrap_path": remote_path,
                    "bklite_execution_id": execution_id,
                    "bklite_task_node_id": task_node_id,
                    "bklite_execution_attempt": attempt,
                    "bklite_execution_deadline_unix": execution_deadline_unix,
                    "bklite_progress_subject": progress_subject,
                },
                task_id=run_task_id,
                timeout=timeout,
            )
            def replay_terminal_events(terminal_result):
                if event_callback is None:
                    return
                task_result = terminal_result.get("result") if isinstance(terminal_result, dict) else None
                if not isinstance(task_result, dict):
                    return
                event_output = self._extract_installer_events(task_result)
                if event_output:
                    event_callback(event_output)

            result = self._wait_for_task(
                executor,
                self._accepted_task_id(accepted, run_task_id),
                timeout,
                terminal_callback=replay_terminal_events,
            )
            return self._extract_stdout(result)
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            try:
                self._cleanup_remote_files(
                    executor,
                    credentials,
                    task_node_id,
                    attempt,
                    remote_path,
                    session_dir,
                    timeout,
                )
            except Exception:
                logger.exception(
                    "Windows bootstrap fallback cleanup failed: task_node_id=%s attempt=%s primary_failed=%s",
                    task_node_id,
                    attempt,
                    primary_error is not None,
                )
