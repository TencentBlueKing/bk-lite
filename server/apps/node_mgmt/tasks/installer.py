import uuid

from celery import shared_task
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
    SidecarEnv,
)
from apps.node_mgmt.models import ControllerTaskNode

from apps.node_mgmt.utils.installer import (
    exec_command_to_remote,
    download_to_local,
    exec_command_to_local,
    get_install_command,
    get_uninstall_command,
    unzip_file,
    transfer_file_to_remote,
)
from apps.node_mgmt.utils.step_tracker import (
    advance_step,
    append_step,
    append_steps,
    build_step,
    clone_steps,
    now_iso,
    update_last_running_step,
)
from apps.node_mgmt.utils.token_auth import generate_node_token
from config.components.nats import NATS_NAMESPACE


CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS = InstallerConstants.CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS


def _add_steps(node_obj, step_items):
    result = node_obj.result or {}
    append_steps(result, clone_steps(step_items, timestamp=now_iso()))
    node_obj.result = result
    node_obj.save(update_fields=["result"])


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
    result["overall_status"] = overall_status
    result["final_message"] = final_message
    node_obj.status = "success" if overall_status == "success" else "error"
    node_obj.result = result
    node_obj.save(update_fields=["status", "result"])


def _save_node_pending_connectivity(node_obj, final_message):
    """保存节点待连通确认状态"""
    result = node_obj.result or {}
    result["overall_status"] = "running"
    result["final_message"] = final_message
    node_obj.status = "running"
    node_obj.result = result
    node_obj.save(update_fields=["status", "result"])


