"""跨模块推送写入节点：只关联，永不新建节点。

CMDB / 监控创建主机后调用本 ingest；按 ip+云区域匹配唯一节点并互写关联 ID。
删除通知只清关联 ID，不删节点。
"""

from __future__ import annotations

from typing import Any

from apps.core.logger import node_logger as logger
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.services.module_link import NodeAssociationService
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE, IngestResult

RECEIVING_MODULE = "node_mgmt"


class NodeModuleIngestService:
    """接收 cmdb / monitor 推送：只补全或清除关联 ID，不创建/删除节点。"""

    @classmethod
    def ingest(cls, params: dict[str, Any]) -> dict[str, Any]:
        raw = params.get("raw") or {}
        if not isinstance(raw, dict):
            raise ValueError("raw must be an object")

        link_ids = params.get("link_ids") or {}
        if not isinstance(link_ids, dict):
            link_ids = {}

        source_module = str(params.get("source_module") or "").strip()
        node_id = cls._normalize_str(link_ids.get("node_id"))
        cmdb_id = cls._normalize_str(link_ids.get("cmdb_id"))
        monitor_id = cls._normalize_str(link_ids.get("monitor_id"))
        if not node_id and source_module == RECEIVING_MODULE:
            node_id = cls._normalize_str(params.get("source_id"))

        if cls._is_echo(params):
            return IngestResult(id=node_id, ignored=True).as_dict()

        event_type = str(params.get("event_type") or "").strip()
        if event_type == EVENT_LIFECYCLE:
            return cls._handle_lifecycle(
                source_module=source_module,
                node_id=node_id,
                cmdb_id=cmdb_id,
                monitor_id=monitor_id,
                raw=raw,
            )

        ip = cls._extract_ip(raw)
        cloud = raw.get("cloud_region_id", raw.get("cloud"))

        linked: str | None = None
        if source_module == "cmdb" or (cmdb_id and not monitor_id):
            linked = NodeAssociationService.best_effort_associate_cmdb_host(
                cmdb_id=cmdb_id or params.get("source_id"),
                ip=ip,
                cloud=cloud,
                existing_node_id=node_id,
            )
        elif source_module == "monitor" or monitor_id:
            linked = NodeAssociationService.best_effort_associate_monitor_host(
                monitor_id=monitor_id or params.get("source_id"),
                ip=ip,
                cloud=cloud,
                existing_node_id=node_id,
            )
        else:
            logger.info(
                "[NodeModuleIngest] ignored unknown source_module=%s",
                source_module,
            )
            return IngestResult(id=None, ignored=True).as_dict()

        if not linked:
            return IngestResult(id=None, ignored=True).as_dict()
        return IngestResult(id=linked, updated=True).as_dict()

    @classmethod
    def _handle_lifecycle(
        cls,
        *,
        source_module: str,
        node_id: str | None,
        cmdb_id: str | None,
        monitor_id: str | None,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        """对端删除：只清 Node 上的关联 ID，永不删节点。"""
        action = str((raw or {}).get("action") or "unlink").strip().lower()
        if action not in ("retire", "archive", "stop", "unlink", ""):
            return IngestResult(id=node_id, ignored=True).as_dict()

        node = None
        if node_id:
            node = Node.objects.filter(id=node_id).first()
        if not node and source_module == "cmdb" and cmdb_id:
            node = Node.objects.filter(cmdb_id=cmdb_id).first()
        if not node and source_module == "monitor" and monitor_id:
            node = Node.objects.filter(monitor_id=monitor_id).first()

        if not node:
            return IngestResult(id=node_id, ignored=True).as_dict()

        update_fields: list[str] = []
        if source_module == "cmdb":
            if node.cmdb_id:
                node.cmdb_id = ""
                update_fields.append("cmdb_id")
        elif source_module == "monitor":
            if node.monitor_id:
                node.monitor_id = ""
                update_fields.append("monitor_id")
        else:
            if cmdb_id and node.cmdb_id:
                node.cmdb_id = ""
                update_fields.append("cmdb_id")
            if monitor_id and node.monitor_id:
                node.monitor_id = ""
                update_fields.append("monitor_id")

        if not update_fields:
            return IngestResult(id=node.id, ignored=True).as_dict()

        update_fields.append("updated_at")
        node.save(update_fields=update_fields)
        logger.info(
            "[NodeModuleIngest] lifecycle unlink cleared %s on node_id=%s source=%s",
            [f for f in update_fields if f != "updated_at"],
            node.id,
            source_module,
        )
        return IngestResult(id=node.id, updated=True).as_dict()

    @classmethod
    def _is_echo(cls, params: dict[str, Any]) -> bool:
        source_module = str(params.get("source_module") or "")
        if source_module == RECEIVING_MODULE:
            return True
        causation_id = str(params.get("causation_id") or "")
        return causation_id.startswith(f"{RECEIVING_MODULE}:")

    @staticmethod
    def _normalize_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _extract_ip(cls, raw: dict[str, Any]) -> str | None:
        for key in ("ip_addr", "ip"):
            value = cls._normalize_str(raw.get(key))
            if value:
                return value
        return None
