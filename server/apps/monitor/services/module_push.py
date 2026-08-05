"""监控 → CMDB 显式推送：用户触发，无级联。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization
from apps.node_mgmt.services.module_push_contract import EVENT_UPSERT, IngestEnvelope
from apps.rpc.cmdb import CMDB

MODULE_NAME = "monitor"
TARGET_CMDB = "cmdb"

# 监控对象名 → CMDB model_id；未匹配时优先 host
MONITOR_OBJECT_TO_CMDB_MODEL = {
    "host": "host",
    "Host": "host",
    "主机": "host",
    "switch": "switch",
    "Switch": "switch",
    "router": "router",
    "Router": "router",
    "firewall": "firewall",
    "Firewall": "firewall",
    "loadbalance": "loadbalance",
    "LoadBalance": "loadbalance",
    "physcial_server": "physcial_server",
}


def build_monitor_push_actor_scope(request) -> dict[str, Any]:
    """从请求鉴权上下文构造跨模块推送 actor_scope。"""
    operator = getattr(getattr(request, "user", None), "username", "") or ""
    try:
        scope = resolve_current_team_data_scope(request)
        return {
            "allowed_org_ids": list(scope.data_team_ids),
            "operator": scope.username or operator,
        }
    except BaseAppException:
        return {"allowed_org_ids": [], "operator": operator}


def causation_id_for(source_module: str, source_id: str, target: str) -> str:
    return f"{source_module}:{source_id}:{target}"


def resolve_cmdb_model_id(monitor_object_name: str | None) -> str:
    """主机类优先映射为 host；未知对象默认 host。"""
    if not monitor_object_name:
        return "host"
    return MONITOR_OBJECT_TO_CMDB_MODEL.get(monitor_object_name, "host")


class MonitorToCmdbPushService:
    """将监控实例显式推送到 CMDB（带 causation，无级联）。"""

    @classmethod
    def push_instance(
        cls,
        inst_id: str,
        *,
        actor_scope: dict[str, Any],
    ) -> dict[str, Any]:
        instance = (
            MonitorInstance.objects.filter(id=str(inst_id), is_deleted=False)
            .select_related("monitor_object")
            .first()
        )
        if not instance:
            raise ValueError(f"monitor instance not found: {inst_id}")

        envelope = cls._build_envelope(instance)
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""

        logger.info(
            "[MonitorToCmdbPush] push monitor_id=%s node_id=%s cmdb_id=%s",
            instance.id,
            instance.node_id,
            instance.cmdb_id,
        )
        result = CMDB().ingest_from_source(
            **envelope,
            allowed_org_ids=allowed_org_ids,
            operator=operator,
        )
        if not isinstance(result, dict):
            result = {"id": result}

        # 成功响应回填 cmdb_id（含幂等命中）；ignored/conflict 不回填
        result_id = result.get("id")
        if (
            result_id is not None
            and not result.get("ignored")
            and not result.get("conflict")
        ):
            new_cmdb_id = str(result_id)
            if instance.cmdb_id != new_cmdb_id:
                instance.cmdb_id = new_cmdb_id
                instance.save(update_fields=["cmdb_id", "updated_at"])

        return {
            "monitor_id": instance.id,
            "node_id": instance.node_id,
            "cmdb_id": instance.cmdb_id,
            "cmdb_result": result,
        }

    @classmethod
    def _build_envelope(cls, instance: MonitorInstance) -> dict[str, Any]:
        org_ids = list(
            MonitorInstanceOrganization.objects.filter(
                monitor_instance=instance
            ).values_list("organization", flat=True)
        )
        model_id = resolve_cmdb_model_id(
            getattr(instance.monitor_object, "name", None)
        )
        raw: dict[str, Any] = {
            "ip": str(instance.ip) if instance.ip else None,
            "ip_addr": str(instance.ip) if instance.ip else None,
            "name": instance.name,
            "inst_name": instance.name,
            "cloud_region_id": instance.cloud_region_id,
            "cloud": instance.cloud_region_id,
            "organization_ids": org_ids,
            "organization": org_ids,
            "model_id": model_id,
        }
        raw = {k: v for k, v in raw.items() if v not in (None, "", [])}

        link_ids: dict[str, Any] = {}
        if instance.node_id:
            link_ids["node_id"] = instance.node_id
        if instance.cmdb_id:
            link_ids["cmdb_id"] = instance.cmdb_id

        source_id = str(instance.id)
        envelope = IngestEnvelope(
            source_module=MODULE_NAME,
            source_id=source_id,
            event_type=EVENT_UPSERT,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw=raw,
            link_ids=link_ids,
            causation_id=causation_id_for(MODULE_NAME, source_id, TARGET_CMDB),
        )
        return {
            "source_module": envelope.source_module,
            "source_id": envelope.source_id,
            "event_type": envelope.event_type,
            "occurred_at": envelope.occurred_at,
            "raw": envelope.raw,
            "link_ids": envelope.link_ids,
            "causation_id": envelope.causation_id,
        }
