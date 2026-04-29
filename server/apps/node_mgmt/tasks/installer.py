import uuid
import json
import queue
import threading

from celery import shared_task
from django.db import transaction
from django.db.models import Count, Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants

from apps.node_mgmt.models import (
    ControllerTask,
    CollectorTask,
    PackageVersion,
    Node,
    NodeCollectorInstallStatus,
    Collector,
)
from apps.node_mgmt.models import ControllerTaskNode

from apps.node_mgmt.utils.installer import (
    exec_command_to_remote,
    exec_command_to_remote_stream,
    download_to_local,
    exec_command_to_local,
    get_uninstall_command,
    unzip_file,
)
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.step_tracker import (
    advance_step,
    append_step,
    append_steps,
    build_step,
    clone_steps,
    now_iso,
    update_latest_step_by_action,
    update_last_running_step,
)
from apps.node_mgmt.utils.installer_schema import (
    build_installer_event_record,
    normalize_failure,
    normalize_overall_status,
    summarize_installer_progress,
)
from apps.node_mgmt.utils.task_result_schema import (
    _extract_latest_failure_from_steps,
    apply_result_envelope,
)
from config.components.nats import NATS_NAMESPACE
from nats_client.clients import subscribe_lines_sync


CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS = InstallerConstants.CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS

INSTALLER_EVENT_PREFIX = "BKINSTALL_EVENT "


def _parse_installer_events(output_text: str):
    events = []
    if not output_text:
        return events

    for line in output_text.splitlines():
        if not line.startswith(INSTALLER_EVENT_PREFIX):
            continue
        payload = line[len(INSTALLER_EVENT_PREFIX) :].strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        events.append(data)
    return events


def _apply_installer_events_to_node(node_obj, output_text: str):
    events = _parse_installer_events(output_text)
    if not events:
        return False

    for event in events:
        event_record = build_installer_event_record(event)
        action = event_record["action"]
        status = event_record["status"]
        message = event_record["message"]
        details = event_record["details"]

        if status == "running":
            steps = (node_obj.result or {}).get("steps", [])
            existing_running = any(
                step.get("action") == action and step.get("status") == InstallerConstants.STEP_STATUS_RUNNING
                for step in reversed(steps)
                if isinstance(step, dict)
            )
            if existing_running:
                _update_step_status_by_action(node_obj, action, InstallerConstants.STEP_STATUS_RUNNING, message, details=details)
            else:
                _add_step(node_obj, action, status, message, details=details)
        else:
            if not _update_step_status_by_action(node_obj, action, status, message, details=details):
                _update_step_status(node_obj, status, message, details=details)

    _refresh_installer_progress(node_obj)
    return True


def _consume_installer_stream(node_obj, result_queue, stop_event):
    while not stop_event.is_set() or not result_queue.empty():
        try:
            payload = result_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        line = payload.get("line", "")
        _apply_installer_events_to_node(node_obj, line)


def _add_steps(node_obj, step_items):
    result = node_obj.result or {}
    append_steps(result, clone_steps(step_items, timestamp=now_iso()))
    node_obj.result = result
    node_obj.save(update_fields=["result"])


def _get_execution_phase(node_obj) -> str | None:
    result = node_obj.result or {}
    return result.get(InstallerConstants.EXECUTION_PHASE_KEY)


def _get_execution_attempt(node_obj) -> int:
    result = node_obj.result or {}
    attempt = result.get(InstallerConstants.EXECUTION_ATTEMPT_KEY)
    if isinstance(attempt, int) and attempt > 0:
        return attempt
    return 1


def _add_step(node_obj, action, status, message, timestamp=None, details=None):
    """添加执行步骤记录并立即持久化"""
    result = node_obj.result or {}
    step = append_step(
        result,
        action,
        status,
        message,
        timestamp=timestamp or now_iso(),
        details=details,
    )
    node_obj.result = result
    node_obj.save(update_fields=["result"])
    return step


def _build_step(action, status, message, timestamp=None, details=None):
    return build_step(
        action,
        status,
        message,
        timestamp=timestamp or now_iso(),
        details=details,
    )