def _reconcile_controller_task_status(task_id):
    """根据节点状态收敛控制器任务状态"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        return

    running_or_waiting_exists = task_obj.controllertasknode_set.filter(status__in=["waiting", "running"]).exists()

    task_obj.status = "running" if running_or_waiting_exists else "finished"
    task_obj.save(update_fields=["status"])


def _reconcile_controller_task_statuses(task_ids):
    if not task_ids:
        return

    pending_by_task = {
        item["task_id"]: item["pending_count"]
        for item in ControllerTaskNode.objects.filter(task_id__in=task_ids)
        .values("task_id")
        .annotate(pending_count=Count("id", filter=Q(status__in=["waiting", "running"])))
    }

    running_ids = []
    finished_ids = []

    for task_id in task_ids:
        if pending_by_task.get(task_id, 0):
            running_ids.append(task_id)
        else:
            finished_ids.append(task_id)

    if running_ids:
        ControllerTask.objects.filter(id__in=running_ids).update(status="running")
    if finished_ids:
        ControllerTask.objects.filter(id__in=finished_ids).update(status="finished")


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
    file_key = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"

    dir_map = ControllerConstants.CONTROLLER_INSTALL_DIR.get(package_obj.os)
    controller_install_dir, controller_storage_dir = (
        dir_map["install_dir"],
        dir_map["storage_dir"],
    )

    obj = SidecarEnv.objects.filter(cloud_region=task_obj.cloud_region_id, key=NodeConstants.SERVER_URL_KEY).first()
    server_url = obj.value if obj else "null"

    aes_obj = AESCryptor()
    nodes_list = list(nodes)

    base_run = True
    base_error_message = ""
    unzip_name = ""

    _batch_add_step(nodes_list, "download", "running", "Downloading package to work node")
    try:
        download_to_local(
            task_obj.work_node,
            NATS_NAMESPACE,
            file_key,
            package_obj.name,
            controller_storage_dir,
        )
        _batch_advance_step(
            nodes_list,
            "success",
            "Package downloaded successfully",
            next_steps=[
                _build_step("unzip", "running", "Extracting package"),
            ],
        )
    except Exception as e:
        _batch_update_step_status(nodes_list, "error", f"Download failed: {str(e)}")
        base_run = False
        base_error_message = f"Download failed: {str(e)}"

    if base_run:
        try:
            unzip_name = unzip_file(
                task_obj.work_node,
                f"{controller_storage_dir}/{package_obj.name}",
                controller_storage_dir,
            )
            _batch_update_step_status(nodes_list, "success", "Package extracted successfully")
        except Exception as e:
            _batch_update_step_status(nodes_list, "error", f"Unzip failed: {str(e)}")
            base_run = False
            base_error_message = f"Unzip failed: {str(e)}"

    for node_obj in nodes_list:
        overall_status = "success"

        if not base_run:
            _save_node_result(node_obj, "error", base_error_message)
            continue

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
                    f"Credential validation passed (using {auth_method})",
                ),
                _build_step("prepare", "running", "Preparing remote directory"),
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
            remote_target_dir = f"{controller_install_dir}/{unzip_name}"
            exec_command_to_remote(
                task_obj.work_node,
                node_obj.ip,
                node_obj.username,
                password,
                f"mkdir -p {remote_target_dir}",
                node_obj.port,
                private_key=private_key,
                passphrase=passphrase,
            )
            _advance_step(
                node_obj,
                "success",
                "Remote directory prepared successfully",
                next_steps=[
                    _build_step(
                        "send",
                        "running",
                        "Starting file transfer to remote host",
                    )
                ],
            )
            transfer_file_to_remote(
                task_obj.work_node,
                f"{controller_storage_dir}/{unzip_name}",
                controller_install_dir,
                node_obj.ip,
                node_obj.username,
                password,
                node_obj.port,
                private_key=private_key,
                passphrase=passphrase,
            )
            _advance_step(
                node_obj,
                "success",
                "File transfer completed successfully",
                next_steps=[_build_step("run", "running", "Starting controller installation")],
            )
            groups = ",".join([str(i) for i in node_obj.organizations])

            node_id = uuid.uuid4().hex
            sidecar_token = generate_node_token(node_id, node_obj.ip, task_obj.created_by)
            install_command = get_install_command(
                package_obj.os,
                package_obj.name,
                task_obj.cloud_region_id,
                sidecar_token,
                server_url,
                groups,
                node_obj.node_name,
                node_id,
            )

            exec_command_to_remote(
                task_obj.work_node,
                node_obj.ip,
                node_obj.username,
                password,
                install_command,
                node_obj.port,
                private_key=private_key,
                passphrase=passphrase,
            )
            _advance_step(
                node_obj,
                "success",
                "Controller installation completed successfully",
                next_steps=[
                    _build_step(
                        "connectivity_check",
                        "running",
                        "Waiting for sidecar callback to confirm connectivity",
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

    # 获取所有节点
    nodes = task_obj.controllertasknode_set.all()
    # 安装控制器
    install_controller_on_nodes(task_obj, nodes, package_obj)

    # 根据节点收敛状态更新任务状态并清理密码
    _reconcile_controller_task_status(task_id)
    nodes.update(password="", private_key="", passphrase="")


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
        _save_node_result(task_node, "success", "All steps completed successfully")
        affected_task_ids.add(task_node.task_id)

    _reconcile_controller_task_statuses(affected_task_ids)


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
            details={"timeout": True},
        )
        _save_node_result(task_node, "error", "Connectivity check timeout")

    _reconcile_controller_task_status(task_id)


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

    # 调用安装方法
    install_controller_on_nodes(task_obj, retry_nodes, package_obj)

    # 清理密码和密钥
    retry_nodes.update(password="", private_key="", passphrase="")


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
                    f"Credential validation passed (using {auth_method})",
                ),
                _build_step("stop_run", "running", "Stopping controller service"),
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
                "Controller service stopped successfully",
                next_steps=[
                    _build_step(
                        "delete_dir",
                        "running",
                        "Removing controller installation directory",
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
                "Installation directory removed successfully",
                next_steps=[_build_step("delete_node", "running", "Removing node from database")],
            )
            Node.objects.filter(cloud_region_id=task_obj.cloud_region_id, ip=node_obj.ip).delete()
            _update_step_status(node_obj, "success", "Node removed from database successfully")

        except Exception as e:
            _handle_step_exception(node_obj, str(e), e)
            overall_status = "error"

        final_message = "All steps completed successfully" if overall_status == "success" else "Uninstallation failed"
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
                f"Starting file download to node {node_obj.node_id}",
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
                    "File download completed successfully",
                    next_steps=[_build_step("unzip", "running", "Extracting collector package")],
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
                        f"Package extracted successfully: {unzip_name}",
                        next_steps=[
                            _build_step(
                                "set_executable",
                                "running",
                                "Setting execution permissions",
                            )
                        ],
                    )
                else:
                    _update_step_status(
                        node_obj,
                        "success",
                        f"Package extracted successfully: {unzip_name}",
                    )
            else:
                executable_name = package_obj.name
                next_steps = [
                    _build_step(
                        "prepare",
                        "success",
                        "Package ready (no extraction required)",
                    )
                ]
                if package_obj.os in NodeConstants.LINUX_OS:
                    next_steps.append(
                        _build_step(
                            "set_executable",
                            "running",
                            "Setting execution permissions",
                        )
                    )
                _advance_step(
                    node_obj,
                    "success",
                    "File download completed successfully",
                    next_steps=next_steps,
                )

            if package_obj.os in NodeConstants.LINUX_OS:
                executable_path = f"{collector_install_dir}/{executable_name}"
                exec_command_to_local(
                    node_obj.node_id,
                    f"if [ -d '{executable_path}' ]; then find '{executable_path}' -type f -exec chmod +x {{}} \\; ; else chmod +x '{executable_path}'; fi",
                )
                _update_step_status(node_obj, "success", "Execution permissions set successfully")

        except Exception as e:
            _handle_step_exception(node_obj, str(e), e)
            overall_status = "error"

        final_message = "All steps completed successfully" if overall_status == "success" else "Collector installation failed"
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
