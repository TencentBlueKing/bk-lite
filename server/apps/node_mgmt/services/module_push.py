"""节点跨模块推送编排：按用户所选 target 推送，有限重试，无级联。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.models.installer import ControllerTaskNode
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from apps.node_mgmt.services.module_push_contract import EVENT_LIFECYCLE, EVENT_UPSERT, IngestEnvelope, PushTargetStatus
from apps.rpc.cmdb import CMDB
from apps.rpc.monitor import Monitor

ALLOWED_PUSH_TARGETS = ("cmdb", "monitor")


def normalize_push_targets(targets: list[str] | None) -> list[str]:
    """去重并只保留合法推送目标，保持勾选顺序。"""
    seen: list[str] = []
    for raw in targets or []:
        name = str(raw or "").strip().lower()
        if name in ALLOWED_PUSH_TARGETS and name not in seen:
            seen.append(name)
    return seen


class CmdbLinkage:
    """CMDB 联动客户端：本进程执行 ingest，避免 NATS RPC 超时三次后 skipped。"""

    def ingest_from_source(self, **kwargs):
        return CMDB(is_local_client=True).ingest_from_source(**kwargs)


class MonitorLinkage:
    """监控联动客户端：本进程执行 Monitor ingest，避免 NATS handler 再嵌套调 NodeMgmt。"""

    def ingest_from_source(self, **kwargs):
        return Monitor(is_local_client=True).ingest_from_source(**kwargs)


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
    def remember_deferred_push(
        cls,
        *,
        cloud_region_id: int,
        nodes: list[dict[str, Any]],
        targets: list[str],
        actor_scope: dict[str, Any],
        task_id: int | None = None,
    ) -> int:
        """节点尚未落库时记下勾选：缓存 + 已有安装任务 result。无新表。"""
        normalized = normalize_push_targets(targets)
        if not normalized:
            return 0
        payload = {
            "targets": normalized,
            "allowed_org_ids": list(actor_scope.get("allowed_org_ids") or []),
            "operator": actor_scope.get("operator") or "",
        }
        remembered = 0
        for node in nodes:
            ip = str(node.get("ip") or "").strip()
            node_id = str(node.get("node_id") or "").strip()
            if not ip and not node_id:
                continue
            for key in cls._intent_cache_keys(cloud_region_id, ip, node_id):
                cache.set(key, payload, timeout=InstallerConstants.MODULE_PUSH_INTENT_CACHE_TTL)
            remembered += 1
        if task_id:
            cls._stamp_install_task_intent(task_id, nodes, payload)
        logger.info(
            "[ModulePush] remembered deferred push cloud_region_id=%s count=%s targets=%s",
            cloud_region_id,
            remembered,
            normalized,
        )
        return remembered

    @classmethod
    def consume_deferred_push_for_node(cls, node: Node) -> dict[str, Any] | None:
        """sidecar 首次建节点钩子：消费安装勾选；无意图则跳过。"""
        node_id = str(getattr(node, "id", "") or "")
        if not node_id:
            return None
        ip = str(getattr(node, "ip", "") or "").strip()
        cloud_region_id = getattr(node, "cloud_region_id", None)
        payload = cls._pop_intent_payload(cloud_region_id, ip, node_id)
        if not payload:
            return None
        targets = normalize_push_targets(payload.get("targets"))
        if not targets:
            logger.info("[ModulePush] deferred push consumed with empty targets node_id=%s", node_id)
            return None
        logger.info(
            "[ModulePush] consuming deferred push node_id=%s targets=%s",
            node_id,
            targets,
        )
        return cls.best_effort_push_node(
            node_id,
            targets=targets,
            actor_scope={
                "allowed_org_ids": list(payload.get("allowed_org_ids") or []),
                "operator": payload.get("operator") or "",
            },
        )

    @classmethod
    def _intent_cache_keys(cls, cloud_region_id, ip: str, node_id: str) -> list[str]:
        prefix = InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX
        keys: list[str] = []
        if node_id:
            keys.append(f"{prefix}:node:{node_id}")
        if ip and cloud_region_id is not None:
            keys.append(f"{prefix}:ip:{cloud_region_id}:{ip}")
        return keys

    @classmethod
    def _stamp_install_task_intent(cls, task_id: int, nodes: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        ips = {str(node.get("ip") or "").strip() for node in nodes if str(node.get("ip") or "").strip()}
        node_ids = {str(node.get("node_id") or "").strip() for node in nodes if str(node.get("node_id") or "").strip()}
        match = Q(task_id=task_id)
        if ips or node_ids:
            row_match = Q()
            if ips:
                row_match |= Q(ip__in=ips)
            if node_ids:
                row_match |= Q(node_id__in=node_ids)
            match &= row_match
        for task_node in ControllerTaskNode.objects.filter(match):
            result = dict(task_node.result or {})
            if result.get(InstallerConstants.MODULE_PUSH_CONSUMED_KEY):
                continue
            result[InstallerConstants.MODULE_PUSH_TARGETS_KEY] = payload["targets"]
            result[InstallerConstants.MODULE_PUSH_ACTOR_SCOPE_KEY] = {
                "allowed_org_ids": payload["allowed_org_ids"],
                "operator": payload["operator"],
            }
            task_node.result = result
            task_node.save(update_fields=["result"])

    @classmethod
    def _pop_intent_payload(cls, cloud_region_id, ip: str, node_id: str) -> dict[str, Any] | None:
        keys = cls._intent_cache_keys(cloud_region_id, ip, node_id)
        payload = None
        for key in keys:
            cached = cache.get(key)
            if isinstance(cached, dict) and cached.get("targets"):
                payload = cached
                break
        for key in keys:
            cache.delete(key)
        task_payload = cls._consume_install_task_intent(cloud_region_id, ip, node_id)
        return payload or task_payload

    @classmethod
    def _consume_install_task_intent(cls, cloud_region_id, ip: str, node_id: str) -> dict[str, Any] | None:
        match = Q(task__type="install")
        row_match = Q()
        if node_id:
            row_match |= Q(node_id=node_id)
            row_match |= Q(**{f"result__{InstallerConstants.INSTALL_NODE_ID_KEY}": node_id})
        if ip and cloud_region_id is not None:
            row_match |= Q(task__cloud_region_id=cloud_region_id, ip=ip)
        if not row_match:
            return None
        payload = None
        with transaction.atomic():
            task_nodes = list(ControllerTaskNode.objects.select_for_update().filter(match & row_match).order_by("-id")[:20])
            for task_node in task_nodes:
                result = dict(task_node.result or {})
                if result.get(InstallerConstants.MODULE_PUSH_CONSUMED_KEY):
                    continue
                targets = normalize_push_targets(result.get(InstallerConstants.MODULE_PUSH_TARGETS_KEY))
                if not targets:
                    continue
                scope = result.get(InstallerConstants.MODULE_PUSH_ACTOR_SCOPE_KEY) or {}
                if payload is None:
                    payload = {
                        "targets": targets,
                        "allowed_org_ids": list(scope.get("allowed_org_ids") or []),
                        "operator": scope.get("operator") or "",
                    }
                result[InstallerConstants.MODULE_PUSH_CONSUMED_KEY] = True
                task_node.result = result
                task_node.save(update_fields=["result"])
        return payload

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
    def best_effort_unlink_cmdb(
        cls,
        node: Node,
        *,
        actor_scope: dict[str, Any],
        max_attempts: int | None = None,
    ) -> dict[str, Any] | None:
        """删除节点时清 CMDB node_id。不要求 Node.cmdb_id 已回填，对端按 node_id 查找。失败不阻断删除。"""
        try:
            return cls.retire_linked(
                node,
                targets=["cmdb"],
                actor_scope=actor_scope,
                max_attempts=max_attempts,
            )
        except Exception:
            logger.exception(
                "[ModulePush] best-effort unlink cmdb failed node_id=%s",
                getattr(node, "id", None),
            )
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
                    push_fn=lambda env=envelope: CmdbLinkage().ingest_from_source(
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
                    push_fn=lambda: CmdbLinkage().ingest_from_source(
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
        org_ids = list(NodeOrganization.objects.filter(node=node).values_list("organization", flat=True))
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
                lambda: CmdbLinkage().ingest_from_source(
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