def _update_step_status(node_obj, status, message, details=None):
    """更新最后一个步骤的状态并立即持久化"""
    result = node_obj.result or {}
    if update_last_running_step(
        result,
        status,
        message,
        details=details,
        timestamp=now_iso(),
    ):
        node_obj.result = result
        node_obj.save(update_fields=["result"])


def _update_step_status_by_action(node_obj, action, status, message, details=None):
    result = node_obj.result or {}
    if update_latest_step_by_action(
        result,
        action,
        status,
        message,
        details=details,
        timestamp=now_iso(),
    ):
        node_obj.result = result
        node_obj.save(update_fields=["result"])
        return True
    return False


def _advance_step(node_obj, status, message, details=None, next_steps=None):
    result = node_obj.result or {}
    advance_step(
        result,
        status,
        message,
        details=details,
        next_steps=next_steps,
        timestamp=now_iso(),
    )
    node_obj.result = result
    node_obj.save(update_fields=["result"])


def _batch_add_step(nodes, action, status, message, timestamp=None, details=None):
    """批量为多个节点添加相同步骤并立即持久化"""
    ts = timestamp or now_iso()

    for node_obj in nodes:
        result = node_obj.result or {}
        append_step(result, action, status, message, timestamp=ts, details=details)
        node_obj.result = result
        node_obj.save(update_fields=["result"])


def _batch_advance_step(nodes, status, message, details=None, next_steps=None):
    timestamp = now_iso()
    for node_obj in nodes:
        result = node_obj.result or {}
        advance_step(
            result,
            status,
            message,
            details=details,
            next_steps=next_steps,
            timestamp=timestamp,
        )
        node_obj.result = result
        node_obj.save(update_fields=["result"])


def _batch_update_step_status(nodes, status, message, details=None):
    """批量更新多个节点最后一个步骤的状态并立即持久化"""
    for node_obj in nodes:
        result = node_obj.result or {}
        if update_last_running_step(
            result,
            status,
            message,
            details=details,
            timestamp=now_iso(),
        ):
            node_obj.result = result
            node_obj.save(update_fields=["result"])


def _save_node_result(node_obj, overall_status, final_message):
    """保存节点最终执行结果"""
    result = node_obj.result or {}
    result = apply_result_envelope(
        result,
        overall_status=normalize_overall_status(overall_status),
        final_message=final_message,
        failure=_extract_latest_failure_from_steps(result.get("steps")),
    )
    result[InstallerConstants.EXECUTION_PHASE_KEY] = InstallerConstants.EXECUTION_PHASE_FINISHED
    result["installer_progress"] = summarize_installer_progress(result)
    node_obj.status = "success" if result["overall_status"] == InstallerConstants.OVERALL_STATUS_SUCCESS else "error"
    node_obj.result = result
    node_obj.save(update_fields=["status", "result"])


def _save_node_pending_connectivity(node_obj, final_message):
    """保存节点待连通确认状态"""
    result = apply_result_envelope(
        node_obj.result or {},
        overall_status=InstallerConstants.OVERALL_STATUS_RUNNING,
        final_message=final_message,
    )
    result[InstallerConstants.EXECUTION_PHASE_KEY] = InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING
    result["installer_progress"] = summarize_installer_progress(result)
    node_obj.status = InstallerConstants.STEP_STATUS_RUNNING
    node_obj.result = result
    node_obj.save(update_fields=["status", "result"])


def _refresh_installer_progress(node_obj):
    result = node_obj.result or {}
    result["installer_progress"] = summarize_installer_progress(result)
    node_obj.result = result
    node_obj.save(update_fields=["result"])


def _finalize_non_connectivity_running_steps(node_obj, message="Installer bootstrap completed"):
    result = node_obj.result or {}
    steps = result.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return False

    updated = False
    timestamp = now_iso()
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("status") != InstallerConstants.STEP_STATUS_RUNNING:
            continue
        if step.get("action") == "connectivity_check":
            continue
        step["status"] = InstallerConstants.STEP_STATUS_SUCCESS
        step["message"] = message if step.get("action") == "run" else (step.get("message") or message)
        step["timestamp"] = timestamp
        updated = True

    if not updated:
        return False

    result["steps"] = steps
    result["installer_progress"] = summarize_installer_progress(result)
    node_obj.result = result
    node_obj.save(update_fields=["result"])
    return True


