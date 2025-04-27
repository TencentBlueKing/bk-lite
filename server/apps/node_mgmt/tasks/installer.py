from celery import shared_task

from apps.node_mgmt.constants import CONTROLLER_INSTALL_DIR, COLLECTOR_INSTALL_DIR, LINUX_OS, \
    CONTROLLER_DIR_DELETE_COMMAND
from apps.node_mgmt.models import ControllerTask, CollectorTask, PackageVersion, Node
from apps.node_mgmt.utils.installer import download_to_remote, exec_command_to_remote, download_to_local, \
    exec_command_to_local, get_install_command, get_uninstall_command
from config.components.nats import NATS_NAMESPACE


@shared_task
def install_controller(task_id):
    """安装控制器"""
    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise ValueError("Task not found")
    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise ValueError("Package version not found")
    file_key = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
    task_obj.status = "running"
    task_obj.save()

    # 获取所有节点
    nodes = task_obj.controllertasknode_set.all()

    # 获取控制器下发目录
    controller_install_dir = CONTROLLER_INSTALL_DIR.get(package_obj.os)

    # 获取安装命令
    install_command = get_install_command(package_obj.os, package_obj.name, task_obj.cloud_region_id)

    for node_obj in nodes:
        try:
            # 控制器压缩包下发
            download_to_remote(
                task_obj.work_node,
                NATS_NAMESPACE,
                file_key,
                package_obj.name,
                controller_install_dir,
                node_obj.ip,
                node_obj.username,
                node_obj.password,
            )
            node_obj.result.update(send={"status": "success"})
            # 解压包，并执行运行脚步
            exec_command_to_remote(task_obj.work_node, node_obj.ip, node_obj.username, node_obj.password, install_command)
            node_obj.result.update(run={"status": "success"})
        except Exception as e:
            if "send" not in node_obj.result:
                node_obj.result.update(send={"status": "failed", "message": str(e)})
            elif "run" not in node_obj.result:
                node_obj.result.update(run={"status": "failed", "message": str(e)})

        node_obj.save()

    # 更新任务状态
    task_obj.status = "finished"
    task_obj.save()


@shared_task
def uninstall_controller(task_id):
    """卸载控制器"""

    task_obj = ControllerTask.objects.filter(id=task_id).first()
    if not task_obj:
        return
    task_obj.status = "running"
    task_obj.save()

    # 获取所有节点
    nodes = task_obj.controllertasknode_set.all()
    for node_obj in nodes:
        try:
            # 获取卸载命令
            uninstall_command = get_uninstall_command(node_obj.os)
            # 执行卸载脚步
            exec_command_to_remote(task_obj.work_node, node_obj.ip, node_obj.username, node_obj.password, uninstall_command)
            node_obj.result.update(stop_run={"status": "success"})

            # 删除控制器安装目录
            exec_command_to_remote(
                task_obj.work_node,
                node_obj.ip,
                node_obj.username,
                node_obj.password,
                CONTROLLER_DIR_DELETE_COMMAND.get(node_obj.os),
            )
            node_obj.result.update(delete_dir={"status": "success"})

            # 删除node实例
            Node.objects.filter(cloud_region_id=task_obj.cloud_region_id, ip=node_obj.ip).delete()
            node_obj.result.update(delete_node={"status": "success"})

        except Exception as e:

            if "stop_run" not in node_obj.result:
                node_obj.result.update(stop_run={"status": "failed", "message": str(e)})
            elif "delete_dir" not in node_obj.result:
                node_obj.result.update(delete_dir={"status": "failed", "message": str(e)})
            elif "delete_node" not in node_obj.result:
                node_obj.result.update(delete_node={"status": "failed", "message": str(e)})

        node_obj.save()

    # 更新任务状态
    task_obj.status = "finished"
    task_obj.save()


@shared_task
def install_collector(task_id):
    """安装采集器"""
    task_obj = CollectorTask.objects.filter(id=task_id).first()
    if not task_obj:
        raise ValueError("Task not found")
    package_obj = PackageVersion.objects.filter(id=task_obj.package_version_id).first()
    if not package_obj:
        raise ValueError("Package version not found")
    file_key = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
    task_obj.status = "running"
    task_obj.save()

    # 获取采集器下发目录
    collector_install_dir = COLLECTOR_INSTALL_DIR.get(package_obj.os)

    # 获取所有节点
    nodes = task_obj.collectortasknode_set.all()
    for node_obj in nodes:
        try:
            # 下发采集器
            download_to_local(
                node_obj.node_id,
                NATS_NAMESPACE,
                file_key,
                package_obj.name,
                collector_install_dir,
            )
            node_obj.result.update(send={"status": "success"})
            # Linux操作系统赋予执行权限
            if package_obj.os in LINUX_OS:
                exec_command_to_local(node_obj.node_id, f"chmod +x {collector_install_dir}/{package_obj.name}")
                node_obj.result.update(set_exe={"status": "success"})
            else:
                node_obj.result.update(set_exe={"status": "success"})
        except Exception as e:
            node_obj.result.update(send={"status": "failed", "message": str(e)})

        node_obj.save()

    # 更新任务状态
    task_obj.status = "finished"
    task_obj.save()


@shared_task
def uninstall_collector(task_id):
    """卸载采集器"""
    pass
