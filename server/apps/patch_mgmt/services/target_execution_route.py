"""补丁目标执行路由。

该模块是连通性探测与补丁执行共享的 seam：调用方只提供目标，模块负责根据
目标来源和操作系统解析真实执行链路，避免两处路由规则漂移。
"""

from dataclasses import dataclass
from typing import Any, Optional

from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.models import CloudRegion
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.services.windows_remote_bootstrap import AnsibleExecutorResolver
from apps.patch_mgmt.constants import OSType, PatchTargetSource


class TargetTransport:
    NODE_EXECUTOR = "node_executor"
    NATS_SSH = "nats_ssh"
    ANSIBLE_WINRM = "ansible_winrm"


class TargetExecutorUnavailable(RuntimeError):
    """目标所在区域没有可用的执行器。"""


@dataclass(frozen=True)
class TargetExecutionRoute:
    transport: str
    instance_id: str
    port: Optional[int]


def _target_value(target: Any, field: str, default=None):
    if isinstance(target, dict):
        return target.get(field, default)
    return getattr(target, field, default)


def _cloud_region_name(cloud_region_id: Optional[int]) -> str:
    if not cloud_region_id:
        raise ValueError("目标未配置云区域")
    try:
        return CloudRegion.objects.get(pk=cloud_region_id).name
    except CloudRegion.DoesNotExist as exc:
        raise ValueError(f"云区域 {cloud_region_id} 不存在") from exc


def _regional_nats_executor_id(cloud_region_id: Optional[int]) -> str:
    region_name = _cloud_region_name(cloud_region_id)
    instance_id = RegionService.get_region_service_instance_id(
        region_name,
        CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME,
    )
    if not instance_id:
        raise TargetExecutorUnavailable(f"云区域 {cloud_region_id} 未配置 NATS Executor")
    return str(instance_id)


def _regional_ansible_executor_id(cloud_region_id: Optional[int]) -> str:
    if not cloud_region_id:
        raise ValueError("Windows 手动目标必须配置云区域")
    try:
        return AnsibleExecutorResolver.resolve(int(cloud_region_id))
    except Exception as exc:  # noqa: BLE001
        raise TargetExecutorUnavailable(
            f"云区域 {cloud_region_id} 下未找到健康的 Ansible Executor"
        ) from exc


def resolve_target_execution_route(target: Any) -> TargetExecutionRoute:
    """按目标来源和 OS 解析执行链路；同时校验路由所需的最小配置。"""
    source_type = _target_value(target, "source_type", PatchTargetSource.MANUAL)
    os_type = _target_value(target, "os_type")

    if os_type not in (OSType.LINUX, OSType.WINDOWS):
        raise ValueError(f"不支持的目标操作系统: {os_type!r}")

    if source_type == PatchTargetSource.NODE_MGMT:
        node_id = _target_value(target, "node_id")
        if not node_id:
            raise ValueError("节点管理目标缺少 node_id")
        return TargetExecutionRoute(TargetTransport.NODE_EXECUTOR, str(node_id), None)

    if source_type == PatchTargetSource.MANUAL and os_type == OSType.LINUX:
        cloud_region_id = _target_value(target, "cloud_region_id")
        return TargetExecutionRoute(
            TargetTransport.NATS_SSH,
            _regional_nats_executor_id(cloud_region_id),
            int(_target_value(target, "ssh_port", 22) or 22),
        )

    if source_type == PatchTargetSource.MANUAL and os_type == OSType.WINDOWS:
        cloud_region_id = _target_value(target, "cloud_region_id")
        return TargetExecutionRoute(
            TargetTransport.ANSIBLE_WINRM,
            _regional_ansible_executor_id(cloud_region_id),
            int(_target_value(target, "winrm_port", 5986) or 5986),
        )

    raise ValueError(f"不支持的目标来源: {source_type!r}")