def _dispatch_or_finalize_controller_task(task_id: int):
    dispatch_items = []

    with transaction.atomic(using="default"):
        task_obj = ControllerTask.objects.select_for_update().filter(id=task_id).first()
        if not task_obj or task_obj.type != "install":
            return

        task_nodes = list(ControllerTaskNode.objects.filter(task_id=task_id).order_by("id"))
        bootstrap_running_count = sum(
            1
            for node in task_nodes
            if node.status == InstallerConstants.STEP_STATUS_RUNNING
            and _get_execution_phase(node) == InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING
        )
        waiting_nodes = [node for node in task_nodes if node.status == InstallerConstants.STEP_STATUS_WAITING]

        available_slots = max(
            InstallerConstants.CONTROLLER_INSTALL_MAX_PARALLEL - bootstrap_running_count,
            0,
        )

        for node_obj in waiting_nodes[:available_slots]:
            attempt = _get_execution_attempt(node_obj)
            result = node_obj.result or {}
            result[InstallerConstants.EXECUTION_PHASE_KEY] = InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING
            result[InstallerConstants.EXECUTION_ATTEMPT_KEY] = attempt
            node_obj.status = InstallerConstants.STEP_STATUS_RUNNING
            node_obj.result = result
            node_obj.save(update_fields=["status", "result"])
            dispatch_items.append((node_obj.id, attempt))

        task_obj.status = "running" if any(node.status in ["waiting", "running"] for node in task_nodes) else "finished"
        task_obj.save(update_fields=["status"])

        if dispatch_items:
            transaction.on_commit(
                lambda items=dispatch_items: [install_controller_for_node.delay(task_node_id, attempt) for task_node_id, attempt in items]
            )


def _parse_exception_details(error_message, exception_obj=None):
    """解析异常详情，提取结构化错误信息"""
    import json
    import re

    details = {
        "exception_type": type(exception_obj).__name__ if exception_obj else "Unknown",
        "error_message": str(exception_obj) if exception_obj else error_message,
    }

    if exception_obj:
        error_str = str(exception_obj)

        json_match = re.search(r'{.*"success".*}', error_str)
        if json_match:
            try:
                go_response = json.loads(json_match.group())
                if isinstance(go_response, dict) and not go_response.get("success", True):
                    if "error" in go_response:
                        details["service_error"] = go_response["error"]
                    if "result" in go_response:
                        details["command_output"] = go_response["result"]
                    if "instance_id" in go_response:
                        details["instance_id"] = go_response["instance_id"]

                    error_text = go_response.get("error", "").lower()
                    if "exit code" in error_text:
                        exit_code_match = re.search(r"exit code (\d+)", error_text)
                        if exit_code_match:
                            details["exit_code"] = int(exit_code_match.group(1))

                    if "timed out" in error_text:
                        details["error_type"] = "timeout"
                    elif "ssh client" in error_text or "connection" in error_text:
                        details["error_type"] = "connection"
                    elif "command execution failed" in error_text:
                        details["error_type"] = "execution"

            except (json.JSONDecodeError, KeyError):
                pass

    return details


def _handle_step_exception(node_obj, error_message, exception_obj=None, timestamp=None):
    """处理步骤执行异常并立即持久化"""
    details = _parse_exception_details(error_message, exception_obj)
    failure = normalize_failure(message=error_message, error=str(exception_obj) if exception_obj else error_message, details=details)
    if failure:
        details["failure"] = failure
    if "error_type" in details and details["error_type"] == "timeout":
        details["timeout"] = True

    result = node_obj.result or {}
    steps = result.get("steps", [])

    if steps and steps[-1]["status"] == "running":
        _update_step_status(node_obj, "error", f"Step failed: {error_message}", details)
    else:
        _add_step(
            node_obj,
            "unknown",
            "error",
            f"Unexpected error: {error_message}",
            timestamp,
            details,
        )


