"""CMDB → 对端 IoC 通知：创建后钩子调用固定 ingest，无业务暗建。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import cmdb_link_identity, optional_inst_uuid
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE, EVENT_UPSERT, IngestEnvelope
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
    """将 CMDB 实例推送到监控（显式或创建钩子）。

    对外只经 Monitor().ingest_from_source；调用方不直连监控内部 ingest 实现。
    公开资产页 push_instance 信封不带凭据；扫描等特权路径走 push_with_credential。
    """

    @classmethod
    def push_instance(
        cls,
        inst_ref: int | str,
        *,
        actor_scope: dict[str, Any],
    ) -> dict[str, Any]:
        instance = cls._resolve_cmdb_instance(inst_ref)
        cmdb_id, aliases = cmdb_link_identity(instance)
        if not cmdb_id:
            raise ValueError(f"CMDB instance missing inst_uuid: {inst_ref}")

        node_id = cls._normalize_optional_str(instance.get("node_id"))
        envelope = cls._build_envelope(instance, cmdb_id=cmdb_id, aliases=aliases, node_id=node_id)
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

        conflict = result.get("conflict")
        monitor_id = result.get("id")
        if conflict:
            link_status = "conflict"
        elif result.get("ignored") or monitor_id in (None, ""):
            link_status = "not_found"
            monitor_id = None
        else:
            link_status = "ok"

        instance_out = instance
        if link_status == "ok" and monitor_id and instance.get("_id") not in (None, ""):
            instance_out = cls._backfill_monitor_id(
                instance,
                str(monitor_id),
                operator=operator,
                allowed_org_ids=allowed_org_ids,
            )

        return {
            "cmdb_id": cmdb_id,
            "node_id": node_id,
            "monitor_id": str(monitor_id) if link_status == "ok" else None,
            "link_status": link_status,
            "monitor_result": result,
            "instance": instance_out,
        }

    @classmethod
    def push_with_credential(
        cls,
        instance: dict[str, Any],
        *,
        credential: dict[str, Any],
        actor_scope: dict[str, Any],
        actor_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """显式带凭据推送（扫描清单等）：仍只调 Monitor.ingest_from_source。

        凭据只进 raw.credential，不进 link_ids；allow_credential_create 由本入口置位。
        成功后回写 CI monitor_id。公开资产页不得走本方法。
        """
        if not isinstance(credential, dict) or not credential:
            raise ValueError("credential is required for credential push")

        cmdb_id, aliases = cmdb_link_identity(instance)
        if not cmdb_id:
            raise ValueError(f"CMDB instance missing inst_uuid: {instance.get('_id') or instance.get('inst_uuid')}")

        node_id = cls._normalize_optional_str(instance.get("node_id"))
        envelope = cls._build_envelope(instance, cmdb_id=cmdb_id, aliases=aliases, node_id=node_id)
        raw = dict(envelope.get("raw") or {})
        # 扫描等调用方可能已把 model_id / 端口 / 云区域写在 instance 上；合并进 raw。
        for key in (
            "model_id",
            "object_type",
            "device_type",
            "port",
            "snmp_port",
            "cloud",
            "cloud_region_id",
            "cloud_name",
            "cloud_region_name",
            "ip",
            "ip_addr",
            "name",
            "inst_name",
            "organization",
            "organization_ids",
            "os_type",
            "operating_system",
        ):
            value = instance.get(key)
            if value not in (None, "", []):
                raw[key] = value
        raw["credential"] = {key: value for key, value in credential.items() if key != "_client_id"}
        envelope["raw"] = raw

        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""
        # 特权路径：打开 allow_credential_create；公开 push_instance 不传此字段。
        payload = {
            **envelope,
            "allowed_org_ids": allowed_org_ids,
            "operator": operator,
            "allow_credential_create": True,
        }
        if actor_context is not None:
            from apps.core.utils.current_team_scope import actor_context_to_wire

            wired = actor_context_to_wire(actor_context)
            if wired is not None:
                payload["actor_context"] = wired

        logger.info(
            "[CmdbToMonitorPush] credential push cmdb_id=%s model_id=%s",
            cmdb_id,
            raw.get("model_id"),
        )
        result = Monitor().ingest_from_source(**payload)
        if not isinstance(result, dict):
            result = {"id": result}

        if result.get("ignored") or result.get("conflict") or result.get("collect_error"):
            logger.warning(
                "[CmdbToMonitorPush] credential push not applied cmdb_id=%s "
                "ignored=%s conflict=%s collect_error=%s id=%s "
                "(若连远端共享 NATS：设 IS_LOCAL_RPC=1 并重启 Server)",
                cmdb_id,
                result.get("ignored"),
                result.get("conflict"),
                result.get("collect_error"),
                result.get("id"),
            )

        monitor_id = result.get("id")
        if (
            monitor_id
            and not result.get("ignored")
            and not result.get("conflict")
            and not result.get("collect_error")
            and instance.get("_id") not in (None, "")
        ):
            instance = cls._backfill_monitor_id(
                instance,
                str(monitor_id),
                operator=operator,
                allowed_org_ids=allowed_org_ids,
            )

        return {
            "cmdb_id": cmdb_id,
            "node_id": node_id,
            "monitor_result": result,
            "instance": instance,
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
            cmdb_id, aliases = cmdb_link_identity(result)
            if not cmdb_id:
                logger.warning(
                    "[CmdbIoC] skip notify: instance missing inst_uuid graph_id=%s",
                    result.get("_id"),
                )
                return result

            scope = {
                "allowed_org_ids": list(allowed_org_ids or []),
                "operator": operator or "",
            }
            # 1) 节点：只关联
            try:
                node_result = cls._notify_node(result, cmdb_id=cmdb_id, aliases=aliases, actor_scope=scope)
                linked = cls._normalize_optional_str((node_result or {}).get("id") if isinstance(node_result, dict) else None)
                if linked and str(result.get("node_id") or "").strip() != linked:
                    result = cls._backfill_node_id(result, linked, operator=operator, allowed_org_ids=allowed_org_ids)
            except Exception:
                logger.exception("[CmdbIoC] notify node failed cmdb_id=%s", cmdb_id)

            # 2) 监控：无凭据，有则关联 / 无则 ignored（经监控对外 ingest 入口）
            try:
                envelope = cls._build_envelope(
                    result,
                    cmdb_id=cmdb_id,
                    aliases=aliases,
                    node_id=cls._normalize_optional_str(result.get("node_id")),
                )
                monitor_result = Monitor().ingest_from_source(
                    **envelope,
                    allowed_org_ids=scope["allowed_org_ids"],
                    operator=scope["operator"],
                )
                if not isinstance(monitor_result, dict):
                    monitor_result = {"id": monitor_result}
                monitor_id = monitor_result.get("id")
                if monitor_id is not None and not monitor_result.get("ignored") and not monitor_result.get("conflict"):
                    result = cls._backfill_monitor_id(
                        result,
                        str(monitor_id),
                        operator=operator,
                        allowed_org_ids=allowed_org_ids,
                    )
            except Exception:
                logger.exception("[CmdbIoC] notify monitor failed cmdb_id=%s", cmdb_id)
            return result
        except Exception:
            logger.exception(
                "[CmdbIoC] best_effort_notify_on_host_create failed cmdb_id=%s",
                (instance or {}).get("inst_uuid") or (instance or {}).get("_id"),
            )
            return dict(instance or {})

    @classmethod
    def _notify_node(
        cls,
        instance: dict[str, Any],
        *,
        cmdb_id: str,
        aliases: list[str],
        actor_scope: dict[str, Any],
    ) -> dict[str, Any]:
        raw = cls._instance_to_raw(instance)
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        legacy_aliases = [item for item in aliases if item != cmdb_id]
        if legacy_aliases:
            link_ids["cmdb_id_aliases"] = legacy_aliases
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
                result.get("inst_uuid") or result.get("_id"),
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

            ensure_model_monitor_id_attr(
                str(result.get("model_id") or "host"),
                username=operator or "admin",
            )
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
                result.get("inst_uuid") or result.get("_id"),
                monitor_id,
            )
            return result

    @classmethod
    def _build_envelope(
        cls,
        instance: dict[str, Any],
        *,
        cmdb_id: str,
        aliases: list[str],
        node_id: str | None,
    ) -> dict[str, Any]:
        raw = cls._instance_to_raw(instance)
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        legacy_aliases = [item for item in aliases if item != cmdb_id]
        if legacy_aliases:
            link_ids["cmdb_id_aliases"] = legacy_aliases
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
        for key in ("port", "snmp_port"):
            if instance.get(key) not in (None, "", []):
                raw[key] = instance.get(key)
        # 明确不携带 credential：公开 push_instance / 创建钩子只关联；
        # 带凭据路径由 push_with_credential 另行写入 raw.credential。
        return {k: v for k, v in raw.items() if v not in (None, "", [])}

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _resolve_cmdb_instance(cls, inst_ref: int | str) -> dict[str, Any]:
        text = str(inst_ref).strip()
        inst_uuid = optional_inst_uuid(text)
        if inst_uuid:
            instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        elif text.isdigit():
            instance = InstanceManage.query_entity_by_id(int(text))
        else:
            instance = None
        if not instance:
            raise ValueError(f"CMDB instance not found: {inst_ref}")
        return instance

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
                        (instance or {}).get("inst_uuid") or (instance or {}).get("_id"),
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
        cmdb_id, aliases = cmdb_link_identity(instance)
        if not cmdb_id:
            return
        node_id = cls._normalize_optional_str(instance.get("node_id"))
        monitor_id = cls._normalize_optional_str(instance.get("monitor_id"))
        if not node_id and not monitor_id:
            return

        raw = cls._instance_to_raw(instance)
        raw["action"] = "unlink"
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id}
        legacy_aliases = [item for item in aliases if item != cmdb_id]
        if legacy_aliases:
            link_ids["cmdb_id_aliases"] = legacy_aliases
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
            logger.exception("[CmdbIoC] delete notify node failed cmdb_id=%s", cmdb_id)

        try:
            payload = {
                **base,
                "causation_id": causation_id_for(MODULE_NAME, cmdb_id, TARGET_MONITOR),
            }
            Monitor().ingest_from_source(**payload)
        except Exception:
            logger.exception("[CmdbIoC] delete notify monitor failed cmdb_id=%s", cmdb_id)
