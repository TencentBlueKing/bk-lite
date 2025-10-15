import uuid
from datetime import datetime

from celery import shared_task

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants

from apps.node_mgmt.models import ControllerTask, CollectorTask, PackageVersion, Node, NodeCollectorInstallStatus, \
    Collector, SidecarEnv
from apps.node_mgmt.utils.installer import exec_command_to_remote, download_to_local, \
    exec_command_to_local, get_install_command, get_uninstall_command, unzip_file, transfer_file_to_remote
from apps.node_mgmt.utils.token_auth import generate_node_token
from config.components.nats import NATS_NAMESPACE


def _add_step(steps, action, status, message, timestamp=None, details=None):
    """添加执行步骤记录"""
    step = {
        "action": action,
        "status": status,
        "message": message,
        "timestamp": timestamp or datetime.now().isoformat()
    }
    # 添加详细信息，特别是错误详情
    if details:
        step["details"] = details
    steps.append(step)


def _update_step_status(steps, status, message, details=None):
    """更新最后一个步骤的状态"""
    if steps and steps[-1]["status"] == "running":
        steps[-1]["status"] = status
        steps[-1]["message"] = message
        if details:
            steps[-1]["details"] = details


def _save_node_result(node_obj, steps, overall_status, final_message):
    """保存节点执行结果"""
    node_obj.status = "success" if overall_status == "success" else "error"
    node_obj.result = {
        "steps": steps,
        "overall_status": overall_status,
        "final_message": final_message
    }
    node_obj.save()


def _handle_step_exception(steps, error_message, exception_obj=None, timestamp=None):
    """处理步骤执行异常"""
    import json
    import re

    details = {
        "exception_type": type(exception_obj).__name__ if exception_obj else "Unknown",
        "error_message": str(exception_obj) if exception_obj else error_message,
    }

    if exception_obj:
        error_str = str(exception_obj)

        # 尝试解析Go服务的JSON错误响应
        json_match = re.search(r'{.*"success".*}', error_str)
        if json_match:
            try:
                go_response = json.loads(json_match.group())
                if isinstance(go_response, dict) and not go_response.get("success", True):
                    # 提取Go服务的关键错误信息
                    if "error" in go_response:
                        details["service_error"] = go_response["error"]
                    if "result" in go_response:
                        details["command_output"] = go_response["result"]
                    if "instance_id" in go_response:
                        details["instance_id"] = go_response["instance_id"]

                    # 简单的错误分类
                    error_text = go_response.get("error", "").lower()
                    if "exit code" in error_text:
                        exit_code_match = re.search(r'exit code (\d+)', error_text)
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

    # 更新步骤状态
    if steps and steps[-1]["status"] == "running":
        _update_step_status(steps, "error", f"Step failed: {error_message}", details)
    else:
        _add_step(steps, "unknown", "error", f"Unexpected error: {error_message}", timestamp, details)