def install_controller_on_nodes(task_obj, nodes, package_obj):
    """安装控制器任务调度入口"""
    aes_obj = AESCryptor()
    nodes_list = list(nodes)

    for node_obj in nodes_list:
        overall_status = "success"

        has_password = bool(node_obj.password)
        has_private_key = bool(node_obj.private_key)

        if not has_password and not has_private_key:
            _add_step(
                node_obj,
                "credential_check",
                "error",
                "No authentication method provided. Password or private key is required.",
            )
            _save_node_result(node_obj, "error", "Credential validation failed")
            continue

        auth_method = "private key" if has_private_key else "password"
        _add_steps(
            node_obj,
            [
                _build_step(
                    "credential_check",
                    "success",
                    f"Validate credentials ({auth_method})",
                ),
                _build_step("run", "running", "Run installer"),
            ],
        )

        password = None
        if has_password:
            password = aes_obj.decode(node_obj.password)

        private_key = None
        if has_private_key:
            private_key = aes_obj.decode(node_obj.private_key)

        passphrase = None
        if node_obj.passphrase:
            passphrase = aes_obj.decode(node_obj.passphrase)

        try:
            resolved_package = package_obj
            resolved_arch = normalize_cpu_architecture(node_obj.cpu_architecture)
            if package_obj.os == NodeConstants.LINUX_OS and not resolved_arch:
                _update_step_status_by_action(
                    node_obj,
                    "run",
                    "running",
                    "Detect target CPU architecture",
                    details={"cpu_architecture": "detecting"},
                )
                detect_output = exec_command_to_remote(
                    task_obj.work_node,
                    node_obj.ip,
                    node_obj.username,
                    password,
                    "uname -m",
                    node_obj.port,
                    private_key=private_key,
                    passphrase=passphrase,
                )
                resolved_arch = normalize_cpu_architecture(str(detect_output).strip())
                if not resolved_arch:
                    raise BaseAppException("Failed to detect target CPU architecture")
                node_obj.cpu_architecture = resolved_arch
                node_obj.save(update_fields=["cpu_architecture"])

            if resolved_arch:
                resolved_package = InstallerService.resolve_package_by_architecture(
                    task_obj.package_version_id,
                    resolved_arch,
                )
                node_obj.resolved_package_version_id = resolved_package.id
                node_obj.save(update_fields=["resolved_package_version_id"])

            _update_step_status_by_action(
                node_obj,
                "run",
                "running",
                "Run installer",
                details={
                    "cpu_architecture": resolved_arch or "",
                    "resolved_package_version_id": node_obj.resolved_package_version_id or resolved_package.id,
                },
            )

            install_command = InstallerService.get_install_command(
                task_obj.created_by,
                node_obj.ip,
                uuid.uuid4().hex,
                resolved_package.os,
                resolved_package.id,
                task_obj.cloud_region_id,
                node_obj.organizations,
                node_obj.node_name,
                install_mode=InstallerService.AUTO_INSTALL_MODE,
                cpu_architecture=resolved_arch,
            )

            if resolved_package.os == NodeConstants.LINUX_OS:
                install_command = f'sh -lc "{install_command}"'
            exec_result = None
            if resolved_package.os == NodeConstants.LINUX_OS:
                execution_id = uuid.uuid4().hex
                stream_log_topic = f"executor.stream.{execution_id}"
                stop_event = threading.Event()
                result_queue, subscribe_runner = subscribe_lines_sync(
                    stream_log_topic,
                    timeout=InstallerConstants.COMMAND_EXECUTE_TIMEOUT,
                    stop_event=stop_event,
                )
                subscribe_thread = threading.Thread(target=subscribe_runner, daemon=True)
                consume_thread = threading.Thread(
                    target=_consume_installer_stream,
                    args=(node_obj, result_queue, stop_event),
                    daemon=True,
                )
                subscribe_thread.start()
                consume_thread.start()
                try:
                    exec_result = exec_command_to_remote_stream(
                        task_obj.work_node,
                        node_obj.ip,
                        node_obj.username,
                        password,
                        install_command,
                        node_obj.port,
                        private_key=private_key,
                        passphrase=passphrase,
                        execution_id=execution_id,
                        stream_log_topic=stream_log_topic,
                    )
                finally:
                    stop_event.set()
                    subscribe_thread.join(timeout=2)
                    consume_thread.join(timeout=2)
            else:
                exec_result = exec_command_to_remote(
                    task_obj.work_node,
                    node_obj.ip,
                    node_obj.username,
                    password,
                    install_command,
                    node_obj.port,
                    private_key=private_key,
                    passphrase=passphrase,
                )
            installer_output = ""
            if isinstance(exec_result, dict):
                installer_output = exec_result.get("result") or exec_result.get("output") or ""
            elif isinstance(exec_result, str):
                installer_output = exec_result
            elif exec_result is not None:
                installer_output = str(exec_result)

            _apply_installer_events_to_node(node_obj, installer_output)
            _finalize_non_connectivity_running_steps(node_obj)
            _advance_step(
                node_obj,
                "success",
                "Installer bootstrap completed",
                next_steps=[
                    _build_step(
                        "connectivity_check",
                        "running",
                        "Wait for node connection",
                    )
                ],
            )

        except Exception as e:
            _handle_step_exception(node_obj, str(e), e)
            overall_status = "error"

        if overall_status == "success":
            _save_node_pending_connectivity(
                node_obj,
                "Installation command succeeded, waiting connectivity confirmation",
            )
        else:
            _save_node_result(node_obj, "error", "Installation failed")

        _dispatch_or_finalize_controller_task(task_obj.id)


