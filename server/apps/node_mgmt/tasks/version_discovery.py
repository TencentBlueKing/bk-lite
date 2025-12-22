from celery import shared_task

from apps.core.logger import logger
from apps.node_mgmt.models import Node, NodeComponentVersion, Controller
from apps.rpc.executor import Executor
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.utils.version_utils import VersionUtils


@shared_task
def discover_node_versions():
    """
    定时任务：发现所有节点的控制器版本信息
    通过执行配置的版本命令获取版本信息，并计算升级状态
    """
    logger.info("开始执行节点控制器版本发现任务")

    # 一次性获取所有最新版本映射（只查询一次）
    latest_versions_map = VersionUpgradeService.get_latest_versions_map(component_type='controller')

    nodes = Node.objects.all()
    success_count = 0
    failed_count = 0

    for node in nodes:
        try:
            _discover_controller_version(node, latest_versions_map)
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


def _discover_controller_version(node: Node, latest_versions_map: dict):
    """
    发现控制器版本信息，并计算升级状态
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
                "latest_version": "",
                "upgradeable": False,
                "message": f"未找到操作系统 {node.operating_system} 对应的控制器配置",
            }
        )
        return

    # component_id 使用数字ID作为唯一标识
    component_id = str(controller.id)
    # component_name 用于匹配 PackageVersion.object 字段
    component_name = controller.name

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
                    "latest_version": "",
                    "upgradeable": False,
                    "message": "控制器未配置版本命令",
                }
            )
            return

        # 使用 Executor 执行版本命令
        executor = Executor(node.id)
        response = executor.execute_local(command=controller.version_command, timeout=10)

        # response 直接是字符串，不是字典
        if response:
            # 去除首尾空白字符（包括换行符）
            version = response.strip()

            if version:
                # 计算升级信息（传递 component_name 用于查询最新版本）
                latest_version, upgradeable = _calculate_upgrade_info(
                    current_version=version,
                    component_name=component_name,
                    os_type=node.operating_system,
                    latest_versions_map=latest_versions_map
                )

                # 更新或创建控制器版本信息（使用 component_id 作为唯一标识）
                NodeComponentVersion.objects.update_or_create(
                    node=node,
                    component_type="controller",
                    component_id=component_id,
                    defaults={
                        "version": version,
                        "latest_version": latest_version,
                        "upgradeable": upgradeable,
                        "message": "版本获取成功",
                    }
                )
                logger.info(f"节点 {node.name} 控制器版本: {version}, 最新版本: {latest_version}, 可升级: {upgradeable}")
            else:
                # 命令返回了空字符串
                NodeComponentVersion.objects.update_or_create(
                    node=node,
                    component_type="controller",
                    component_id=component_id,
                    defaults={
                        "version": "unknown",
                        "latest_version": "",
                        "upgradeable": False,
                        "message": "命令执行成功但返回了空结果",
                    }
                )
                logger.warning(f"节点 {node.name} 控制器版本命令返回空结果")
        else:
            # 记录获取失败的情况
            error_msg = "命令执行失败，未返回结果"
            NodeComponentVersion.objects.update_or_create(
                node=node,
                component_type="controller",
                component_id=component_id,
                defaults={
                    "version": "unknown",
                    "latest_version": "",
                    "upgradeable": False,
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
                    "latest_version": "",
                    "upgradeable": False,
                    "message": error_message,
                }
            )
        except Exception as db_error:
            logger.error(f"保存版本信息异常记录失败: {str(db_error)}")


def _calculate_upgrade_info(current_version: str, component_name: str, os_type: str, latest_versions_map: dict) -> tuple:
    """
    计算升级信息

    Args:
        current_version: 当前版本
        component_name: 组件名称（用于匹配 PackageVersion.object 字段）
        os_type: 操作系统类型
        latest_versions_map: 最新版本映射字典

    Returns:
        (latest_version, upgradeable) 元组
    """
    # 获取该操作系统的最新版本映射
    os_latest_versions = latest_versions_map.get(os_type, {})
    # 使用 component_name 查询最新版本
    latest_version = os_latest_versions.get(component_name, '')

    # 检查当前版本是否包含特殊标签
    current_is_latest = current_version and 'latest' in current_version.lower()
    current_is_unknown = current_version and 'unknown' in current_version.lower()
    latest_is_latest = latest_version and 'latest' in latest_version.lower()

    # 升级逻辑：
    # 1. 当前版本是 unknown → 不升级
    # 2. 当前版本是 latest → 不升级
    # 3. 最新版本是 latest → 需要升级
    # 4. 都是正常版本号 → 进行版本号比较
    if current_is_unknown:
        upgradeable = False
    elif current_is_latest:
        upgradeable = False
    elif latest_is_latest:
        upgradeable = True
    elif not latest_version:
        upgradeable = False
    else:
        upgradeable = VersionUtils.is_upgradeable(current_version, latest_version)

    # 如果没有最新版本，使用当前版本
    if not latest_version:
        latest_version = current_version

    return latest_version, upgradeable