@shared_task
def install_controller(task_id):
    """安装控制器"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise BaseAppException("Task not found")
    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise BaseAppException("Package version not found")

    file_key = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
    task_obj.status = "running"
    task_obj.save()

    # 获取所有节点
    nodes = task_obj.controllertasknode_set.all()

    # 获取控制器下发目录
    dir_map = ControllerConstants.CONTROLLER_INSTALL_DIR.get(package_obj.os)
    controller_install_dir, controller_storage_dir = dir_map["install_dir"], dir_map["storage_dir"]

    # 获取安装命令所需参数
    obj = SidecarEnv.objects.filter(cloud_region=task_obj.cloud_region_id, key=NodeConstants.SERVER_URL_KEY).first()
    server_url = obj.value if obj else "null"

    # 基础准备工作
    base_action, base_massage, unzip_name, base_run = "", "", "", True
    try:
        base_action = "download"
        download_to_local(task_obj.work_node, NATS_NAMESPACE, file_key, package_obj.name, controller_storage_dir)

        base_action = "unzip"
        unzip_name = unzip_file(task_obj.work_node, f"{controller_storage_dir}/{package_obj.name}", controller_storage_dir)
    except Exception as e:
        base_run = False
        base_massage = str(e)

    aes_obj = AESCryptor()
    timestamp = task_obj.updated_at.isoformat() if task_obj.updated_at else datetime.now().isoformat()

    for node_obj in nodes:
        steps = []
        overall_status = "success"

        # 检查基础准备是否成功
        if not base_run:
            _add_step(steps, base_action, "error", base_massage, timestamp)
            _save_node_result(node_obj, steps, "error", f"Base preparation failed at {base_action}")
            continue

        # 检查凭据有效性
        if not node_obj.password:
            _add_step(steps, "credential_check", "error",
                     "Node password is empty, credential has expired. Cannot proceed with installation.", timestamp)
            _save_node_result(node_obj, steps, "error", "Credential validation failed")
            continue

        # 凭据验证成功
        _add_step(steps, "credential_check", "success", "Credential validation passed", timestamp)
        password = aes_obj.decode(node_obj.password)

        try:
            # 文件传输步骤
            _add_step(steps, "send", "running", "Starting file transfer to remote host", timestamp)
            transfer_file_to_remote(task_obj.work_node, f"{controller_storage_dir}/{unzip_name}",
                                  controller_install_dir, node_obj.ip, node_obj.username, password, node_obj.port)
            _update_step_status(steps, "success", "File transfer completed successfully")

            # 安装执行步骤
            _add_step(steps, "run", "running", "Starting controller installation", timestamp)
            groups = ",".join([str(i) for i in node_obj.organizations])

            # token生成
            node_id = uuid.uuid4().hex
            sidecar_token = generate_node_token(node_id, node_obj.ip, task_obj.created_by)
            install_command = get_install_command(package_obj.os, package_obj.name, task_obj.cloud_region_id,
                                                sidecar_token, server_url, groups, node_obj.node_name, node_id)

            exec_command_to_remote(task_obj.work_node, node_obj.ip, node_obj.username, password, install_command, node_obj.port)
            _update_step_status(steps, "success", "Controller installation completed successfully")

        except Exception as e:
            _handle_step_exception(steps, str(e), e, timestamp)
            overall_status = "error"

        # 保存结果
        final_message = "All steps completed successfully" if overall_status == "success" else "Installation failed"
        _save_node_result(node_obj, steps, overall_status, final_message)

    # 更新任务状态并清理密码
    task_obj.status = "finished"
    task_obj.save()
    nodes.update(password="")


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
    timestamp = task_obj.updated_at.isoformat() if task_obj.updated_at else datetime.now().isoformat()

    for node_obj in nodes:
        steps = []
        overall_status = "success"

        # 检查凭据有效性
        if not node_obj.password:
            _add_step(steps, "credential_check", "error",
                     "Node password is empty, credential has expired. Cannot proceed with uninstallation.", timestamp)
            _save_node_result(node_obj, steps, "error", "Credential validation failed")
            continue

        # 凭据验证成功
        _add_step(steps, "credential_check", "success", "Credential validation passed", timestamp)
        password = aes_obj.decode(node_obj.password)

        try:
            # 停止服务步骤
            _add_step(steps, "stop_run", "running", "Stopping controller service", timestamp)
            uninstall_command = get_uninstall_command(node_obj.os)
            exec_command_to_remote(task_obj.work_node, node_obj.ip, node_obj.username, password, uninstall_command, node_obj.port)
            _update_step_status(steps, "success", "Controller service stopped successfully")

            # 删除控制器安装目录步骤
            _add_step(steps, "delete_dir", "running", "Removing controller installation directory", timestamp)
            exec_command_to_remote(task_obj.work_node, node_obj.ip, node_obj.username, password,
                                 ControllerConstants.CONTROLLER_DIR_DELETE_COMMAND.get(node_obj.os), node_obj.port)
            _update_step_status(steps, "success", "Installation directory removed successfully")

            # 删除node实例步骤
            _add_step(steps, "delete_node", "running", "Removing node from database", timestamp)
            Node.objects.filter(cloud_region_id=task_obj.cloud_region_id, ip=node_obj.ip).delete()
            _update_step_status(steps, "success", "Node removed from database successfully")

        except Exception as e:
            _handle_step_exception(steps, str(e), e, timestamp)
            overall_status = "error"

        # 保存结果
        final_message = "All steps completed successfully" if overall_status == "success" else "Uninstallation failed"
        _save_node_result(node_obj, steps, overall_status, final_message)

    # 更新任务状态并清理密码
    task_obj.status = "finished"
    task_obj.save()
    nodes.update(password="")


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
    timestamp = task_obj.updated_at.isoformat() if task_obj.updated_at else datetime.now().isoformat()

    for node_obj in nodes:
        steps = []
        overall_status = "success"

        try:
            # 下发采集器步骤
            _add_step(steps, "send", "running", f"Starting file download to node {node_obj.node_id}", timestamp)
            download_to_local(node_obj.node_id, NATS_NAMESPACE, file_key, package_obj.name, collector_install_dir)
            _update_step_status(steps, "success", "File download completed successfully")

            # 根据文件扩展名决定是否解压
            if package_obj.name.lower().endswith('.zip'):
                _add_step(steps, "unzip", "running", "Extracting collector package", timestamp)
                unzip_name = unzip_file(node_obj.node_id, f"{collector_install_dir}/{package_obj.name}", collector_install_dir)
                executable_name = unzip_name
                _update_step_status(steps, "success", f"Package extracted successfully: {unzip_name}")
            else:
                executable_name = package_obj.name
                _add_step(steps, "prepare", "success", "Package ready (no extraction required)", timestamp)

            # Linux操作系统赋予执行权限
            if package_obj.os in NodeConstants.LINUX_OS:
                _add_step(steps, "set_exe", "running", "Setting execution permissions", timestamp)
                executable_path = f"{collector_install_dir}/{executable_name}"
                exec_command_to_local(node_obj.node_id,
                    f"if [ -d '{executable_path}' ]; then find '{executable_path}' -type f -exec chmod +x {{}} \\; ; else chmod +x '{executable_path}'; fi")
                _update_step_status(steps, "success", "Execution permissions set successfully")

        except Exception as e:
            _handle_step_exception(steps, str(e), e, timestamp)
            overall_status = "error"

        # 保存结果
        final_message = "All steps completed successfully" if overall_status == "success" else "Collector installation failed"
        result = {
            "steps": steps,
            "overall_status": overall_status,
            "final_message": final_message
        }

        # 更新采集器安装状态
        collector_obj = Collector.objects.filter(node_operating_system=package_obj.os, name=package_obj.object).first()
        NodeCollectorInstallStatus.objects.update_or_create(
            node_id=node_obj.node_id,
            collector_id=collector_obj.id,
            defaults={
                "node_id": node_obj.node_id,
                "collector_id": collector_obj.id,
                "status": "success" if overall_status == "success" else "error",
                "result": result,
            },
        )

        node_obj.result = result
        node_obj.status = "success" if overall_status == "success" else "error"
        node_obj.save()

    # 更新任务状态
    task_obj.status = "finished"
    task_obj.save()


@shared_task
def uninstall_collector(task_id):
    """卸载采集器"""
    pass