@shared_task
def install_controller(task_id):
    """安装控制器"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise BaseAppException("Task not found")
    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise BaseAppException("Package version not found")

    task_obj.status = "running"
    task_obj.save()

    _dispatch_or_finalize_controller_task(task_id)


@shared_task
def install_controller_for_node(task_node_id, attempt):
    task_node = ControllerTaskNode.objects.filter(id=task_node_id).first()
    if not task_node:
        return

    if _get_execution_attempt(task_node) != attempt:
        return

    if _get_execution_phase(task_node) != InstallerConstants.EXECUTION_PHASE_BOOTSTRAP_RUNNING:
        return

    task_obj = ControllerTask.objects.filter(id=task_node.task_id).first()
    if not task_obj:
        return

    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        _add_step(task_node, "prepare", "error", "Package version not found")
        _save_node_result(task_node, "error", "Package version not found")
        _dispatch_or_finalize_controller_task(task_node.task_id)
        return

    try:
        install_controller_on_nodes(task_obj, [task_node], package_obj)
    finally:
        ControllerTaskNode.objects.filter(
            id=task_node.id,
            result__execution_attempt=attempt,
        ).update(password="", private_key="", passphrase="")
        _dispatch_or_finalize_controller_task(task_node.task_id)


@shared_task
def converge_controller_install_connectivity_for_node(node_id):
    """根据 sidecar 回调收敛控制器安装任务连通状态"""
    node = Node.objects.filter(id=node_id).first()
    if not node:
        return

    running_task_nodes = ControllerTaskNode.objects.filter(
        ip=node.ip,
        status="running",
        task__type="install",
    ).select_related("task")

    affected_task_ids = set()

    for task_node in running_task_nodes:
        if _get_execution_phase(task_node) != InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING:
            continue

        result = task_node.result or {}
        steps = result.get("steps", [])
        if not steps:
            continue

        last_step = steps[-1]
        if not (last_step.get("action") == "connectivity_check" and last_step.get("status") == "running"):
            continue

        _update_step_status(
            task_node,
            "success",
            "Sidecar connectivity confirmed",
        )
        _finalize_non_connectivity_running_steps(task_node)
        _save_node_result(task_node, "success", "All steps completed successfully")
        affected_task_ids.add(task_node.task_id)

    for task_id in affected_task_ids:
        _dispatch_or_finalize_controller_task(task_id)


@shared_task
def timeout_controller_install_task(task_id):
    """控制器安装任务连通检测超时兜底"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        return

    if task_obj.type != "install":
        return

    if task_obj.status not in ["waiting", "running"]:
        return

    pending_nodes = ControllerTaskNode.objects.filter(
        task_id=task_id,
        status="running",
    )

    for task_node in pending_nodes:
        if _get_execution_phase(task_node) != InstallerConstants.EXECUTION_PHASE_CONNECTIVITY_WAITING:
            continue

        result = task_node.result or {}
        steps = result.get("steps", [])
        if not steps:
            continue

        last_step = steps[-1]
        if not (last_step.get("action") == "connectivity_check" and last_step.get("status") == "running"):
            continue

        _update_step_status(
            task_node,
            "error",
            "Connectivity check timeout",
            details={
                "timeout": True,
                "failure": normalize_failure(
                    message="Connectivity check timeout",
                    details={"error_type": "timeout"},
                ),
            },
        )
        _finalize_non_connectivity_running_steps(task_node)
        _save_node_result(task_node, "error", "Connectivity check timeout")

    _dispatch_or_finalize_controller_task(task_id)


