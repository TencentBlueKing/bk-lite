"""节点跨模块推送编排：按用户所选 target 推送，有限重试，无级联。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.module_push_contract import (
    EVENT_LIFECYCLE,
    EVENT_UPSERT,
    IngestEnvelope,
    PushTargetStatus,
)
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor


class MonitorLinkage:
    """监控联动客户端：转发至 Monitor.ingest_from_source（NATS）。"""

    def ingest_from_source(self, **kwargs):
        return Monitor().ingest_from_source(**kwargs)


def build_module_push_actor_scope(request) -> dict[str, Any]:
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


def parse_retire_linked_flag(request) -> bool:
    """解析销毁节点时的 retire_linked；默认 False（安全）。

    优先 query，其次 body；兼容 true/1/yes/on。
    """
    raw = None
    query = getattr(request, "query_params", None)
    if query is not None and "retire_linked" in query:
        raw = query.get("retire_linked")
    elif hasattr(request, "data"):
        try:
            if "retire_linked" in request.data:
                raw = request.data.get("retire_linked")
        except Exception:
            raw = None
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off", ""):
        return False
    return False


class ModulePushService:
    DEFAULT_MAX_ATTEMPTS = 3

    @classmethod
    def best_effort_push_node(
        cls,
        node_id: str,
        *,
        targets: list[str],
        actor_scope: dict[str, Any],
        max_attempts: int | None = None,
    ) -> dict[str, Any] | None:
        """创建/补推入口的 best-effort 包装：异常不得阻断主流程。"""
        if not targets:
            return None
        try:
            return cls.push_node(
                node_id,
                targets=list(targets),
                actor_scope=actor_scope,
                max_attempts=max_attempts,
            )
        except Exception:
            logger.exception("[ModulePush] best-effort push failed node_id=%s targets=%s", node_id, targets)
            return None

    @classmethod
    def best_effort_retire_linked(
        cls,
        node: Node,
        *,
        actor_scope: dict[str, Any],
        max_attempts: int | None = None,
    ) -> dict[str, Any] | None:
        """删除节点前 best-effort 对已关联模块发 lifecycle（退役）；失败不阻断删除。"""
        targets: list[str] = []
        if str(getattr(node, "cmdb_id", "") or "").strip():
            targets.append("cmdb")
        if str(getattr(node, "monitor_id", "") or "").strip():
            targets.append("monitor")
        if not targets:
            return None
        try:
            return cls.retire_linked(
                node,
                targets=targets,
                actor_scope=actor_scope,
                max_attempts=max_attempts,
            )
        except Exception:
            logger.exception(
                "[ModulePush] best-effort retire failed node_id=%s targets=%s",
                getattr(node, "id", None),
                targets,
            )
            return None

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
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""

        push_status = dict(node.push_status or {})
        results: dict[str, Any] = {}

        for target in targets:
            # 每个 target 前重建信封，带上前面 target 已回填的对端 ID
            envelope = cls._build_envelope(node)
            if target == "cmdb":
                status = cls._push_with_retries(
                    target="cmdb",
                    push_fn=lambda env=envelope: CMDB().ingest_from_source(
                        **env,
                        allowed_org_ids=allowed_org_ids,
                        operator=operator,
                    ),
                    max_attempts=attempts_limit,
                    on_success=lambda result: cls._backfill_id(node, "cmdb_id", result),
                )
            elif target == "monitor":
                status = cls._push_with_retries(
                    target="monitor",
                    push_fn=lambda env=envelope: MonitorLinkage().ingest_from_source(
                        **env,
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

        # 两侧均已关联时，把完整 link_ids 回写对端（补 monitor_id / cmdb_id，不新建、不级联未选模块）
        cls._best_effort_sync_mutual_link_ids(
            node,
            actor_scope=actor_scope,
            max_attempts=1,
        )
        return results

    @classmethod
    def retire_linked(
        cls,
        node: Node,
        *,
        targets: list[str],
        actor_scope: dict[str, Any],
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        """向已关联模块发送 lifecycle 退役事件；不回填、不改 push_status（节点即将删除）。"""
        attempts_limit = max_attempts if max_attempts is not None else cls.DEFAULT_MAX_ATTEMPTS
        attempts_limit = max(1, int(attempts_limit))

        envelope = cls._build_lifecycle_envelope(node)
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""
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
                    on_success=lambda _result: None,
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
                    on_success=lambda _result: None,
                )
            else:
                logger.warning(
                    "[ModulePush] unknown retire target=%s node_id=%s",
                    target,
                    node.id,
                )
                status = PushTargetStatus(
                    state="skipped",
                    error=f"unknown target: {target}",
                    attempts=0,
                )
            results[target] = status
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
        link_ids: dict[str, Any] = {"node_id": str(node.id)}
        cmdb_id = str(getattr(node, "cmdb_id", "") or "").strip()
        monitor_id = str(getattr(node, "monitor_id", "") or "").strip()
        if cmdb_id:
            link_ids["cmdb_id"] = cmdb_id
        if monitor_id:
            link_ids["monitor_id"] = monitor_id
        envelope = IngestEnvelope(
            source_module="node_mgmt",
            source_id=str(node.id),
            event_type=EVENT_UPSERT,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw=raw,
            link_ids=link_ids,
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
    def _best_effort_sync_mutual_link_ids(
        cls,
        node: Node,
        *,
        actor_scope: dict[str, Any],
        max_attempts: int = 1,
    ) -> None:
        """节点已持有 cmdb_id + monitor_id 时，把完整 link_ids 回写两侧。

        只补关联指针，不改变 push_status；失败仅打日志。
        """
        cmdb_id = str(getattr(node, "cmdb_id", "") or "").strip()
        monitor_id = str(getattr(node, "monitor_id", "") or "").strip()
        if not cmdb_id or not monitor_id:
            return

        envelope = cls._build_envelope(node)
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""
        attempts_limit = max(1, int(max_attempts))

        for target, push_fn in (
            (
                "cmdb",
                lambda: CMDB().ingest_from_source(
                    **envelope,
                    allowed_org_ids=allowed_org_ids,
                    operator=operator,
                ),
            ),
            (
                "monitor",
                lambda: MonitorLinkage().ingest_from_source(
                    **envelope,
                    allowed_org_ids=allowed_org_ids,
                    operator=operator,
                ),
            ),
        ):
            status = cls._push_with_retries(
                target=target,
                push_fn=push_fn,
                max_attempts=attempts_limit,
                on_success=lambda _result: None,
            )
            if status.state != "ok":
                logger.warning(
                    "[ModulePush] mutual link sync %s failed node_id=%s error=%s",
                    target,
                    node.id,
                    status.error,
                )

    @classmethod
    def _build_lifecycle_envelope(cls, node: Node) -> dict[str, Any]:
        link_ids: dict[str, Any] = {"node_id": str(node.id)}
        cmdb_id = str(getattr(node, "cmdb_id", "") or "").strip()
        monitor_id = str(getattr(node, "monitor_id", "") or "").strip()
        if cmdb_id:
            link_ids["cmdb_id"] = cmdb_id
        if monitor_id:
            link_ids["monitor_id"] = monitor_id
        envelope = IngestEnvelope(
            source_module="node_mgmt",
            source_id=str(node.id),
            event_type=EVENT_LIFECYCLE,
            occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            raw={"action": "retire"},
            link_ids=link_ids,
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
