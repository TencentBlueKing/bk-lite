"""CMDB → 对端 IoC 通知：创建后钩子调用固定 ingest，无业务暗建。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.node_mgmt.services.module_push_contract import (
    EVENT_LIFECYCLE,
    EVENT_UPSERT,
    IngestEnvelope,
)
from apps.rpc.monitor import Monitor
from apps.rpc.node_mgmt import NodeMgmt


MODULE_NAME = "cmdb"
TARGET_MONITOR = "monitor"
TARGET_NODE = "node_mgmt"


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
    """将 CMDB 实例推送到监控（显式或创建钩子；信封不带凭据）。"""

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
    def best_effort_notify_on_host_create(
        cls,
        instance: dict[str, Any],
        *,
        operator: str,
        allowed_org_ids: list[int] | None,
    ) -> dict[str, Any]:
        """主机创建钩子：通知节点 + 监控（无凭据 → 监控侧只关联）。

        最外层吞掉一切异常，失败不阻断创建；返回可能回填后的 instance 字典。
        """
        try:
            result = dict(instance)
            cmdb_id = result.get("_id")
            if cmdb_id in (None, ""):
                return result

            scope = {
                "allowed_org_ids": list(allowed_org_ids or []),
                "operator": operator or "",
            }
            # 1) 节点：只关联
            try:
                node_result = cls._notify_node(result, actor_scope=scope)
                linked = cls._normalize_optional_str(
                    (node_result or {}).get("id") if isinstance(node_result, dict) else None
                )
                if linked and str(result.get("node_id") or "").strip() != linked:
                    result = cls._backfill_node_id(
                        result, linked, operator=operator, allowed_org_ids=allowed_org_ids
                    )
            except Exception:
                logger.exception(
                    "[CmdbIoC] notify node failed cmdb_id=%s", cmdb_id
                )

            # 2) 监控：无凭据，有则关联 / 无则 ignored
            try:
                from apps.monitor.services.module_ingest import MonitorModuleIngestService

                envelope = cls._build_envelope(
                    result,
                    cmdb_id=str(cmdb_id),
                    node_id=cls._normalize_optional_str(result.get("node_id")),
                )
                monitor_result = MonitorModuleIngestService.ingest(
                    {
                        **envelope,
                        "allowed_org_ids": scope["allowed_org_ids"],
                        "operator": scope["operator"],
                    }
                )
                if not isinstance(monitor_result, dict):
                    monitor_result = {"id": monitor_result}
                monitor_id = monitor_result.get("id")
                if (
                    monitor_id is not None
                    and not monitor_result.get("ignored")
                    and not monitor_result.get("conflict")
                ):
                    result = cls._backfill_monitor_id(
                        result,
                        str(monitor_id),
                        operator=operator,
                        allowed_org_ids=allowed_org_ids,
                    )
            except Exception:
                logger.exception(
                    "[CmdbIoC] notify monitor failed cmdb_id=%s", cmdb_id
                )
            return result
        except Exception:
            logger.exception(
                "[CmdbIoC] best_effort_notify_on_host_create failed cmdb_id=%s",
                (instance or {}).get("_id"),
            )
            return dict(instance or {})

    @classmethod
    def _notify_node(
        cls,
        instance: dict[str, Any],
        *,
        actor_scope: dict[str, Any],
    ) -> dict[str, Any]:
        cmdb_id = str(instance.get("_id"))
        raw = cls._instance_to_raw(instance)
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        node_id = cls._normalize_optional_str(instance.get("node_id"))
        if node_id:
            link_ids["node_id"] = node_id
        monitor_id = cls._normalize_optional_str(instance.get("monitor_id"))
        if monitor_id:
            link_ids["monitor_id"] = monitor_id

        envelope = IngestEnvelope(
            source_module=MODULE_NAME,
            source_id=cmdb_id,
            event_type=EVENT_UPSERT,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw=raw,
            link_ids=link_ids,
            causation_id=causation_id_for(MODULE_NAME, cmdb_id, TARGET_NODE),
        )
        payload = {
            "source_module": envelope.source_module,
            "source_id": envelope.source_id,
            "event_type": envelope.event_type,
            "occurred_at": envelope.occurred_at,
            "raw": envelope.raw,
            "link_ids": envelope.link_ids,
            "causation_id": envelope.causation_id,
            "allowed_org_ids": list(actor_scope.get("allowed_org_ids") or []),
            "operator": actor_scope.get("operator") or "",
        }
        # 同仓部署优先本地 ingest（与 NATS handler 同一实现）；跨进程再走 RPC
        from apps.node_mgmt.services.module_ingest import NodeModuleIngestService

        try:
            return NodeModuleIngestService.ingest(payload)
        except Exception:
            logger.warning(
                "[CmdbIoC] local node ingest failed, try NATS cmdb_id=%s",
                cmdb_id,
                exc_info=True,
            )
            return NodeMgmt().ingest_from_source(**payload)

    @classmethod
    def _backfill_node_id(
        cls,
        result: dict[str, Any],
        linked: str,
        *,
        operator: str,
        allowed_org_ids: list[int] | None,
    ) -> dict[str, Any]:
        try:
            from apps.cmdb.services.module_ingest import ensure_model_node_id_attr

            ensure_model_node_id_attr("host", username=operator or "admin")
            updated = InstanceManage.instance_update(
                user_groups=[],
                roles=[],
                inst_id=int(result["_id"]),
                update_attr={"node_id": linked},
                operator=operator or "",
                allowed_org_ids=list(allowed_org_ids or []),
                skip_permission_check=True,
            )
            if isinstance(updated, dict):
                merged = dict(result)
                merged.update(updated)
                merged["node_id"] = linked
                return merged
            result = dict(result)
            result["node_id"] = linked
            return result
        except Exception:
            logger.exception(
                "[CmdbIoC] backfill node_id failed cmdb_id=%s node_id=%s",
                result.get("_id"),
                linked,
            )
            result = dict(result)
            result["node_id"] = linked
            return result

    @classmethod
    def _backfill_monitor_id(
        cls,
        result: dict[str, Any],
        monitor_id: str,
        *,
        operator: str,
        allowed_org_ids: list[int] | None,
    ) -> dict[str, Any]:
        if str(result.get("monitor_id") or "").strip() == monitor_id:
            return result
        try:
            from apps.cmdb.services.module_ingest import ensure_model_monitor_id_attr

            ensure_model_monitor_id_attr("host", username=operator or "admin")
            updated = InstanceManage.instance_update(
                user_groups=[],
                roles=[],
                inst_id=int(result["_id"]),
                update_attr={"monitor_id": monitor_id},
                operator=operator or "",
                allowed_org_ids=list(allowed_org_ids or []),
                skip_permission_check=True,
            )
            if isinstance(updated, dict):
                merged = dict(result)
                merged.update(updated)
                merged["monitor_id"] = monitor_id
                return merged
            result = dict(result)
            result["monitor_id"] = monitor_id
            return result
        except Exception:
            logger.exception(
                "[CmdbIoC] backfill monitor_id failed cmdb_id=%s monitor_id=%s",
                result.get("_id"),
                monitor_id,
            )
            return result

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
        # 明确不携带 credential：创建钩子 / 显式推送默认只关联，凭据路径另行扩展
        return {k: v for k, v in raw.items() if v not in (None, "", [])}

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def best_effort_notify_on_delete(
        cls,
        instances: list[dict[str, Any]],
        *,
        operator: str = "",
        allowed_org_ids: list[int] | None = None,
    ) -> None:
        """CMDB 实例删除钩子：通知节点 + 监控只清关联 ID（不真删对端）。"""
        try:
            scope = {
                "allowed_org_ids": list(allowed_org_ids or []),
                "operator": operator or "",
            }
            for instance in instances or []:
                try:
                    cls._notify_delete_one(instance, actor_scope=scope)
                except Exception:
                    logger.exception(
                        "[CmdbIoC] delete notify one failed cmdb_id=%s",
                        (instance or {}).get("_id"),
                    )
        except Exception:
            logger.exception("[CmdbIoC] best_effort_notify_on_delete failed")

    @classmethod
    def _notify_delete_one(
        cls,
        instance: dict[str, Any],
        *,
        actor_scope: dict[str, Any],
    ) -> None:
        cmdb_id = str(instance.get("_id") or "").strip()
        if not cmdb_id:
            return
        node_id = cls._normalize_optional_str(instance.get("node_id"))
        monitor_id = cls._normalize_optional_str(instance.get("monitor_id"))
        if not node_id and not monitor_id:
            return

        raw = cls._instance_to_raw(instance)
        raw["action"] = "unlink"
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        if node_id:
            link_ids["node_id"] = node_id
        if monitor_id:
            link_ids["monitor_id"] = monitor_id

        occurred_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = {
            "source_module": MODULE_NAME,
            "source_id": cmdb_id,
            "event_type": EVENT_LIFECYCLE,
            "occurred_at": occurred_at,
            "raw": raw,
            "link_ids": link_ids,
            "allowed_org_ids": list(actor_scope.get("allowed_org_ids") or []),
            "operator": actor_scope.get("operator") or "",
        }

        try:
            from apps.node_mgmt.services.module_ingest import NodeModuleIngestService

            payload = {
                **base,
                "causation_id": causation_id_for(MODULE_NAME, cmdb_id, TARGET_NODE),
            }
            try:
                NodeModuleIngestService.ingest(payload)
            except Exception:
                NodeMgmt().ingest_from_source(**payload)
        except Exception:
            logger.exception(
                "[CmdbIoC] delete notify node failed cmdb_id=%s", cmdb_id
            )

        try:
            from apps.monitor.services.module_ingest import MonitorModuleIngestService

            payload = {
                **base,
                "causation_id": causation_id_for(MODULE_NAME, cmdb_id, TARGET_MONITOR),
            }
            try:
                MonitorModuleIngestService.ingest(payload)
            except Exception:
                Monitor().ingest_from_source(**payload)
        except Exception:
            logger.exception(
                "[CmdbIoC] delete notify monitor failed cmdb_id=%s", cmdb_id
            )
