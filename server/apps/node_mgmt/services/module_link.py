"""CMDB / 监控 → 节点管理：只建关联，不创建节点。

主机资产新增时自动按 ip + 云区域精确匹配唯一节点，互写关联 ID。
失败 / 无法唯一匹配时静默跳过，不得阻断资产创建。
"""

from __future__ import annotations

from typing import Any

from apps.core.logger import node_logger as logger
from apps.node_mgmt.models.sidecar import Node

HOST_MODEL_ID = "host"


class NodeAssociationService:
    """对端主机资产 → 节点关联（自动、无勾选、不创建节点）。"""

    @classmethod
    def best_effort_associate_cmdb_host(
        cls,
        *,
        cmdb_id: Any,
        ip: Any,
        cloud: Any,
        existing_node_id: Any = None,
    ) -> str | None:
        """CMDB 主机创建后：匹配节点并回填 Node.cmdb_id，返回 node_id。"""
        try:
            return cls._associate(
                peer_field="cmdb_id",
                peer_id=cmdb_id,
                ip=ip,
                cloud=cloud,
                existing_node_id=existing_node_id,
            )
        except Exception:
            logger.exception(
                "[NodeAssociation] cmdb host link failed cmdb_id=%s ip=%s cloud=%s",
                cmdb_id,
                ip,
                cloud,
            )
            return None

    @classmethod
    def best_effort_associate_monitor_host(
        cls,
        *,
        monitor_id: Any,
        ip: Any,
        cloud: Any,
        existing_node_id: Any = None,
    ) -> str | None:
        """监控主机创建后：匹配节点并回填 Node.monitor_id，返回 node_id。"""
        try:
            return cls._associate(
                peer_field="monitor_id",
                peer_id=monitor_id,
                ip=ip,
                cloud=cloud,
                existing_node_id=existing_node_id,
            )
        except Exception:
            logger.exception(
                "[NodeAssociation] monitor host link failed monitor_id=%s ip=%s cloud=%s",
                monitor_id,
                ip,
                cloud,
            )
            return None

    @classmethod
    def _associate(
        cls,
        *,
        peer_field: str,
        peer_id: Any,
        ip: Any,
        cloud: Any,
        existing_node_id: Any,
    ) -> str | None:
        peer_id_str = cls._normalize_str(peer_id)
        if not peer_id_str:
            return None

        existing = cls._normalize_str(existing_node_id)
        if existing:
            node = Node.objects.filter(id=existing).first()
            if not node:
                return None
            return cls._write_peer_id(node, peer_field, peer_id_str)

        ip_str = cls._normalize_str(ip)
        cloud_id = cls._normalize_cloud(cloud)
        if not ip_str or cloud_id is None:
            return None

        node = cls._find_unique_host_node(ip=ip_str, cloud_region_id=cloud_id)
        if not node:
            return None
        return cls._write_peer_id(node, peer_field, peer_id_str)

    @classmethod
    def _find_unique_host_node(cls, *, ip: str, cloud_region_id: int) -> Node | None:
        qs = Node.objects.filter(ip=ip, cloud_region_id=cloud_region_id)
        matches = list(qs[:2])
        if len(matches) != 1:
            if matches:
                logger.info(
                    "[NodeAssociation] skip non-unique node match ip=%s cloud=%s count>=2",
                    ip,
                    cloud_region_id,
                )
            return None
        return matches[0]

    @classmethod
    def _write_peer_id(cls, node: Node, peer_field: str, peer_id: str) -> str | None:
        current = cls._normalize_str(getattr(node, peer_field, None))
        if current and current != peer_id:
            logger.info(
                "[NodeAssociation] skip conflict node_id=%s %s existing=%s incoming=%s",
                node.id,
                peer_field,
                current,
                peer_id,
            )
            return None
        if current == peer_id:
            return node.id
        setattr(node, peer_field, peer_id)
        node.save(update_fields=[peer_field, "updated_at"])
        logger.info(
            "[NodeAssociation] linked node_id=%s %s=%s",
            node.id,
            peer_field,
            peer_id,
        )
        return node.id

    @staticmethod
    def _normalize_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_cloud(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
