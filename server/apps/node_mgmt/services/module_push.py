"""节点跨模块推送编排：按用户所选 target 推送，有限重试，无级联。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.core.logger import node_logger as logger
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.module_push_contract import (
    EVENT_UPSERT,
    IngestEnvelope,
    PushTargetStatus,
)
from apps.rpc.cmdb import CMDB


class MonitorLinkage:
    """监控联动占位客户端；Task 8 接入真实实现。"""

    def ingest_from_source(self, **kwargs):
        raise NotImplementedError("MonitorLinkage.ingest_from_source is not implemented yet")


class ModulePushService:
    DEFAULT_MAX_ATTEMPTS = 3

    @classmethod
    def push_node(
        cls,
        node_id: str,
        *,
        targets: list[str],
        actor_scope: dict[str, Any],
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        """按 targets 推送节点；仅处理用户显式选择的模块，不级联。"""
        attempts_limit = max_attempts if max_attempts is not None else cls.DEFAULT_MAX_ATTEMPTS
        attempts_limit = max(1, int(attempts_limit))

        node = Node.objects.select_related("cloud_region").get(id=node_id)
        envelope = cls._build_envelope(node)
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""

        push_status = dict(node.push_status or {})
        results: dict[str, Any] = {}

        for target in targets:
            if target == "cmdb":
                status = cls._push_with_retries(
                    target="cmdb",
                    push_fn=lambda: CMDB().ingest_from_source(
                        **envelope,
                        allowed_org_ids=allowed_org_ids,
                        operator=operator,
                    ),
                    max_attempts=attempts_limit,
                    on_success=lambda result: cls._backfill_id(node, "cmdb_id", result),
                )
            elif target == "monitor":
                status = cls._push_with_retries(
                    target="monitor",
                    push_fn=lambda: MonitorLinkage().ingest_from_source(
                        **envelope,
                        allowed_org_ids=allowed_org_ids,
                        operator=operator,
                    ),
                    max_attempts=attempts_limit,
                    on_success=lambda result: cls._backfill_id(node, "monitor_id", result),
                )
            else:
                logger.warning("[ModulePush] unknown target=%s node_id=%s", target, node_id)
                status = PushTargetStatus(state="skipped", error=f"unknown target: {target}", attempts=0)

            push_status[target] = {
                "state": status.state,
                "error": status.error,
                "attempts": status.attempts,
            }
            results[target] = status

        node.push_status = push_status
        # 回填字段已在 on_success 写入 node 实例；统一落库
        node.save(update_fields=["cmdb_id", "monitor_id", "push_status", "updated_at"])
        return results

    @classmethod
    def _build_envelope(cls, node: Node) -> dict[str, Any]:
        org_ids = list(
            NodeOrganization.objects.filter(node=node).values_list("organization", flat=True)
        )
        cloud_region = node.cloud_region
        raw: dict[str, Any] = {
            "ip": node.ip,
            "name": node.name,
            "operating_system": node.operating_system,
            "cloud_region_id": cloud_region.id if cloud_region else None,
            "cloud_region_name": cloud_region.name if cloud_region else "",
            "organization_ids": org_ids,
        }
        envelope = IngestEnvelope(
            source_module="node_mgmt",
            source_id=str(node.id),
            event_type=EVENT_UPSERT,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw=raw,
            link_ids={"node_id": str(node.id)},
        )
        return {
            "source_module": envelope.source_module,
            "source_id": envelope.source_id,
            "event_type": envelope.event_type,
            "occurred_at": envelope.occurred_at,
            "raw": envelope.raw,
            "link_ids": envelope.link_ids,
        }

    @classmethod
    def _push_with_retries(
        cls,
        *,
        target: str,
        push_fn,
        max_attempts: int,
        on_success,
    ) -> PushTargetStatus:
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = push_fn()
                if isinstance(result, dict) and result.get("conflict"):
                    # conflict：不回填 id，状态记为 conflict（也可视为 skipped）
                    return PushTargetStatus(
                        state="conflict",
                        error=str(result.get("conflict")),
                        attempts=attempt,
                    )
                on_success(result if isinstance(result, dict) else {})
                return PushTargetStatus(state="ok", attempts=attempt)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "[ModulePush] target=%s attempt=%s/%s failed: %s",
                    target,
                    attempt,
                    max_attempts,
                    last_error,
                )
        return PushTargetStatus(state="skipped", error=last_error, attempts=max_attempts)

    @classmethod
    def _backfill_id(cls, node: Node, field: str, result: dict[str, Any]) -> None:
        result_id = result.get("id")
        if result_id is None:
            return
        setattr(node, field, str(result_id))
