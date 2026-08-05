"""跨模块推送写入监控：按 link_ids.node_id / cmdb_id 归并 upsert。

一期：最小实例 upsert + ID 归并，不开采集配置流水线。
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.node_mgmt.services.module_push_contract import (
    EVENT_LIFECYCLE,
    EVENT_UPSERT,
    LINK_CONFLICT,
    IngestResult,
)

HOST_OBJECT_NAME = "Host"
RECEIVING_MODULE = "monitor"


class MonitorModuleIngestService:
    """接收 node_mgmt / CMDB 等模块推送的 ingest envelope，写入 MonitorInstance。"""

    @classmethod
    def ingest(cls, params: dict[str, Any]) -> dict[str, Any]:
        allowed_org_ids = params.get("allowed_org_ids")
        if not allowed_org_ids:
            raise ValueError("authorization scope is required for monitor ingest")

        raw = params.get("raw") or {}
        if not isinstance(raw, dict):
            raise ValueError("raw must be an object")

        link_ids = params.get("link_ids") or {}
        if not isinstance(link_ids, dict):
            link_ids = {}

        node_id = cls._normalize_optional_str(link_ids.get("node_id"))
        cmdb_id = cls._normalize_optional_str(link_ids.get("cmdb_id"))
        monitor_id = cls._normalize_optional_str(link_ids.get("monitor_id"))
        # node_mgmt 信封常把节点 ID 放在 source_id；勿把 CMDB source_id 误当作 node_id
        if not node_id and params.get("source_module") == "node_mgmt":
            node_id = cls._normalize_optional_str(params.get("source_id"))

        # 回声抑制：本模块自推，或 causation 标明由本模块出站引起的回写
        if cls._is_echo(params):
            existing = None
            if monitor_id:
                existing = cls._find_by_pk(monitor_id)
            if not existing and node_id:
                existing = cls._find_by_node_id(node_id)
            if not existing and cmdb_id:
                existing = cls._find_by_cmdb_id(cmdb_id)
            return IngestResult(
                id=existing.id if existing else None,
                ignored=True,
            ).as_dict()

        event_type = str(params.get("event_type") or EVENT_UPSERT).strip()
        if event_type == EVENT_LIFECYCLE:
            return cls._handle_lifecycle(
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                monitor_id=monitor_id,
                operator=str(params.get("operator") or ""),
            )

        operator = str(params.get("operator") or "")
        allowed = [int(x) for x in allowed_org_ids]

        by_node = cls._find_by_node_id(node_id) if node_id else None
        by_cmdb = cls._find_by_cmdb_id(cmdb_id) if cmdb_id else None

        if by_node and by_cmdb and by_node.id != by_cmdb.id:
            logger.warning(
                "[MonitorModuleIngest] link_conflict node_id=%s cmdb_id=%s "
                "by_node=%s by_cmdb=%s",
                node_id,
                cmdb_id,
                by_node.id,
                by_cmdb.id,
            )
            return IngestResult(
                id=by_node.id,
                conflict=LINK_CONFLICT,
                created=False,
                updated=False,
                claimed=False,
            ).as_dict()

        existing = by_node or by_cmdb
        if existing:
            updated = cls._update_instance(
                existing,
                raw=raw,
                node_id=node_id,
                cmdb_id=cmdb_id,
                operator=operator,
                allowed_org_ids=allowed,
            )
            return IngestResult(id=updated.id, updated=True).as_dict()

        created = cls._create_instance(
            raw=raw,
            node_id=node_id,
            cmdb_id=cmdb_id,
            operator=operator,
            allowed_org_ids=allowed,
        )
        return IngestResult(id=created.id, created=True).as_dict()

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _is_echo(cls, params: dict[str, Any]) -> bool:
        source_module = str(params.get("source_module") or "")
        if source_module == RECEIVING_MODULE:
            return True
        causation_id = str(params.get("causation_id") or "")
        return causation_id.startswith(f"{RECEIVING_MODULE}:")

    @classmethod
    def _handle_lifecycle(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        monitor_id: str | None,
        operator: str,
    ) -> dict[str, Any]:
        """lifecycle 退役：软停用（is_active=False / is_deleted=True），不硬删。"""
        action = str((raw or {}).get("action") or "retire").strip().lower()
        if action not in ("retire", "archive", "stop", ""):
            logger.info(
                "[MonitorModuleIngest] lifecycle ignored unknown action=%s monitor_id=%s",
                action,
                monitor_id,
            )
            return IngestResult(id=monitor_id, ignored=True).as_dict()

        existing = None
        if monitor_id:
            existing = cls._find_by_pk(monitor_id)
        if not existing and node_id:
            existing = cls._find_by_node_id(node_id)
        if not existing and cmdb_id:
            existing = cls._find_by_cmdb_id(cmdb_id)

        if not existing:
            logger.info(
                "[MonitorModuleIngest] lifecycle no-op: instance not found "
                "monitor_id=%s node_id=%s cmdb_id=%s",
                monitor_id,
                node_id,
                cmdb_id,
            )
            return IngestResult(id=monitor_id, ignored=True).as_dict()

        if existing.is_deleted and not existing.is_active:
            return IngestResult(id=existing.id, ignored=True).as_dict()

        update_fields = ["is_active", "is_deleted", "updated_at"]
        existing.is_active = False
        existing.is_deleted = True
        if operator:
            existing.updated_by = operator
            update_fields.append("updated_by")
        existing.save(update_fields=update_fields)
        logger.info(
            "[MonitorModuleIngest] lifecycle retire soft-deactivated instance_id=%s",
            existing.id,
        )
        return IngestResult(id=existing.id, updated=True).as_dict()

    @classmethod
    def _find_by_pk(cls, instance_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(id=instance_id)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _find_by_node_id(cls, node_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(node_id=node_id, is_deleted=False)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _find_by_cmdb_id(cls, cmdb_id: str) -> MonitorInstance | None:
        return (
            MonitorInstance.objects.filter(cmdb_id=cmdb_id, is_deleted=False)
            .select_related("monitor_object")
            .first()
        )

    @classmethod
    def _resolve_monitor_object(cls, raw: dict[str, Any]) -> MonitorObject:
        object_id = raw.get("monitor_object_id")
        if object_id not in (None, ""):
            obj = MonitorObject.objects.filter(id=object_id).first()
            if obj:
                return obj
            raise ValueError(f"monitor_object_id not found: {object_id!r}")

        obj = MonitorObject.objects.filter(name=HOST_OBJECT_NAME).first()
        if obj:
            return obj
        raise ValueError(
            f"monitor object {HOST_OBJECT_NAME!r} not found; "
            "provide raw.monitor_object_id or create Host monitor object"
        )

    @classmethod
    def _extract_ip(cls, raw: dict[str, Any]) -> str | None:
        for key in ("ip", "ip_addr"):
            value = raw.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return None

    @classmethod
    def _extract_cloud_region_id(cls, raw: dict[str, Any]) -> int | None:
        value = raw.get("cloud_region_id") if "cloud_region_id" in raw else raw.get("cloud")
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_name(cls, raw: dict[str, Any], *, ip: str | None) -> str:
        name = str(raw.get("name") or raw.get("inst_name") or "").strip()
        if name:
            return name
        if ip:
            cloud_label = raw.get("cloud_region_name") or raw.get("cloud_region_id") or ""
            return f"{ip}[{cloud_label}]" if cloud_label != "" else ip
        return "unnamed"

    @classmethod
    def _normalize_org_ids(cls, raw: dict[str, Any], allowed_org_ids: list[int]) -> list[int]:
        raw_orgs = raw.get("organization_ids") if "organization_ids" in raw else raw.get("organization")
        if raw_orgs in (None, ""):
            return list(allowed_org_ids)
        if not isinstance(raw_orgs, (list, tuple, set)):
            raw_orgs = [raw_orgs]
        parsed: list[int] = []
        for item in raw_orgs:
            try:
                parsed.append(int(item))
            except (TypeError, ValueError):
                continue
        allowed_set = set(allowed_org_ids)
        in_scope = [org_id for org_id in parsed if org_id in allowed_set]
        return in_scope or list(allowed_org_ids)

    @classmethod
    def _new_instance_id(cls, *, node_id: str | None, raw: dict[str, Any]) -> str:
        if node_id:
            try:
                return normalize_instance_identity(node_id)["storage_instance_key"]
            except ValueError:
                pass
        cloud = cls._extract_cloud_region_id(raw)
        ip = cls._extract_ip(raw)
        if cloud is not None and ip:
            try:
                from apps.monitor.utils.dimension import build_safe_instance_id, extract_monitor_instance_id

                logical = build_safe_instance_id(cloud, ip)
                return extract_monitor_instance_id((logical,))
            except ValueError:
                pass
        return uuid.uuid4().hex

    @classmethod
    def _bind_organizations(
        cls,
        instance: MonitorInstance,
        org_ids: list[int],
        *,
        operator: str,
    ) -> None:
        existing = set(
            MonitorInstanceOrganization.objects.filter(monitor_instance=instance).values_list(
                "organization", flat=True
            )
        )
        for org_id in org_ids:
            if org_id in existing:
                continue
            MonitorInstanceOrganization.objects.create(
                monitor_instance=instance,
                organization=org_id,
                created_by=operator,
                updated_by=operator,
            )

    @classmethod
    @transaction.atomic
    def _update_instance(
        cls,
        instance: MonitorInstance,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> MonitorInstance:
        update_fields: list[str] = []
        ip = cls._extract_ip(raw)
        if ip and instance.ip != ip:
            instance.ip = ip
            update_fields.append("ip")

        cloud = cls._extract_cloud_region_id(raw)
        if cloud is not None and instance.cloud_region_id != cloud:
            instance.cloud_region_id = cloud
            update_fields.append("cloud_region_id")

        name = cls._extract_name(raw, ip=ip or (str(instance.ip) if instance.ip else None))
        if name and instance.name != name:
            instance.name = name
            update_fields.append("name")

        if node_id and instance.node_id != node_id:
            instance.node_id = node_id
            update_fields.append("node_id")

        if cmdb_id and instance.cmdb_id != cmdb_id:
            instance.cmdb_id = cmdb_id
            update_fields.append("cmdb_id")

        if instance.is_deleted:
            instance.is_deleted = False
            update_fields.append("is_deleted")

        if operator:
            instance.updated_by = operator
            update_fields.append("updated_by")

        if update_fields:
            instance.save(update_fields=update_fields + ["updated_at"])

        org_ids = cls._normalize_org_ids(raw, allowed_org_ids)
        cls._bind_organizations(instance, org_ids, operator=operator)
        return instance

    @classmethod
    @transaction.atomic
    def _create_instance(
        cls,
        *,
        raw: dict[str, Any],
        node_id: str | None,
        cmdb_id: str | None,
        operator: str,
        allowed_org_ids: list[int],
    ) -> MonitorInstance:
        monitor_object = cls._resolve_monitor_object(raw)
        ip = cls._extract_ip(raw)
        cloud = cls._extract_cloud_region_id(raw)
        name = cls._extract_name(raw, ip=ip)
        instance_id = cls._new_instance_id(node_id=node_id, raw=raw)

        # 主键冲突时回退 uuid，避免与存量云区域+IP 实例撞车阻断推送
        if MonitorInstance.objects.filter(id=instance_id).exists():
            instance_id = uuid.uuid4().hex

        instance = MonitorInstance.objects.create(
            id=instance_id,
            name=name,
            monitor_object=monitor_object,
            ip=ip,
            cloud_region_id=cloud,
            node_id=node_id,
            cmdb_id=cmdb_id,
            created_by=operator,
            updated_by=operator,
            is_deleted=False,
            is_active=True,
        )
        org_ids = cls._normalize_org_ids(raw, allowed_org_ids)
        cls._bind_organizations(instance, org_ids, operator=operator)
        logger.info(
            "[MonitorModuleIngest] created instance_id=%s node_id=%s cmdb_id=%s",
            instance.id,
            node_id,
            cmdb_id,
        )
        return instance
