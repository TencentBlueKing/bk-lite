"""目标同步服务"""

from typing import Optional

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutorDriver, OSType, TargetSource
from apps.job_mgmt.models import Target
from apps.rpc.node_mgmt import NodeMgmt


class TargetSyncService:
    """从 Node 同步 Target 的服务"""

    # Node.operating_system -> Target.os 映射
    OS_MAPPING = {
        "linux": OSType.LINUX,
        "windows": OSType.WINDOWS,
    }

    def __init__(self):
        self.node_mgmt = NodeMgmt()

    def sync_nodes(self, node_ids: Optional[list] = None, team: Optional[list] = None) -> dict:
        """
        同步 Node 到 Target

        Args:
            node_ids: 要同步的 Node ID 列表，为空则同步全部
            team: 目标归属团队 ID 列表

        Returns:
            同步结果统计
        """
        team = team or []

        # 通过 RPC 接口查询 Node
        query_data = {"page": 1, "page_size": -1}  # 获取全部
        if team:
            query_data["organization_ids"] = team

        result = self.node_mgmt.node_list(query_data)
        nodes = result.get("nodes", [])

        # 如果指定了 node_ids，则过滤
        if node_ids:
            nodes = [n for n in nodes if n.get("id") in node_ids]

        if not nodes:
            return {"synced": 0, "created": 0, "updated": 0, "skipped": 0}

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for node in nodes:
            try:
                sync_result = self._sync_single_node(node, team)
                if sync_result == "created":
                    created_count += 1
                elif sync_result == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                logger.exception(f"同步 Node {node.get('id')} 失败: {e}")
                skipped_count += 1

        return {"synced": created_count + updated_count, "created": created_count, "updated": updated_count, "skipped": skipped_count}

    def _sync_single_node(self, node: dict, team: list) -> str:
        """
        同步单个 Node

        Args:
            node: Node 数据字典（来自 RPC 接口）
            team: 目标归属团队

        Returns:
            "created" / "updated" / "skipped"
        """
        node_id = node.get("id")
        node_name = node.get("name", "")
        node_ip = node.get("ip", "")
        operating_system = node.get("operating_system", "linux")
        cloud_region_id = node.get("cloud_region")  # 整数类型，可能为 None

        # 映射操作系统
        os_type = self.OS_MAPPING.get(operating_system, OSType.LINUX)

        # 查找已存在的同步目标
        existing = Target.objects.filter(source=TargetSource.SYNC, source_id=node_id).first()

        if existing:
            # 更新已存在的目标
            changed = False
            field_updates = {
                "name": node_name,
                "ip": node_ip,
                "os_type": os_type,
                "node_id": node_id,
                "cloud_region_id": cloud_region_id,
            }
            for field, value in field_updates.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed = True

            # 合并 team（保留已有，添加新的）
            current_team = set(existing.team or [])
            new_team = set(team or [])
            merged_team = list(current_team | new_team)
            if set(existing.team or []) != set(merged_team):
                existing.team = merged_team
                changed = True

            if changed:
                existing.save()
                return "updated"
            return "skipped"

        # 创建新目标
        Target.objects.create(
            name=node_name,
            ip=node_ip,
            os_type=os_type,
            node_id=node_id,
            cloud_region_id=cloud_region_id,
            source=TargetSource.SYNC,
            source_id=node_id,
            driver=ExecutorDriver.SIDECAR,  # 同步来源默认使用 sidecar 驱动
            team=team or [],
        )
        return "created"
