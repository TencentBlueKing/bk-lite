import json
import re
import time
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
                    detail = result.get("error") or result.get("result") or status
                    raise BaseAppException(f"Ansible task failed: {detail}")
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
    def _execution_playbook() -> str:
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
                                "ansible.builtin.raw": (
                                    'powershell.exe -NoProfile -NonInteractive -Command "'
                                    "$ErrorActionPreference='Stop'; "
                                    "$os=[Environment]::OSVersion.Version; "
                                    "$ps=$PSVersionTable.PSVersion; "
                                    "if ($os.Major -lt 10 -or $ps -lt [Version]'5.1') { "
                                    "Write-Error 'BK-Lite remote installation requires Windows 10/Server 2016 and PowerShell 5.1 or newer'; "
                                    "exit 42 }; "
                                    "Write-Output ('Windows {0}; PowerShell {1}' -f $os,$ps)\""
                                ),
                                "changed_when": False,
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
                                    "argv": [
                                        "{{ bklite_bootstrap_path }}",
                                        "--url-file",
                                        "{{ bklite_session_file }}",
                                        "--require-https",
                                        "--install-dir",
                                        r"C:\fusion-collectors",
                                        "--execution-id",
                                        "{{ bklite_execution_id }}",
                                        "--progress-subject",
                                        "{{ bklite_progress_subject }}",
                                    ]
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
        cleanup_timeout = min(timeout, 30)
        cleanup_task_id = f"controller-bootstrap-cleanup-{task_node_id}-{attempt}"
        accepted = executor.playbook(
            host_credentials=credentials,
            playbook_content=self._cleanup_playbook(remote_path, session_dir),
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
    ) -> str:
        if target.scheme != "https" or target.port != 5986 or target.transport != "ntlm" or target.validate_certificate is not True:
            raise BaseAppException("Windows remote installation requires HTTPS, NTLM, port 5986, and server certificate validation")
        parsed_session_url = urlparse(session_url)
        if parsed_session_url.scheme.lower() != "https" or not parsed_session_url.hostname:
            raise BaseAppException("Windows remote installation requires an HTTPS installer session URL")
        executor_id = self.resolver.resolve(cloud_region_id)
        executor = self.executor_factory(executor_id)
        credentials = self._host_credentials(target)
        artifact = InstallerSessionService.windows_bootstrap_artifact(cpu_architecture)
        remote_name = f"bklite-controller-bootstrap-{task_node_id}-{attempt}.exe"
        remote_path = f"C:/Windows/Temp/{remote_name}"
        session_dir = f"C:/Windows/Temp/bklite-controller-session-{task_node_id}-{attempt}"
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
                task_id=stage_task_id,
                timeout=timeout,
            )
            self._wait_for_task(executor, self._accepted_task_id(accepted, stage_task_id), timeout)

            run_task_id = f"controller-bootstrap-run-{task_node_id}-{attempt}"
            accepted = executor.playbook(
                host_credentials=credentials,
                playbook_content=self._execution_playbook(),
                extra_vars={
                    "bklite_session_url": session_url,
                    "bklite_session_dir": session_dir,
                    "bklite_session_file": session_file,
                    "bklite_session_user": target.user,
                    "bklite_bootstrap_path": remote_path,
                    "bklite_execution_id": execution_id,
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