@shared_task
def retry_controller(task_id, task_node_ids, password=None, private_key=None, passphrase=None):
    """
    重试控制器安装任务中的特定节点

    Args:
        task_id: 控制器任务ID
        task_node_ids: 需要重试的节点ID列表（支持单个或多个）
        password: 节点密码（明文，将被加密后存储，可选）
        private_key: SSH私钥（PEM格式，将被加密后存储，可选）
        passphrase: 私钥密码短语（明文，将被加密后存储，可选）
    """

    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise BaseAppException("Task not found")

    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise BaseAppException("Package version not found")

    # 确保 task_node_ids 是列表
    if not isinstance(task_node_ids, list):
        task_node_ids = [task_node_ids]

    # 获取需要重试的节点
    retry_nodes = ControllerTaskNode.objects.filter(id__in=task_node_ids, task_id=task_id)

    if not retry_nodes.exists():
        raise BaseAppException("No valid nodes found for retry")

    # 加密并更新到节点
    aes_obj = AESCryptor()
    update_data = {}

    if password:
        update_data["password"] = aes_obj.encode(password)
    if private_key:
        update_data["private_key"] = aes_obj.encode(private_key)
    if passphrase:
        update_data["passphrase"] = aes_obj.encode(passphrase)

    if update_data:
        retry_nodes.update(**update_data)

    for retry_node in retry_nodes:
        next_attempt = _get_execution_attempt(retry_node) + 1
        retry_node.status = InstallerConstants.STEP_STATUS_WAITING
        retry_node.result = {
            InstallerConstants.EXECUTION_ATTEMPT_KEY: next_attempt,
        }
        retry_node.save(update_fields=["status", "result"])

    _dispatch_or_finalize_controller_task(task_id)


