import re

from celery import shared_task

from apps.core.logger import logger
from apps.node_mgmt.models import Node, NodeComponentVersion, Controller
from apps.rpc.executor import Executor
from apps.node_mgmt.services.version_upgrade import VersionUpgradeService
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.version_utils import VersionUtils

# 版本号格式校验：支持 x.y.z、x.y.z.w、带预发布标签（如 1.2.3-beta.1）
VERSION_FORMAT_PATTERN = re.compile(r"^\d+\.\d+\.\d+(\.\d+)?(-[\w.]+)?$")


@shared_task
def discover_node_versions():
    """
    定时任务：发现所有节点的控制器版本信息
    通过执行配置的版本命令获取版本信息，并计算升级状态
    """
    logger.info("开始执行节点控制器版本发现任务")

    # 一次性获取所有最新版本映射（只查询一次）
    latest_versions_map = VersionUpgradeService.get_latest_versions_map(component_type="controller")

    # 预加载所有 Controller 记录，避免循环内每节点发起最多 3 次 DB 查询
    # Controller 表记录数有限（按 os×arch 组合），一次全量加载后在内存中查找
    all_controllers = list(Controller.objects.filter(name="Controller"))
    controllers_map = {(c.os, c.cpu_architecture): c for c in all_controllers}

    success_count = 0
    failed_count = 0

    for node in Node.objects.iterator(chunk_size=200):
        try:
            _discover_controller_version(node, latest_versions_map, controllers_map, all_controllers)
            success_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"节点 {node.name}({node.ip}) 控制器版本发现失败: {str(e)}")

    total = success_count + failed_count
    logger.info(f"节点控制器版本发现任务完成，成功: {success_count}, 失败: {failed_count}")
    return {"success_count": success_count, "failed_count": failed_count, "total": total}


def _discover_controller_version(node: Node, latest_versions_map: dict, controllers_map: dict, all_controllers: list):
    """
    发现控制器版本信息，并计算升级状态
    从预加载的 Controller 列表中查找（不再发起 DB 查询）
    """
    # 根据节点操作系统从预加载的 map 中查找控制器配置（精确匹配 → x86_64 回退 → os 兜底）
    node_arch = normalize_cpu_architecture(getattr(node, "cpu_architecture", ""))
    controller = (
        controllers_map.get((node.operating_system, node_arch))
        or controllers_map.get((node.operating_system, NodeConstants.X86_64_ARCH))
        or next((c for c in all_controllers if c.os == node.operating_system), None)
    )

    if not controller:
        logger.warning(f"节点 {node.name} 操作系统 {node.operating_system} 未找到对应的控制器配置")
        _save_controller_version_failure(
            node=node,
            message=f"未找到操作系统 {node.operating_system} 对应的控制器配置",
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
            _save_controller_version_failure(node=node, component_id=component_id, message="控制器未配置版本命令")
            return

        # 使用 Executor 执行版本命令
        executor = Executor(node.id)
        shell = "powershell" if node.operating_system == NodeConstants.WINDOWS_OS else None
        response = executor.execute_local(command=controller.version_command, timeout=10, shell=shell)

        # response 直接是字符串，不是字典
        if response:
            # 去除首尾空白字符（包括换行符）
            version = response.strip()

            if version and VERSION_FORMAT_PATTERN.match(version):
                # 计算升级信息（传递 component_name 用于查询最新版本）
                latest_version, upgradeable = _calculate_upgrade_info(
                    current_version=version,
                    component_name=component_name,
                    os_type=node.operating_system,
                    cpu_architecture=node_arch,
                    latest_versions_map=latest_versions_map,
                )

                _save_controller_version_success(
                    node=node,
                    component_id=component_id,
                    version=version,
                    latest_version=latest_version,
                    upgradeable=upgradeable,
                )
                logger.info(f"节点 {node.name} 控制器版本: {version}, 最新版本: {latest_version}, 可升级: {upgradeable}")
            elif version:
                _save_controller_version_failure(
                    node=node,
                    component_id=component_id,
                    message=f"返回内容不是有效版本号: {version[:100]}",
                )
                logger.warning(f"节点 {node.name} 控制器版本命令返回非版本号内容: {version[:100]}")
            else:
                # 命令返回了空字符串
                _save_controller_version_failure(node=node, component_id=component_id, message="命令执行成功但返回了空结果")
                logger.warning(f"节点 {node.name} 控制器版本命令返回空结果")
        else:
            # 记录获取失败的情况
            error_msg = "命令执行失败，未返回结果"
            _save_controller_version_failure(node=node, component_id=component_id, message=error_msg)
            logger.warning(f"节点 {node.name} 控制器版本获取失败: {error_msg}")

    except Exception as e:
        error_message = f"异常: {str(e)}"
        logger.error(f"获取节点 {node.name} 控制器版本失败: {error_message}")
        # 记录异常信息
        try:
            _save_controller_version_failure(node=node, component_id=component_id, message=error_message)
        except Exception as db_error:
            logger.error(f"保存版本信息异常记录失败: {str(db_error)}")


def _get_existing_controller_version(node: Node, component_id: str | None = None):
    queryset = NodeComponentVersion.objects.filter(node=node, component_type="controller")
    if component_id:
        exact_record = queryset.filter(component_id=component_id).first()
        if exact_record:
            return exact_record
    return queryset.order_by("-last_check_at", "-id").first()


def _save_controller_version_success(
    node: Node,
    component_id: str,
    version: str,
    latest_version: str,
    upgradeable: bool,
):
    record = _get_existing_controller_version(node=node, component_id=component_id)
    if record:
        record.component_id = component_id
        record.version = version
        record.latest_version = latest_version
        record.upgradeable = upgradeable
        record.message = "版本获取成功"
        record.save()
        return record

    return NodeComponentVersion.objects.create(
        node=node,
        component_type="controller",
        component_id=component_id,
        version=version,
        latest_version=latest_version,
        upgradeable=upgradeable,
        message="版本获取成功",
    )


def _save_controller_version_failure(node: Node, message: str, component_id: str | None = None):
    record = _get_existing_controller_version(node=node, component_id=component_id)
    if record:
        if component_id:
            record.component_id = component_id
        record.message = message
        record.save()
        return record

    return NodeComponentVersion.objects.create(
        node=node,
        component_type="controller",
        component_id=component_id or "unknown",
        version="unknown",
        latest_version="",
        upgradeable=False,
        message=message,
    )


def _calculate_upgrade_info(current_version: str, component_name: str, os_type: str, cpu_architecture: str, latest_versions_map: dict) -> tuple:
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
    component_versions = os_latest_versions.get(component_name, {})
    latest_version = component_versions.get(cpu_architecture, "") or component_versions.get("", "")

    # 检查当前版本是否包含特殊标签
    current_is_latest = current_version and "latest" in current_version.lower()
    current_is_unknown = current_version and "unknown" in current_version.lower()
    latest_is_latest = latest_version and "latest" in latest_version.lower()

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
