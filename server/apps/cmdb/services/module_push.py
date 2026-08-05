"""CMDB → 监控显式推送：用户触发，无级联。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.node_mgmt.services.module_push_contract import EVENT_UPSERT, IngestEnvelope
from apps.rpc.monitor import Monitor


MODULE_NAME = "cmdb"
TARGET_MONITOR = "monitor"


def build_cmdb_push_actor_scope(request) -> dict[str, Any]:
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


class CmdbToMonitorPushService:
    """将 CMDB 实例显式推送到监控（带 causation，无级联）。"""

    @classmethod
    def push_instance(
        cls,
        inst_id: int | str,
        *,
        actor_scope: dict[str, Any],
    ) -> dict[str, Any]:
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise ValueError(f"CMDB instance not found: {inst_id}")

        cmdb_id = str(instance.get("_id"))
        node_id = cls._normalize_optional_str(instance.get("node_id"))
        envelope = cls._build_envelope(instance, cmdb_id=cmdb_id, node_id=node_id)
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""

        logger.info(
            "[CmdbToMonitorPush] push cmdb_id=%s node_id=%s",
            cmdb_id,
            node_id,
        )
        result = Monitor().ingest_from_source(
            **envelope,
            allowed_org_ids=allowed_org_ids,
            operator=operator,
        )
        if not isinstance(result, dict):
            result = {"id": result}
        return {
            "cmdb_id": cmdb_id,
            "node_id": node_id,
            "monitor_result": result,
        }

    @classmethod
    def _build_envelope(
        cls,
        instance: dict[str, Any],
        *,
        cmdb_id: str,
        node_id: str | None,
    ) -> dict[str, Any]:
        raw = cls._instance_to_raw(instance)
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        if node_id:
            link_ids["node_id"] = node_id

        envelope = IngestEnvelope(
            source_module=MODULE_NAME,
            source_id=cmdb_id,
            event_type=EVENT_UPSERT,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw=raw,
            link_ids=link_ids,
            causation_id=causation_id_for(MODULE_NAME, cmdb_id, TARGET_MONITOR),
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

    @classmethod
    def _instance_to_raw(cls, instance: dict[str, Any]) -> dict[str, Any]:
        org = instance.get("organization")
        raw: dict[str, Any] = {
            "ip": instance.get("ip_addr") or instance.get("ip"),
            "ip_addr": instance.get("ip_addr") or instance.get("ip"),
            "name": instance.get("inst_name") or instance.get("name"),
            "inst_name": instance.get("inst_name") or instance.get("name"),
            "cloud": instance.get("cloud"),
            "cloud_region_id": instance.get("cloud"),
            "organization": org,
            "organization_ids": org if isinstance(org, list) else ([org] if org not in (None, "") else []),
            "os_type": instance.get("os_type"),
            "operating_system": instance.get("os_type"),
            "model_id": instance.get("model_id") or "host",
        }
        return {k: v for k, v in raw.items() if v not in (None, "", [])}

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None