@shared_task
def uninstall_controller(task_id):
    """卸载控制器"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        return
    task_obj.status = "running"
    task_obj.save()

    nodes = task_obj.controllertasknode_set.all()
    aes_obj = AESCryptor()

    for node_obj in nodes:
        overall_status = "success"

        has_password = bool(node_obj.password)
        has_private_key = bool(node_obj.private_key)

        if not has_password and not has_private_key:
            _add_step(
                node_obj,
                "credential_check",
                "error",
                "No authentication method provided. Password or private key is required.",
            )
            _save_node_result(node_obj, "error", "Credential validation failed")
            continue

        auth_method = "private key" if has_private_key else "password"
        _add_steps(
            node_obj,
            [
                _build_step(
                    "credential_check",
                    "success",
                    f"Validate credentials ({auth_method})",
                ),
                _build_step("stop_run", "running", "Stop controller service"),
            ],
        )

        password = None
        if has_password:
            password = aes_obj.decode(node_obj.password)

        private_key = None
        if has_private_key:
            private_key = aes_obj.decode(node_obj.private_key)

        passphrase = None
        if node_obj.passphrase:
            passphrase = aes_obj.decode(node_obj.passphrase)

        try:
            uninstall_command = get_uninstall_command(node_obj.os)
            exec_command_to_remote(
                task_obj.work_node,
                node_obj.ip,
                node_obj.username,
                password,
                uninstall_command,
                node_obj.port,
                private_key=private_key,
                passphrase=passphrase,
            )
            _advance_step(
                node_obj,
                "success",
                "Controller service stopped",
                next_steps=[
                    _build_step(
                        "delete_dir",
                        "running",
                        "Remove installation directory",
                    )
                ],
            )
            exec_command_to_remote(
                task_obj.work_node,
                node_obj.ip,
                node_obj.username,
                password,
                ControllerConstants.CONTROLLER_DIR_DELETE_COMMAND.get(node_obj.os),
                node_obj.port,
                private_key=private_key,
                passphrase=passphrase,
            )
            _advance_step(
                node_obj,
                "success",
                "Installation directory removed",
                next_steps=[_build_step("delete_node", "running", "Remove node record")],
            )
            Node.objects.filter(cloud_region_id=task_obj.cloud_region_id, ip=node_obj.ip).delete()
            _update_step_status(node_obj, "success", "Node record removed")

        except Exception as e:
            _handle_step_exception(node_obj, str(e), e)
            overall_status = "error"

        final_message = "Controller uninstallation completed" if overall_status == "success" else "Controller uninstallation failed"
        _save_node_result(node_obj, overall_status, final_message)

    task_obj.status = "finished"
    task_obj.save()
    nodes.update(password="", private_key="", passphrase="")


@shared_task
def install_collector(task_id):
    """安装采集器"""
    task_obj = CollectorTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise BaseAppException("Task not found")
    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise BaseAppException("Package version not found")

    file_key = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
    task_obj.status = "running"
    task_obj.save()

    collector_install_dir = CollectorConstants.DOWNLOAD_DIR.get(package_obj.os)
    nodes = task_obj.collectortasknode_set.all()

    for node_obj in nodes:
        overall_status = "success"

        try:
            _add_step(
                node_obj,
                "download",
                "running",
                "Download collector package",
            )
            download_to_local(
                node_obj.node_id,
                NATS_NAMESPACE,
                file_key,
                package_obj.name,
                collector_install_dir,
            )
            if package_obj.name.lower().endswith(".zip"):
                _advance_step(
                    node_obj,
                    "success",
                    "Collector package downloaded",
                    next_steps=[_build_step("unzip", "running", "Extract collector package")],
                )
                unzip_name = unzip_file(
                    node_obj.node_id,
                    f"{collector_install_dir}/{package_obj.name}",
                    collector_install_dir,
                )
                executable_name = unzip_name
                if package_obj.os in NodeConstants.LINUX_OS:
                    _advance_step(
                        node_obj,
                        "success",
                        "Collector package extracted",
                        next_steps=[
                            _build_step(
                                "set_executable",
                                "running",
                                "Set executable permissions",
                            )
                        ],
                    )
                else:
                    _update_step_status(
                        node_obj,
                        "success",
                        "Collector package extracted",
                    )
            else:
                executable_name = package_obj.name
                next_steps = [
                    _build_step(
                        "prepare",
                        "success",
                        "Package ready",
                    )
                ]
                if package_obj.os in NodeConstants.LINUX_OS:
                    next_steps.append(
                        _build_step(
                            "set_executable",
                            "running",
                            "Set executable permissions",
                        )
                    )
                _advance_step(
                    node_obj,
                    "success",
                    "Collector package downloaded",
                    next_steps=next_steps,
                )

            if package_obj.os in NodeConstants.LINUX_OS:
                executable_path = f"{collector_install_dir}/{executable_name}"
                exec_command_to_local(
                    node_obj.node_id,
                    f"if [ -d '{executable_path}' ]; then find '{executable_path}' -type f -exec chmod +x {{}} \\; ; else chmod +x '{executable_path}'; fi",
                )
                _update_step_status(node_obj, "success", "Executable permissions updated")

        except Exception as e:
            _handle_step_exception(node_obj, str(e), e)
            overall_status = "error"

        final_message = "Collector installation completed" if overall_status == "success" else "Collector installation failed"
        _save_node_result(node_obj, overall_status, final_message)

        collector_obj = Collector.objects.filter(node_operating_system=package_obj.os, name=package_obj.object).first()
        NodeCollectorInstallStatus.objects.update_or_create(
            node_id=node_obj.node_id,
            collector_id=collector_obj.id,
            defaults={
                "node_id": node_obj.node_id,
                "collector_id": collector_obj.id,
                "status": "success" if overall_status == "success" else "error",
                "result": node_obj.result,
            },
        )

    task_obj.status = "finished"
    task_obj.save()


@shared_task
def uninstall_collector(task_id):
    """卸载采集器"""
    pass
