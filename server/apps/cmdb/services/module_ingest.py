"""跨模块推送写入 CMDB：host ID 优先 upsert + 存量认领。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.logger import cmdb_logger as logger
from apps.node_mgmt.services.module_push_contract import IngestResult

# push 路径必须持久化 node_id；与 pull sync 的 HOST_SYNC_UPDATE_FIELDS 刻意相反
HOST_INGEST_UPDATE_FIELDS = (
    "inst_name",
    "ip_addr",
    "organization",
    "cloud",
    "os_type",
    "node_id",
)


class CmdbModuleIngestService:
    """接收 node_mgmt 等模块推送的 ingest envelope，写入 CMDB host。"""

    @classmethod
    def ingest(cls, params: dict[str, Any]) -> dict[str, Any]:
        allowed_org_ids = params.get("allowed_org_ids")
        if not allowed_org_ids:
            raise ValueError("authorization scope is required for CMDB ingest")

        raw = params.get("raw") or {}
        if not isinstance(raw, dict):
            raise ValueError("raw must be an object")

        link_ids = params.get("link_ids") or {}
        if not isinstance(link_ids, dict):
            link_ids = {}

        node_id = link_ids.get("node_id") or params.get("source_id")
        if not node_id:
            raise ValueError("link_ids.node_id or source_id is required")

        operator = params.get("operator") or ""
        desired = cls._build_host_desired(raw=raw, node_id=str(node_id))

        existing = cls._find_by_node_id(str(node_id))
        if existing:
            updated = cls._update_host(
                existing,
                desired,
                operator=operator,
                allowed_org_ids=list(allowed_org_ids),
            )
            return IngestResult(id=updated.get("_id"), updated=True).as_dict()

        existing = cls._find_host_by_ip_cloud(desired.get("ip_addr"), desired.get("cloud"))
        if existing:
            claimed = cls._claim_host(
                existing,
                desired,
                operator=operator,
                allowed_org_ids=list(allowed_org_ids),
            )
            return IngestResult(id=claimed.get("_id"), claimed=True).as_dict()

        created = cls._create_host(
            desired,
            operator=operator,
            allowed_org_ids=list(allowed_org_ids),
        )
        return IngestResult(id=created.get("_id"), created=True).as_dict()

    @classmethod
    def _build_host_desired(cls, *, raw: dict[str, Any], node_id: str) -> dict[str, Any]:
        ip = str(raw.get("ip") or raw.get("ip_addr") or "").strip()
        cloud_raw = raw.get("cloud_region_id") if "cloud_region_id" in raw else raw.get("cloud")
        try:
            cloud = int(cloud_raw) if cloud_raw not in (None, "") else None
        except (TypeError, ValueError):
            cloud = None

        organization = NodeMgmtSyncService._normalize_org_ids(
            raw.get("organization_ids") if "organization_ids" in raw else raw.get("organization")
        )
        inst_name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        if not inst_name and ip:
            cloud_label = raw.get("cloud_region_name") or (cloud if cloud is not None else "")
            inst_name = f"{ip}[{cloud_label}]"

        os_type = NodeMgmtSyncService._map_host_os_type(
            raw.get("operating_system") or raw.get("os_type")
        )

        desired: dict[str, Any] = {
            "model_id": "host",
            "inst_name": inst_name,
            "ip_addr": ip,
            "organization": organization,
            "cloud": cloud,
            "os_type": os_type,
            "node_id": node_id,
        }
        return desired

    @classmethod
    def _find_by_node_id(cls, node_id: str) -> dict[str, Any] | None:
        if not node_id:
            return None
        try:
            found = InstanceManage.query_entity_by_identity("host", {"node_id": node_id})
        except Exception:
            logger.exception("[ModuleIngest] 按 node_id 查找 host 失败 node_id=%s", node_id)
            raise
        return found or None

    @classmethod
    def _find_host_by_ip_cloud(cls, ip_addr: Any, cloud: Any) -> dict[str, Any] | None:
        ip, normalized_cloud = NodeMgmtSyncService._host_lookup_key(
            {"ip_addr": ip_addr, "cloud": cloud}
        )
        if not ip or normalized_cloud is None:
            return None
        try:
            found = InstanceManage.query_entity_by_identity(
                "host",
                {"ip_addr": ip, "cloud": normalized_cloud},
            )
        except Exception:
            logger.exception(
                "[ModuleIngest] 按 ip+cloud 查找 host 失败 ip=%s cloud=%s",
                ip,
                normalized_cloud,
            )
            raise
        return found or None

    @classmethod
    def _host_update_payload(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field in HOST_INGEST_UPDATE_FIELDS:
            if field not in desired:
                continue
            value = desired.get(field)
            if value in (None, "", []):
                continue
            if existing.get(field) != value:
                changes[field] = value
        return changes

    @classmethod
    def _update_host(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        changes = cls._host_update_payload(existing, desired)
        if not changes:
            return existing
        updated = InstanceManage.instance_update(
            user_groups=[{"id": org_id} for org_id in allowed_org_ids],
            roles=[],
            inst_id=int(existing["_id"]),
            update_attr=changes,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            skip_permission_check=False,
        )
        return updated if isinstance(updated, dict) else {**existing, **changes}

    @classmethod
    def _claim_host(
        cls,
        existing: dict[str, Any],
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        # 认领：白名单字段 + 强制写入 node_id
        changes = cls._host_update_payload(existing, desired)
        changes["node_id"] = desired["node_id"]
        updated = InstanceManage.instance_update(
            user_groups=[{"id": org_id} for org_id in allowed_org_ids],
            roles=[],
            inst_id=int(existing["_id"]),
            update_attr=changes,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            skip_permission_check=False,
        )
        return updated if isinstance(updated, dict) else {**existing, **changes}

    @classmethod
    def _create_host(
        cls,
        desired: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int],
    ) -> dict[str, Any]:
        payload = {
            field: desired[field]
            for field in HOST_INGEST_UPDATE_FIELDS
            if field in desired and desired.get(field) not in (None, "")
        }
        created = InstanceManage.instance_create(
            model_id="host",
            instance_info=payload,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
        return created if isinstance(created, dict) else payload
