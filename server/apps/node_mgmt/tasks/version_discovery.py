from celery import shared_task

from apps.core.logger import logger
from apps.node_mgmt.models import Node, NodeComponentVersion, Controller
from apps.rpc.executor import Executor


@shared_task
def discover_node_versions():
    """
    定时任务：发现所有节点的控制器版本信息
    通过执行配置的版本命令获取版本信息
    """
    logger.info("开始执行节点控制器版本发现任务")

    nodes = Node.objects.all()
    success_count = 0
    failed_count = 0

    for node in nodes:
        try:
            _discover_controller_version(node)
            success_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"节点 {node.name}({node.ip}) 控制器版本发现失败: {str(e)}")

    logger.info(f"节点控制器版本发现任务完成，成功: {success_count}, 失败: {failed_count}")
    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "total": nodes.count()
    }


def _discover_controller_version(node: Node):
    """
    发现控制器版本信息
    从 Controller 模型中读取配置的 version_command
    """
    # 根据节点操作系统查询对应的控制器配置
    controller = Controller.objects.filter(os=node.operating_system, name="Controller").first()

    if not controller:
        logger.warning(f"节点 {node.name} 操作系统 {node.operating_system} 未找到对应的控制器配置")
        # 记录未找到配置的情况
        NodeComponentVersion.objects.update_or_create(
            node=node,
            component_type="controller",
            component_id="unknown",
            defaults={
                "version": "unknown",
                "message": f"未找到操作系统 {node.operating_system} 对应的控制器配置",
            }
        )
        return

    component_id = str(controller.id)

    try:

        # 检查是否配置了版本命令
        if not controller.version_command:
            logger.warning(f"控制器 {controller.name} 未配置版本命令")
            NodeComponentVersion.objects.update_or_create(
                node=node,
                component_type="controller",
                component_id=component_id,
                defaults={
                    "version": "unknown",
                    "message": "控制器未配置版本命令",
                }
            )
            return

        # 使用 Executor 执行版本命令
        executor = Executor(node.id)
        response = executor.execute_local(command=controller.version_command, timeout=10)

        if response and response.get("stdout"):
            version = response["stdout"].strip()
            exit_code = response.get("exit_code", -1)
            stderr = response.get("stderr", "")

            # 构建执行信息
            if exit_code == 0:
                message = "版本获取成功"
            else:
                message = f"命令执行返回非零状态码: {exit_code}"
                if stderr:
                    message += f", 错误输出: {stderr}"

            # 更新或创建控制器版本信息
            NodeComponentVersion.objects.update_or_create(
                node=node,
                component_type="controller",
                component_id=component_id,
                defaults={
                    "version": version if version else "unknown",
                    "message": message,
                }
            )
            logger.info(f"节点 {node.name} 控制器版本: {version} (exit_code: {exit_code})")
        else:
            # 记录获取失败的情况
            error_msg = "命令执行失败，未返回输出"
            if response:
                stderr = response.get("stderr", "")
                if stderr:
                    error_msg += f", 错误输出: {stderr}"

            NodeComponentVersion.objects.update_or_create(
                node=node,
                component_type="controller",
                component_id=component_id,
                defaults={
                    "version": "unknown",
                    "message": error_msg,
                }
            )
            logger.warning(f"节点 {node.name} 控制器版本获取失败: {error_msg}")

    except Exception as e:
        error_message = f"异常: {str(e)}"
        logger.error(f"获取节点 {node.name} 控制器版本失败: {error_message}")
        # 记录异常信息
        try:
            NodeComponentVersion.objects.update_or_create(
                node=node,
                component_type="controller",
                component_id=component_id,
                defaults={
                    "version": "unknown",
                    "message": error_message,
                }
            )
        except Exception as db_error:
            logger.error(f"保存版本信息异常记录失败: {str(db_error)}")
