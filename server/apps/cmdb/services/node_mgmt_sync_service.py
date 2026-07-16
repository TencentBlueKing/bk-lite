from __future__ import annotations

import copy
import os
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.timezone import localtime, now

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger
from apps.rpc.node_mgmt import NodeMgmt


def _get_positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


class NodeMgmtSyncError(RuntimeError):
    """节点管理同步的稳定、可安全外显错误。"""


class NodeMgmtSyncService:
    ACTIVE_SCOPE = "node_mgmt_sync"
    RUN_TIMEOUT_MINUTES = 30
    REASON_ALREADY_ACTIVE = "RUN_ALREADY_ACTIVE"
    REASON_TIMEOUT = "RUN_TIMEOUT"
    TERMINAL_STATUSES = (
        NodeMgmtSyncRun.STATUS_SUCCESS,
        NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        NodeMgmtSyncRun.STATUS_BLOCKED,
        NodeMgmtSyncRun.STATUS_FAILED,
        NodeMgmtSyncRun.STATUS_TIMEOUT,
    )
    ACTIVE_STATUSES = (
        NodeMgmtSyncRun.STATUS_RUNNING,
        NodeMgmtSyncRun.STATUS_WAITING_SYNC,
        NodeMgmtSyncRun.STATUS_SUBMITTED,
    )
    SYNC_PERIODIC_TASK_NAME = "cmdb_node_mgmt_sync_hosts"
    COLLECT_PERIODIC_TASK_NAME = "cmdb_node_mgmt_collect_hosts"
    SYNC_TASK = "apps.cmdb.tasks.celery_tasks.sync_node_mgmt_hosts"
    COLLECT_TASK = "apps.cmdb.tasks.celery_tasks.collect_node_mgmt_hosts"
    SYSTEM_TASK_PREFIX = "node_mgmt_sync_host_collect_"
    SYSTEM_SOURCE = "node_mgmt_sync"
    TASK_NAME = "节点管理同步"
    EMPTY_NODE_CREDENTIAL = {"password": "", "username": "", "port": 22}
    NODE_TYPE_CONTAINER = "container"
    DISPLAY_SOURCE_SYNC = "sync"
    DISPLAY_SOURCE_COLLECT = "collect"
    DISPLAY_SOURCE_SYNC_FALLBACK = "sync_fallback"
    DISPLAY_SOURCE_NONE = "none"
    NODE_MGMT_SYNC_PAGE_SIZE = _get_positive_int_env("CMDB_NODE_MGMT_SYNC_PAGE_SIZE", 500)
    NODE_PAGE_SIZE = 500
    MAX_NODE_PAGES = 100
    SYSTEM_NODE_QUERY = {"skip_permission": True}
    RAW_DATA_FIELDS = (
        "id",
        "_id",
        "model_id",
        "inst_name",
        "name",
        "ip_addr",
        "ip",
        "cloud",
        "cloud_id",
        "cloud_name",
        "organization",
        "organization_ids",
        "__time__",
        "_status",
        "_error",
    )
    HOST_SYNC_UPDATE_FIELDS = ("inst_name", "ip_addr", "organization", "cloud", "os_type")

    @staticmethod
    def _empty_display_message() -> dict[str, Any]:
        return {
            "all": 0,
            "add": 0,
            "update": 0,
            "delete": 0,
            "association": 0,
            "add_error": 0,
            "add_success": 0,
            "update_error": 0,
            "update_success": 0,
            "delete_error": 0,
            "delete_success": 0,
            "association_error": 0,
            "association_success": 0,
            "message": "",
        }

    @staticmethod
    def _empty_display_detail() -> dict[str, Any]:
        return {
            "add": {"data": [], "count": 0},
            "update": {"data": [], "count": 0},
            "delete": {"data": [], "count": 0},
            "relation": {"data": [], "count": 0},
            "raw_data": {"data": [], "count": 0},
            "todo": [],
        }

    @staticmethod
    def _safe_count(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _normalize_detail_bucket(cls, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            data = payload.get("data", [])
        elif isinstance(payload, list):
            data = payload
        else:
            data = []
        if not isinstance(data, list):
            data = []
        return {"data": [cls._sanitize_raw_data_item(item) if isinstance(item, dict) else item for item in data], "count": len(data)}

    @classmethod
    def _sanitize_raw_data_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        sanitized = {key: item.get(key) for key in cls.RAW_DATA_FIELDS if key in item}
        if sanitized.get("model_id") in (None, ""):
            sanitized["model_id"] = "host"
        return sanitized

    @classmethod
    def _normalize_display_message(cls, summary: dict[str, Any] | None) -> dict[str, Any]:
        summary = summary or {}
        message = cls._empty_display_message()
        if not isinstance(summary, dict):
            return message

        message["all"] = cls._safe_count(summary.get("all"))
        for key, legacy_key in (
                ("add", "add_count"),
                ("update", "update_count"),
                ("delete", "delete_count"),
                ("association", "conflict_count"),
        ):
            message[key] = cls._safe_count(summary.get(key, summary.get(legacy_key)))
            error_key = f"{key}_error"
            success_key = f"{key}_success"
            message[error_key] = cls._safe_count(summary.get(error_key))
            if summary.get(success_key) is not None:
                message[success_key] = cls._safe_count(summary.get(success_key))
            else:
                message[success_key] = max(message[key] - message[error_key], 0)

        if summary.get("message"):
            message["message"] = str(summary.get("message") or "")
        if summary.get("last_time"):
            message["last_time"] = str(summary.get("last_time") or "")
        return message

    @classmethod
    def _normalize_display_detail(cls, detail: dict[str, Any] | None) -> dict[str, Any]:
        detail = detail or {}
        normalized = cls._empty_display_detail()
        if not isinstance(detail, dict):
            return normalized

        normalized["add"] = cls._normalize_detail_bucket(detail.get("add"))
        normalized["update"] = cls._normalize_detail_bucket(detail.get("update"))
        normalized["delete"] = cls._normalize_detail_bucket(detail.get("delete"))
        normalized["relation"] = cls._normalize_detail_bucket(
            detail.get("relation") or detail.get("association") or detail.get("conflict")
        )
        normalized["raw_data"] = cls._normalize_detail_bucket(
            detail.get("raw_data") or detail.get("__raw_data__")
        )

        if normalized["raw_data"]["count"] == 0:
            derived_raw_data = []
            for key in ("add", "update", "delete", "relation"):
                derived_raw_data.extend(normalized[key]["data"])
            normalized["raw_data"] = {"data": derived_raw_data, "count": len(derived_raw_data)}

        todo = detail.get("todo")
        normalized["todo"] = todo if isinstance(todo, list) else []
        return normalized

    @classmethod
    def _has_display_data(cls, detail: dict[str, Any] | None) -> bool:
        detail = detail or {}
        return any(
            cls._safe_count((detail.get(key) or {}).get("count"))
            for key in ("add", "update", "delete", "relation", "raw_data")
        ) or bool(detail.get("todo"))

    @staticmethod
    def _merge_detail_bucket(target: dict[str, Any], bucket: dict[str, Any]) -> None:
        target["data"].extend(bucket.get("data") or [])
        target["count"] = len(target["data"])

    @classmethod
    def _fallback_collect_raw_data(cls, task: CollectModels) -> list[dict[str, Any]]:
        instances = task.instances if isinstance(task.instances, list) else []
        fallback_rows: list[dict[str, Any]] = []
        for item in instances:
            if not isinstance(item, dict):
                continue
            payload = cls._sanitize_raw_data_item(item)
            payload.setdefault("model_id", task.model_id or "host")
            payload.setdefault("inst_name", item.get("inst_name") or item.get("name") or "")
            payload.setdefault("ip_addr", item.get("ip_addr") or item.get("ip") or "")
            payload.setdefault("cloud_name", item.get("cloud_name") or "")
            payload.setdefault("_status", cls._collect_status_to_text(task.exec_status))
            payload.setdefault("_error", "")
            fallback_rows.append(payload)
        return fallback_rows

    @classmethod
    def get_task(cls) -> NodeMgmtSyncConfig:
        task = NodeMgmtSyncConfig.objects.order_by("id").first()
        if task:
            updated = False
            if not getattr(task, "name", ""):
                task.name = cls.TASK_NAME
                updated = True
            if getattr(task, "is_builtin", None) is not True:
                task.is_builtin = True
                updated = True
            if updated:
                task.save(update_fields=["name", "is_builtin", "updated_at"])
            return task
        return NodeMgmtSyncConfig.objects.create(name=cls.TASK_NAME, is_builtin=True)

    @classmethod
    def get_config(cls) -> NodeMgmtSyncConfig:
        return cls.get_task()

    @staticmethod
    def _build_cycle(minutes: int) -> str:
        return f"*/{int(minutes)} * * * *"

    @classmethod
    def _sync_collect_node_configs(cls, *, enabled: bool) -> None:
        from apps.cmdb.services.collect_service import CollectModelService

        for collect_task in cls._list_region_collect_tasks():
            if not CollectModelService.should_sync_node_params(collect_task):
                continue
            if enabled:
                CollectModelService.delete_butch_node_params(collect_task)
                CollectModelService.push_butch_node_params(collect_task)
            else:
                CollectModelService.delete_butch_node_params(collect_task)

    @staticmethod
    def _validate_task_update(data: dict[str, Any]) -> dict[str, Any]:
        validated = dict(data)
        for field in ("sync_interval_minutes", "collect_interval_minutes"):
            if field not in validated:
                continue
            value = validated[field]
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError(f"{field} 必须在 1 到 1440 分钟之间")
            if isinstance(value, str):
                if not value.isascii() or not value.isdecimal():
                    raise ValueError(f"{field} 必须在 1 到 1440 分钟之间")
                value = int(value)
            if not 1 <= value <= 1440:
                raise ValueError(f"{field} 必须在 1 到 1440 分钟之间")
            validated[field] = value
        return validated

    @classmethod
    def update_task(cls, data: dict[str, Any]) -> NodeMgmtSyncConfig:
        data = cls._validate_task_update(data)
        task = cls.get_task()
        old_auto_collect_enabled = task.auto_collect_enabled

        with transaction.atomic():
            task.auto_sync_enabled = bool(data.get("auto_sync_enabled", task.auto_sync_enabled))
            task.auto_collect_enabled = bool(data.get("auto_collect_enabled", task.auto_collect_enabled))
            task.sync_interval_minutes = int(data.get("sync_interval_minutes", task.sync_interval_minutes))
            task.collect_interval_minutes = int(data.get("collect_interval_minutes", task.collect_interval_minutes))
            if task.auto_collect_enabled and not task.auto_sync_enabled:
                task.node_config_status = "waiting_sync"
            task.name = cls.TASK_NAME
            task.is_builtin = True
            task.version += 1
            task.save()

        from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

        NodeMgmtSyncReconciler.reconcile(
            task, reconcile_node_configs=task.auto_sync_enabled and old_auto_collect_enabled != task.auto_collect_enabled,
        )

        return task

    @classmethod
    def update_config(cls, data: dict[str, Any]) -> NodeMgmtSyncConfig:
        return cls.update_task(data)

    @classmethod
    def sync_periodic_tasks(cls, task: NodeMgmtSyncConfig) -> None:
        from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

        NodeMgmtSyncReconciler.reconcile(task)

    @classmethod
    def get_task_payload(cls, *, reconcile: bool = True) -> dict[str, Any]:
        task = cls.get_task()
        if reconcile:
            from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

            NodeMgmtSyncReconciler.reconcile(task)
            task.refresh_from_db()
        return cls.serialize_task(task)

    @staticmethod
    def _serialize_dt(value):
        if not value:
            return None
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return localtime(value).strftime("%Y-%m-%d %H:%M:%S%z")

    @classmethod
    def serialize_task(cls, task: NodeMgmtSyncConfig | None = None) -> dict[str, Any]:
        task = task or cls.get_task()
        health = {
            "schedule_status": task.schedule_status,
            "node_config_status": task.node_config_status,
            "last_reconciled_at": cls._serialize_dt(task.last_reconciled_at),
            "reason_code": task.reconcile_error_code,
            "message": task.reconcile_error_message,
        }
        return {
            "id": task.id,
            "name": task.name,
            "is_builtin": task.is_builtin,
            "auto_sync_enabled": task.auto_sync_enabled,
            "auto_collect_enabled": task.auto_collect_enabled,
            "sync_interval_minutes": task.sync_interval_minutes,
            "collect_interval_minutes": task.collect_interval_minutes,
            "version": task.version,
            "schedule_status": task.schedule_status,
            "node_config_status": task.node_config_status,
            "last_reconciled_at": cls._serialize_dt(task.last_reconciled_at),
            "reconcile_error_code": task.reconcile_error_code,
            "reconcile_error_message": task.reconcile_error_message,
            "health": health,
            "last_sync_at": cls._serialize_dt(task.last_sync_at),
            "last_collect_at": cls._serialize_dt(task.last_collect_at),
        }

    @classmethod
    def serialize_config(cls, config: NodeMgmtSyncConfig | None = None) -> dict[str, Any]:
        return cls.serialize_task(config)

    @classmethod
    def serialize_run(cls, run: NodeMgmtSyncRun | None) -> dict[str, Any]:
        if not run:
            return {
                "id": None,
                "task_id": cls.get_task().id,
                "run_type": None,
                "status": None,
                "started_at": None,
                "finished_at": None,
                "message": cls._empty_display_message(),
                "summary": cls._empty_display_message(),
                "detail": cls._empty_display_detail(),
                "error_message": "",
            }
        message = cls._normalize_display_message(run.summary_json or {})
        detail = cls._normalize_display_detail(run.detail_json or {})
        return {
            "id": run.id,
            "task_id": run.task_id,
            "run_type": run.run_type,
            "status": run.status,
            "started_at": cls._serialize_dt(run.started_at),
            "finished_at": cls._serialize_dt(run.finished_at),
            "message": message,
            "summary": message,
            "detail": detail,
            "error_message": run.error_message or "",
        }

    @classmethod
    def get_latest_run(cls, run_type: str, task: NodeMgmtSyncConfig | None = None) -> NodeMgmtSyncRun | None:
        task = task or cls.get_task()
        return task.runs.filter(run_type=run_type).order_by("-created_at").first()

    @classmethod
    def get_latest_run_payload(cls, run_type: str, task: NodeMgmtSyncConfig | None = None) -> dict[str, Any]:
        return cls.serialize_run(cls.get_latest_run(run_type, task=task))

    @classmethod
    def _build_sync_run(cls, task: NodeMgmtSyncConfig | None = None) -> NodeMgmtSyncRun:
        return cls.acquire_run(NodeMgmtSyncRun.RUN_TYPE_SYNC, task=task)

    @classmethod
    def _build_collect_run(cls, task: NodeMgmtSyncConfig | None = None) -> NodeMgmtSyncRun:
        return cls.acquire_run(NodeMgmtSyncRun.RUN_TYPE_COLLECT, task=task)

    @classmethod
    def acquire_run(
        cls, run_type: str, task: NodeMgmtSyncConfig | None = None
    ) -> NodeMgmtSyncRun:
        task = task or cls.get_task()
        current_time = now()
        try:
            # 失败的 INSERT 必须由内层 savepoint 回滚，否则外层事务会进入
            # rollback-only，无法再写 blocked 历史记录。
            with transaction.atomic():
                return NodeMgmtSyncRun.objects.create(
                    task=task,
                    run_type=run_type,
                    status=NodeMgmtSyncRun.STATUS_RUNNING,
                    active_scope=cls.ACTIVE_SCOPE,
                    started_at=current_time,
                    heartbeat_at=current_time,
                    deadline_at=current_time
                    + timedelta(minutes=cls.RUN_TIMEOUT_MINUTES),
                )
        except IntegrityError:
            return NodeMgmtSyncRun.objects.create(
                task=task,
                run_type=run_type,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code=cls.REASON_ALREADY_ACTIVE,
                started_at=current_time,
                finished_at=current_time,
            )

    @classmethod
    def finish_run(
        cls,
        run: NodeMgmtSyncRun,
        *,
        status: str,
        reason_code: str = "",
        summary_json: dict[str, Any] | None = None,
        detail_json: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> NodeMgmtSyncRun:
        if status not in cls.TERMINAL_STATUSES:
            raise ValueError("finish_run requires a terminal status")
        current_time = now()
        updates: dict[str, Any] = {
            "status": status,
            "reason_code": reason_code,
            "active_scope": None,
            "finished_at": current_time,
            "updated_at": current_time,
        }
        if summary_json is not None:
            updates["summary_json"] = summary_json
        if detail_json is not None:
            updates["detail_json"] = detail_json
        if error is not None:
            updates["error_message"] = (
                f"{reason_code or 'RUN_FAILED'}: {type(error).__name__}"[:255]
            )
        lease = NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            status__in=cls.ACTIVE_STATUSES,
        )
        if status in (
            NodeMgmtSyncRun.STATUS_SUCCESS,
            NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        ):
            lease = lease.filter(
                active_scope=cls.ACTIVE_SCOPE,
                deadline_at__gt=current_time,
            )
        updated = lease.update(**updates)
        run.refresh_from_db()
        if not updated and status in (
            NodeMgmtSyncRun.STATUS_SUCCESS,
            NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        ):
            cls.heartbeat_run(run)
            raise NodeMgmtSyncError("RUN_NOT_ACTIVE")
        return run

    @classmethod
    def heartbeat_run(cls, run: NodeMgmtSyncRun) -> None:
        if run.active_scope is None and run.deadline_at is None:
            # 内部 helper 的无执行上下文调用不参与运行租约；正式入口必有两字段。
            return
        current_time = now()
        updated = NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            active_scope=cls.ACTIVE_SCOPE,
            deadline_at__gt=current_time,
        ).exclude(status__in=cls.TERMINAL_STATUSES).update(
            heartbeat_at=current_time,
            updated_at=current_time,
        )
        if updated:
            run.heartbeat_at = current_time
            return
        expired = NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            active_scope=cls.ACTIVE_SCOPE,
            status__in=cls.ACTIVE_STATUSES,
            deadline_at__lte=current_time,
        ).update(
            status=NodeMgmtSyncRun.STATUS_TIMEOUT,
            reason_code=cls.REASON_TIMEOUT,
            active_scope=None,
            finished_at=current_time,
            updated_at=current_time,
        )
        run.refresh_from_db()
        if expired or (
            run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
            and run.reason_code == cls.REASON_TIMEOUT
        ):
            raise NodeMgmtSyncError(cls.REASON_TIMEOUT)
        raise NodeMgmtSyncError("RUN_NOT_ACTIVE")

    @classmethod
    def recover_stale_runs(cls) -> int:
        current_time = now()
        return NodeMgmtSyncRun.objects.filter(
            active_scope=cls.ACTIVE_SCOPE,
            status__in=cls.ACTIVE_STATUSES,
            deadline_at__lte=current_time,
        ).update(
            status=NodeMgmtSyncRun.STATUS_TIMEOUT,
            reason_code=cls.REASON_TIMEOUT,
            active_scope=None,
            finished_at=current_time,
            updated_at=current_time,
        )

    @classmethod
    def _mark_run_failed(cls, run: NodeMgmtSyncRun, error: Exception) -> None:
        """把运行记录标记为失败并写入结束时间/错误信息。

        编排过程中任意步骤抛异常时调用，避免运行记录永久停留在 RUNNING、
        被前端展示为「运行中」从而掩盖失败。
        """
        run_type = getattr(run, "run_type", "")
        action_label = "采集" if run_type == NodeMgmtSyncRun.RUN_TYPE_COLLECT else "同步"
        # 透传到页面的错误信息：带上动作语义，去掉裸异常类名噪声，便于运维定位
        page_message = "节点管理{}失败：{}".format(action_label, type(error).__name__)
        logger.error(
            "[NodeMgmtSync] 运行记录标记失败 run_id=%s, run_type=%s, error=%s",
            getattr(run, "id", None),
            run_type,
            type(error).__name__,
        )
        try:
            cls.finish_run(
                run,
                status=NodeMgmtSyncRun.STATUS_FAILED,
                reason_code="RUN_FAILED",
                error=error,
            )
            if run.status == NodeMgmtSyncRun.STATUS_FAILED:
                NodeMgmtSyncRun.objects.filter(pk=run.pk).update(
                    error_message=page_message
                )
        except Exception:  # pragma: no cover - 兜底：标记失败本身不应再抛
            logger.exception("[NodeMgmtSync] 标记运行记录失败状态时出错, run_id=%s", getattr(run, "id", None))

    @staticmethod
    def _normalize_org_ids(org_ids: list[Any] | None) -> list[int]:
        result = []
        for item in org_ids or []:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return sorted(set(result))

    @staticmethod
    def _node_mgmt_client() -> NodeMgmt:
        return NodeMgmt()

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_nodes(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            rows = payload.get("nodes", [])
            return [item for item in rows if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @classmethod
    def _cloud_region_name_map(
        cls, run: NodeMgmtSyncRun | None = None
    ) -> dict[int, str]:
        if run is not None:
            cls.heartbeat_run(run)
        rows = cls._node_mgmt_client().cloud_region_list()
        if run is not None:
            cls.heartbeat_run(run)
        result: dict[int, str] = {}
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            cloud_region_id = cls._safe_int(item.get("id"))
            if cloud_region_id is None:
                continue
            result[cloud_region_id] = str(item.get("name") or "").strip()
        return result

    @classmethod
    def _raise_for_node_response(cls, response: Any) -> None:
        if isinstance(response, dict) and response.get("result") is False:
            error_type = "remote_rejected"
        else:
            count = response.get("count") if isinstance(response, dict) else None
            nodes = response.get("nodes") if isinstance(response, dict) else None
            is_valid_count = type(count) is int and count >= 0
            is_valid_nodes = isinstance(nodes, list) and all(
                isinstance(node, dict) for node in nodes
            )
            if is_valid_count and is_valid_nodes:
                return
            error_type = "invalid_response"
        logger.error(
            "[NodeMgmtSync] 节点查询失败 code=NODE_QUERY_FAILED, error_type=%s",
            error_type,
        )
        raise NodeMgmtSyncError(f"NODE_QUERY_FAILED: {error_type}")

    @classmethod
    def _fetch_node_mgmt_pages(
        cls,
        query: dict[str, Any],
        *,
        max_pages: int = MAX_NODE_PAGES,
        deadline_at=None,
        run: NodeMgmtSyncRun | None = None,
    ) -> list[dict[str, Any]]:
        requested_page_size = query.get("page_size", cls.NODE_MGMT_SYNC_PAGE_SIZE)
        try:
            requested_page_size = int(requested_page_size)
        except (TypeError, ValueError):
            requested_page_size = cls.NODE_MGMT_SYNC_PAGE_SIZE
        page_size = min(max(1, requested_page_size), cls.NODE_PAGE_SIZE)
        max_pages = min(max(1, int(max_pages)), cls.MAX_NODE_PAGES)
        base_payload = {**query, **cls.SYSTEM_NODE_QUERY, "page_size": page_size}
        nodes: list[dict[str, Any]] = []
        client = cls._node_mgmt_client()
        for page in range(1, max_pages + 1):
            if run is not None:
                cls.heartbeat_run(run)
            if deadline_at is not None and timezone.now() >= deadline_at:
                raise NodeMgmtSyncError("NODE_QUERY_TIMEOUT")
            payload = {**base_payload, "page": page}
            try:
                rows = client.node_list(payload)
            except Exception as error:
                error_type = error.__class__.__name__[:200]
                logger.error(
                    "[NodeMgmtSync] 节点查询失败 code=NODE_QUERY_FAILED, error_type=%s",
                    error_type,
                )
                raise NodeMgmtSyncError(f"NODE_QUERY_FAILED: {error_type}"[:255]) from None
            if run is not None:
                cls.heartbeat_run(run)
            cls._raise_for_node_response(rows)
            page_nodes = cls._extract_nodes(rows)
            nodes.extend(page_nodes)
            count = cls._safe_count(rows.get("count") if isinstance(rows, dict) else len(page_nodes))
            if not page_nodes or (count > 0 and len(nodes) >= count) or len(page_nodes) < page_size:
                return nodes
        raise NodeMgmtSyncError("NODE_PAGE_LIMIT_EXCEEDED")

    @classmethod
    def _fetch_non_container_nodes(
        cls, run: NodeMgmtSyncRun | None = None
    ) -> list[dict[str, Any]]:
        logger.info("[NodeMgmtSync] 开始获取非容器节点列表")
        cloud_region_names = cls._cloud_region_name_map(run=run)
        logger.debug("[NodeMgmtSync] 获取到云区域名称映射, region_count=%d", len(cloud_region_names))
        nodes = cls._fetch_node_mgmt_pages(
            {"is_container": False},
            deadline_at=getattr(run, "deadline_at", None),
            run=run,
        )
        total_nodes = len(nodes)
        logger.info("[NodeMgmtSync] 从节点管理获取到节点数据, total=%d", total_nodes)
        result: list[dict[str, Any]] = []
        skipped_count = 0
        for node in nodes:
            cloud_region_id = cls._safe_int(node.get("cloud_region_id") or node.get("cloud_region"))
            if cloud_region_id is None:
                skipped_count += 1
                continue
            result.append(
                {
                    "id": node.get("id"),
                    "inst_name": node.get("name") or str(node.get("ip") or ""),
                    "ip": node.get("ip"),
                    "ip_addr": str(node.get("ip") or "").strip(),
                    "cloud_region_id": cloud_region_id,
                    "cloud_region_name": str(
                        node.get("cloud_region_name") or cloud_region_names.get(cloud_region_id) or ""),
                    "cloud_name": str(node.get("cloud_region_name") or cloud_region_names.get(cloud_region_id) or ""),
                    "operating_system": node.get("operating_system"),
                    "os_type": node.get("operating_system") or "other",
                    "node_type": node.get("node_type"),
                    "organization_ids": cls._normalize_org_ids(node.get("organization")),
                    "organization": cls._normalize_org_ids(node.get("organization")),
                    "model_id": "host",
                    "_status": "success",
                    "_error": "",
                }
            )
        logger.info("[NodeMgmtSync] 非容器节点过滤完成, valid=%d, skipped=%d", len(result), skipped_count)
        return result

    @classmethod
    def _group_nodes_by_region(cls, nodes: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for node in nodes:
            region_id = node.get("cloud_region_id")
            if region_id in (None, ""):
                continue
            grouped.setdefault(int(region_id), []).append(node)
        return grouped

    @classmethod
    def _pick_access_point(
        cls,
        cloud_region_id: int,
        run: NodeMgmtSyncRun | None = None,
    ) -> dict[str, Any] | None:
        logger.debug("[NodeMgmtSync] 查找云区域接入点, cloud_region_id=%d", cloud_region_id)
        cloud_region_name = cls._cloud_region_name_map(run=run).get(
            int(cloud_region_id), ""
        )
        nodes = cls._fetch_node_mgmt_pages(
            {"cloud_region_id": cloud_region_id, "is_container": True},
            deadline_at=getattr(run, "deadline_at", None),
            run=run,
        )
        if not nodes:
            logger.warning("[NodeMgmtSync] 云区域无可用容器节点作为接入点, cloud_region_id=%d", cloud_region_id)
            return None
        node = max(nodes, key=lambda item: str(item.get("updated_at") or ""))
        logger.debug("[NodeMgmtSync] 选中接入点, cloud_region_id=%d, node_id=%s, node_name=%s",
                     cloud_region_id, node.get("id"), node.get("name"))
        return {
            "id": node.get("id"),
            "name": node.get("name"),
            "cloud": int(cloud_region_id),
            "cloud_name": cloud_region_name,
        }

    @classmethod
    def _system_code(cls, cloud_region_id: int) -> str:
        return f"{cls.SYSTEM_TASK_PREFIX}{cloud_region_id}"

    @classmethod
    def _task_name(cls, cloud_region_name: str, cloud_region_id: int) -> str:
        label = cloud_region_name or str(cloud_region_id)
        return f"节点管理主机自动采集-{label}"

    @classmethod
    def _build_scan_cycle(cls, minutes: int) -> dict[str, Any]:
        return {"value_type": "cycle", "value": int(minutes)}

    @staticmethod
    def _normalize_sync_snapshot(payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: NodeMgmtSyncService._normalize_sync_snapshot(value) for key, value in sorted(payload.items())}
        if isinstance(payload, list):
            normalized_items = [NodeMgmtSyncService._normalize_sync_snapshot(item) for item in payload]
            if all(isinstance(item, dict) for item in normalized_items):
                return sorted(
                    normalized_items,
                    key=lambda item: (
                        str(item.get("id") or ""),
                        str(item.get("ip_addr") or item.get("ip") or ""),
                        str(item.get("inst_name") or ""),
                    ),
                )
            return normalized_items
        return payload

    @classmethod
    def _should_repush_collect_task_node_params(
            cls,
            old_task: CollectModels,
            new_task: CollectModels,
    ) -> bool:
        old_snapshot = {
            "instances": cls._normalize_sync_snapshot(getattr(old_task, "instances", [])),
            "access_point": cls._normalize_sync_snapshot(getattr(old_task, "access_point", [])),
        }
        new_snapshot = {
            "instances": cls._normalize_sync_snapshot(getattr(new_task, "instances", [])),
            "access_point": cls._normalize_sync_snapshot(getattr(new_task, "access_point", [])),
        }
        return old_snapshot != new_snapshot

    @classmethod
    def _collect_task_payload(
            cls,
            *,
            cloud_region_id: int,
            cloud_region_name: str,
            access_point: dict[str, Any] | None,
            team: list[int],
            instances: list[dict[str, Any]],
            interval_minutes: int,
    ) -> dict[str, Any]:
        return {
            "name": cls._task_name(cloud_region_name, cloud_region_id),
            "task_type": "host",
            "driver_type": "job",
            "model_id": "host",
            "timeout": 10,
            "input_method": 0,
            "team": team,
            "instances": instances,
            "access_point": [access_point] if access_point else [],
            "credential": dict(cls.EMPTY_NODE_CREDENTIAL),
            "params": {
                "source": cls.SYSTEM_SOURCE,
                "cloud": cloud_region_id,
                "cloud_name": cloud_region_name,
            },
            "is_system": True,
            "is_visible": False,
            "system_code": cls._system_code(cloud_region_id),
        }

    @classmethod
    def _ensure_region_collect_task(
            cls,
            *,
            cloud_region_id: int,
            cloud_region_name: str,
            access_point: dict[str, Any] | None,
            team: list[int],
            instances: list[dict[str, Any]],
            interval_minutes: int,
            run: NodeMgmtSyncRun | None = None,
    ) -> CollectModels:
        from apps.cmdb.services.collect_service import CollectModelService

        logger.debug("[NodeMgmtSync] 确保区域采集任务存在, cloud_region_id=%d, cloud_region_name=%s, instances_count=%d",
                     cloud_region_id, cloud_region_name, len(instances))
        auto_collect_enabled = bool(getattr(cls.get_task(), "auto_collect_enabled", False))

        if run is not None:
            cls.heartbeat_run(run)
        payload = cls._collect_task_payload(
            cloud_region_id=cloud_region_id,
            cloud_region_name=cloud_region_name,
            access_point=access_point,
            team=team,
            instances=instances,
            interval_minutes=interval_minutes,
        )
        task = CollectModels.objects.filter(system_code=cls._system_code(cloud_region_id)).first()
        if task:
            logger.debug("[NodeMgmtSync] 更新已有采集任务, task_id=%d, cloud_region_id=%d", task.id, cloud_region_id)
            old_task = copy.deepcopy(task)
            for key, value in payload.items():
                setattr(task, key, value)
            task.is_interval = True
            task.cycle_value_type = "cycle"
            task.cycle_value = str(interval_minutes)
            task.scan_cycle = cls._build_cycle(interval_minutes)
            if run is not None:
                cls.heartbeat_run(run)
            task.save()
            if run is not None:
                cls.heartbeat_run(run)
            if (
                    auto_collect_enabled
                    and CollectModelService.should_sync_node_params(task)
                    and cls._should_repush_collect_task_node_params(old_task, task)
            ):
                logger.info("[NodeMgmtSync] 采集任务参数变更, 重新推送节点参数, task_id=%d", task.id)
                if run is not None:
                    cls.heartbeat_run(run)
                CollectModelService.delete_butch_node_params(old_task)
                if run is not None:
                    cls.heartbeat_run(run)
                CollectModelService.push_butch_node_params(task)
                if run is not None:
                    cls.heartbeat_run(run)
            return task
        logger.info("[NodeMgmtSync] 创建新采集任务, cloud_region_id=%d, cloud_region_name=%s", cloud_region_id, cloud_region_name)
        if run is not None:
            cls.heartbeat_run(run)
        task = CollectModels.objects.create(
            **payload,
            created_by="system",
            updated_by="system",
            domain="domain.com",
            updated_by_domain="domain.com",
            is_interval=True,
            cycle_value_type="cycle",
            cycle_value=str(interval_minutes),
            scan_cycle=cls._build_cycle(interval_minutes),
        )
        if run is not None:
            cls.heartbeat_run(run)
        logger.info("[NodeMgmtSync] 采集任务创建成功, task_id=%d, cloud_region_id=%d", task.id, cloud_region_id)
        if auto_collect_enabled and CollectModelService.should_sync_node_params(task):
            logger.debug("[NodeMgmtSync] 推送新任务节点参数, task_id=%d", task.id)
            if run is not None:
                cls.heartbeat_run(run)
            CollectModelService.push_butch_node_params(task)
            if run is not None:
                cls.heartbeat_run(run)
        return task

    @classmethod
    def _load_existing_host_map(cls, task_id: int) -> dict[tuple[str, int], dict[str, Any]]:
        model_info = ModelManage.search_model_info("host")
        attrs = model_info.get("attrs", []) if isinstance(model_info, dict) else []
        if isinstance(attrs, str):
            attrs = []
        inst_list, _ = InstanceManage.search_inst(model_id="host")
        if not inst_list:
            return {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for item in inst_list:
            ip = str(item.get("ip_addr") or "").strip()
            cloud = item.get("cloud") or item.get("cloud_id")
            if not ip or cloud in (None, ""):
                continue
            result[(ip, int(cloud))] = item
        return result

    @classmethod
    def _query_region_host_instances(cls, cloud_region_id: int, region_nodes: list[dict[str, Any]]) -> list[
        dict[str, Any]]:
        existing_map = cls._load_existing_host_map(task_id=0)
        region_instances: list[dict[str, Any]] = []
        for node in region_nodes:
            ip = str(node.get("ip") or node.get("ip_addr") or "").strip()
            if not ip:
                continue
            instance = existing_map.get((ip, int(cloud_region_id)))
            if instance:
                region_instances.append(instance)
        return region_instances

    @classmethod
    def _host_attr_map(cls) -> dict[str, dict[str, Any]]:
        model_info = ModelManage.search_model_info("host") or {}
        attrs = model_info.get("attrs", []) if isinstance(model_info, dict) else []
        if not isinstance(attrs, list):
            return {}
        return {str(attr.get("attr_id")): attr for attr in attrs if isinstance(attr, dict) and attr.get("attr_id")}

    @classmethod
    def _map_host_os_type(cls, operating_system: Any) -> str:
        raw_value = str(operating_system or "").strip()
        if not raw_value:
            return "other"

        attr = cls._host_attr_map().get("os_type") or {}
        options = ModelManage.resolve_runtime_enum_options(attr) if attr else []
        if not isinstance(options, list):
            options = []

        normalized = raw_value.lower()
        for option in options:
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("id") or "").strip()
            option_name = str(option.get("name") or "").strip()
            if option_name and option_name.lower() in normalized:
                return option_id or "other"
            if option_id and option_id.lower() == normalized:
                return option_id

        if any(keyword in normalized for keyword in ("linux", "centos", "ubuntu", "debian", "rhel", "rocky", "alma")):
            return "1"
        if any(keyword in normalized for keyword in ("windows", "win")):
            return "2"
        if "aix" in normalized:
            return "3"
        if "unix" in normalized:
            return "4"
        return "other"

    @classmethod
    def _build_host_instance_payload(
            cls,
            *,
            node: dict[str, Any],
            collect_task_id: int,
    ) -> dict[str, Any]:
        cloud_region_id = int(node["cloud_region_id"])
        cloud_region_name = node.get("cloud_region_name") or ""
        ip = str(node.get("ip") or node.get("ip_addr") or "").strip()
        inst_name = f"{ip}[{cloud_region_name or cloud_region_id}]"
        return {
            "id": node.get("id"),
            "model_id": "host",
            "inst_name": inst_name,
            "ip_addr": ip,
            "organization": cls._normalize_org_ids(node.get("organization_ids") or node.get("organization")),
            "cloud": cloud_region_id,
            "cloud_id": cloud_region_id,
            "cloud_name": cloud_region_name,
            "os_type": cls._map_host_os_type(node.get("operating_system") or node.get("os_type")),
            "collect_task": collect_task_id,
            "node_id": node.get("id"),
            "source": cls.SYSTEM_SOURCE,
            "_status": node.get("_status") or "success",
            "_error": node.get("_error") or "",
        }

    @classmethod
    def _changed_host_attrs(cls, existing: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
        return {
            field: desired.get(field)
            for field in cls.HOST_SYNC_UPDATE_FIELDS
            if field in desired and desired.get(field) != existing.get(field)
        }

    @classmethod
    def _host_persistence_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return {field: payload.get(field) for field in cls.HOST_SYNC_UPDATE_FIELDS if field in payload}

    @classmethod
    def _host_display_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        result = cls._host_persistence_payload(payload)
        if payload.get("_id") is not None:
            result["_id"] = payload["_id"]
        return result

    @staticmethod
    def _host_lookup_key(payload: dict[str, Any]) -> tuple[str, int | None]:
        ip_addr = str(payload.get("ip_addr") or "").strip()
        cloud = payload.get("cloud")
        try:
            normalized_cloud = int(cloud) if cloud not in (None, "") else None
        except (TypeError, ValueError):
            normalized_cloud = None
        return ip_addr, normalized_cloud

    @classmethod
    def _persist_hosts(
            cls,
            desired_hosts: list[dict[str, Any]],
            *,
            existing_hosts: dict[Any, dict[str, Any]],
            operator: str,
            operation_id: str,
            run: NodeMgmtSyncRun | None = None,
    ) -> dict[str, Any]:
        result = {
            "add": 0,
            "add_success": 0,
            "add_error": 0,
            "update": 0,
            "update_success": 0,
            "update_error": 0,
            "add_data": [],
            "update_data": [],
            "errors": [],
            "changed_instance_ids": [],
        }

        for desired in desired_hosts:
            if run is not None:
                cls.heartbeat_run(run)
            persistence_payload = cls._host_persistence_payload(desired)
            ip_addr, cloud = cls._host_lookup_key(desired)
            tuple_key = (ip_addr, cloud)
            lookup_key: Any = tuple_key if tuple_key in existing_hosts else ip_addr
            existing = existing_hosts.get(lookup_key)

            if existing:
                changes = cls._changed_host_attrs(existing, desired)
                if not changes:
                    continue
                result["update"] += 1
                try:
                    if run is not None:
                        cls.heartbeat_run(run)
                    updated = InstanceManage.instance_update(
                        user_groups=[],
                        roles=[],
                        inst_id=existing["_id"],
                        update_attr=changes,
                        operator=operator,
                        allowed_org_ids=None,
                        skip_permission_check=True,
                        operation_id=operation_id,
                        schedule_post_actions=False,
                    )
                    if run is not None:
                        cls.heartbeat_run(run)
                except NodeMgmtSyncError:
                    raise
                except Exception as exc:
                    error = {"operation": "update", "error": f"HOST_UPDATE_FAILED: {type(exc).__name__}"}
                    result["update_error"] += 1
                    result["errors"].append(error)
                    logger.error("[NodeMgmtSync] 主机更新失败, error_type=%s", type(exc).__name__)
                    continue

                persisted = updated if isinstance(updated, dict) else {**existing, **changes}
                existing_hosts[lookup_key] = persisted
                result["update_success"] += 1
                result["update_data"].append(cls._host_display_payload(persisted))
                if persisted.get("_id") is not None:
                    result["changed_instance_ids"].append(persisted["_id"])
                continue

            try:
                if run is not None:
                    cls.heartbeat_run(run)
                created = InstanceManage.instance_create(
                    "host",
                    persistence_payload,
                    operator=operator,
                    allowed_org_ids=persistence_payload.get("organization", []),
                    operation_id=operation_id,
                    schedule_post_actions=False,
                )
                if run is not None:
                    cls.heartbeat_run(run)
            except NodeMgmtSyncError:
                raise
            except Exception as exc:
                error = {"operation": "add", "error": f"HOST_CREATE_FAILED: {type(exc).__name__}"}
                result["add_error"] += 1
                result["errors"].append(error)
                logger.error("[NodeMgmtSync] 主机创建失败, error_type=%s", type(exc).__name__)
                continue

            persisted = created if isinstance(created, dict) else persistence_payload
            existing_hosts[tuple_key] = persisted
            result["add"] += 1
            result["add_success"] += 1
            result["add_data"].append(cls._host_display_payload(persisted))
            if persisted.get("_id") is not None:
                result["changed_instance_ids"].append(persisted["_id"])

        return result

    @classmethod
    def _list_region_collect_tasks(cls) -> list[CollectModels]:
        return list(
            CollectModels.objects.filter(is_system=True, system_code__startswith=cls.SYSTEM_TASK_PREFIX).order_by("id"))

    @staticmethod
    def _execute_collect_task(task):
        from apps.cmdb.services.collect_service import CollectModelService

        logger.info("[NodeMgmtSync] 执行采集任务, task_id=%d, task_name=%s", task.id, task.name)
        result = CollectModelService.exec_task(
            task,
            "system",
        )
        logger.info("[NodeMgmtSync] 采集任务执行完成, task_id=%d", task.id)
        return result

    @classmethod
    def _build_collect_display_payload(cls, source: str) -> dict[str, Any] | None:
        collect_tasks = cls._list_region_collect_tasks()
        if not collect_tasks:
            return None

        detail = cls._empty_display_detail()
        message = cls._empty_display_message()

        for collect_task in collect_tasks:
            task_info = collect_task.info
            task_digest = collect_task.collect_digest if isinstance(collect_task.collect_digest, dict) else {}
            task_instances = collect_task.instances if isinstance(collect_task.instances, list) else []

            for key in ("add", "update", "delete", "relation", "raw_data"):
                bucket = task_info.get(key, {"data": [], "count": 0})
                cls._merge_detail_bucket(detail[key], bucket)

            info_has_data = any(task_info.get(k, {}).get("count", 0) for k in ("add", "update", "delete", "raw_data"))
            if not info_has_data and task_instances:
                fallback_rows = cls._fallback_collect_raw_data(collect_task)
                if fallback_rows:
                    cls._merge_detail_bucket(detail["raw_data"], {"data": fallback_rows, "count": len(fallback_rows)})

            for key in ("all", "add", "update", "delete", "association",
                        "add_error", "add_success", "update_error", "update_success",
                        "delete_error", "delete_success", "association_error", "association_success"):
                message[key] += cls._safe_count(task_digest.get(key))
            if task_digest.get("last_time"):
                message["last_time"] = task_digest["last_time"]
            if task_digest.get("message"):
                message["message"] = task_digest["message"]

        if detail["raw_data"]["count"] == 0 and message.get("all"):
            derived_raw_data = []
            for key in ("add", "update", "delete"):
                derived_raw_data.extend(detail[key]["data"])
            detail["raw_data"] = {"data": derived_raw_data, "count": len(derived_raw_data)}

        if message["all"] == 0:
            message["all"] = detail["raw_data"]["count"]

        if detail["raw_data"]["count"] > 0 and message.get("message"):
            message["message"] = ""

        latest_collect_task = max(
            collect_tasks,
            key=lambda item: item.updated_at or item.created_at or item.exec_time,
        )
        run = {
            "id": latest_collect_task.id,
            "task_id": cls.get_task().id,
            "run_type": NodeMgmtSyncRun.RUN_TYPE_COLLECT,
            "status": cls._collect_status_to_text(latest_collect_task.exec_status),
            "started_at": cls._serialize_dt(latest_collect_task.exec_time),
            "finished_at": cls._serialize_dt(latest_collect_task.updated_at),
            "message": message,
            "summary": message,
            "detail": detail,
            "error_message": (latest_collect_task.collect_digest or {}).get("message", "")
            if isinstance(latest_collect_task.collect_digest, dict)
            else "",
        }
        return {
            "display_source": source,
            "display_schema": "host_collect",
            "message": message,
            "summary": message,
            "detail": detail,
            "run": run,
        }

    @classmethod
    def _display_payload_from_collect_task(cls, task: CollectModels, source: str) -> dict[str, Any]:
        message = cls._normalize_display_message(task.collect_digest if isinstance(task.collect_digest, dict) else {})
        detail = cls._normalize_display_detail(task.info if isinstance(task.info, dict) else {})
        # Legacy safety net for already-persisted tasks that predate raw_data backfilling.
        if detail["raw_data"]["count"] == 0 and message.get("all"):
            fallback_rows = cls._fallback_collect_raw_data(task)
            detail["raw_data"] = {"data": fallback_rows, "count": len(fallback_rows)}
        return {
            "display_source": source,
            "display_schema": "host_collect",
            "message": message,
            "summary": message,
            "detail": detail,
            "run": {
                "id": task.id,
                "task_id": cls.get_task().id,
                "run_type": NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                "status": cls._collect_status_to_text(task.exec_status),
                "started_at": cls._serialize_dt(task.exec_time),
                "finished_at": cls._serialize_dt(task.updated_at),
                "message": message,
                "summary": message,
                "detail": detail,
                "error_message": (task.collect_digest or {}).get("message", "") if isinstance(task.collect_digest,
                                                                                              dict) else "",
            },
        }

    @staticmethod
    def _collect_status_to_text(status: int | None) -> str:
        status_map = {
            CollectRunStatusType.NOT_START: "unexecuted",
            CollectRunStatusType.RUNNING: "running",
            CollectRunStatusType.SUCCESS: "success",
            CollectRunStatusType.ERROR: "error",
            CollectRunStatusType.TIME_OUT: "timeout",
            CollectRunStatusType.WRITING: "writing",
            CollectRunStatusType.FORCE_STOP: "force_stop",
        }
        return status_map.get(status, "unknown")

    @classmethod
    def _list_collect_items(cls) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for task in cls._list_region_collect_tasks():
            info = task.info if isinstance(task.info, dict) else {}
            for bucket in ("add", "update", "delete"):
                bucket_data = (info.get(bucket) or {}).get("data", []) if isinstance(info.get(bucket), dict) else []
                for item in bucket_data if isinstance(bucket_data, list) else []:
                    if not isinstance(item, dict):
                        continue
                    payload = dict(item)
                    payload.setdefault("model_id", "host")
                    payload.setdefault("_status", cls._collect_status_to_text(task.exec_status))
                    payload.setdefault("_error", "")
                    items.append(payload)
        return items

    @classmethod
    def _display_payload_from_sync_run(cls, run: NodeMgmtSyncRun, source: str) -> dict[str, Any]:
        message = cls._normalize_display_message(run.summary_json or {})
        detail = cls._normalize_display_detail(run.detail_json or {})
        return {
            "display_source": source,
            "display_schema": "host_collect",
            "message": message,
            "summary": message,
            "detail": detail,
            "run": cls.serialize_run(run),
        }

    @classmethod
    def _build_empty_display_payload(cls, source: str | None = None) -> dict[str, Any]:
        task = cls.get_task()
        return {
            "task": cls.serialize_task(task),
            "display_source": source or cls.DISPLAY_SOURCE_NONE,
            "display_schema": "host_collect",
            "message": cls._empty_display_message(),
            "summary": cls._empty_display_message(),
            "detail": cls._empty_display_detail(),
            "run": cls.serialize_run(None),
        }

    @classmethod
    def get_display_payload(cls) -> dict[str, Any]:
        task = cls.get_task()
        if task.auto_collect_enabled:
            collect_payload = cls._build_collect_display_payload(cls.DISPLAY_SOURCE_COLLECT)
            if collect_payload and cls._has_display_data(collect_payload.get("detail")):
                payload = collect_payload
                payload["task"] = cls.serialize_task(task)
                return payload
            latest_collect_run = cls.get_latest_run(NodeMgmtSyncRun.RUN_TYPE_COLLECT, task=task)
            if latest_collect_run and (latest_collect_run.detail_json or latest_collect_run.summary_json):
                payload = cls._display_payload_from_sync_run(latest_collect_run, cls.DISPLAY_SOURCE_COLLECT)
                payload["task"] = cls.serialize_task(task)
                return payload
            payload = cls._build_empty_display_payload(cls.DISPLAY_SOURCE_COLLECT)
            payload["task"] = cls.serialize_task(task)
            return payload

        latest_sync_run = cls.get_latest_run(NodeMgmtSyncRun.RUN_TYPE_SYNC, task=task)
        if latest_sync_run:
            payload = cls._display_payload_from_sync_run(latest_sync_run, cls.DISPLAY_SOURCE_SYNC)
            payload["task"] = cls.serialize_task(task)
            return payload

        payload = cls._build_empty_display_payload(cls.DISPLAY_SOURCE_SYNC)
        payload["task"] = cls.serialize_task(task)
        return payload

    @classmethod
    def sync_hosts(cls) -> dict[str, Any]:
        logger.info("[NodeMgmtSync] ========== 开始同步节点管理主机 ==========")
        task_config = cls.get_task()
        logger.info("[NodeMgmtSync] 同步配置: auto_sync_enabled=%s, sync_interval=%d分钟, auto_collect_enabled=%s",
                    task_config.auto_sync_enabled, task_config.sync_interval_minutes, task_config.auto_collect_enabled)
        run = cls._build_sync_run(task=task_config)
        logger.debug("[NodeMgmtSync] 创建同步运行记录, run_id=%d", run.id)
        if run.status == NodeMgmtSyncRun.STATUS_BLOCKED:
            return cls.serialize_run(run)

        try:
            return cls._do_sync_hosts(run, task_config)
        except Exception as exc:
            cls._mark_run_failed(run, exc)
            logger.error(
                "[NodeMgmtSync] 同步失败, run_id=%s, error_type=%s",
                run.id,
                type(exc).__name__,
            )
            raise

    @classmethod
    def _do_sync_hosts(cls, run: NodeMgmtSyncRun, task_config: NodeMgmtSyncConfig) -> dict[str, Any]:
        logger.info("[NodeMgmtSync] 开始获取节点管理主机数据")
        nodes = cls._fetch_non_container_nodes(run=run)
        logger.info("[NodeMgmtSync] 获取节点完成, total_nodes=%d", len(nodes))

        grouped_nodes = cls._group_nodes_by_region(nodes)
        logger.info("[NodeMgmtSync] 节点按云区域分组完成, region_count=%d", len(grouped_nodes))

        detail = cls._empty_display_detail()
        message = cls._empty_display_message()
        changed_instance_ids: list[int] = []

        for cloud_region_id, region_nodes in grouped_nodes.items():
            cls.heartbeat_run(run)
            cloud_region_name = str(region_nodes[0].get("cloud_region_name") or cloud_region_id)
            logger.info("[NodeMgmtSync] 处理云区域: cloud_region_id=%d, cloud_region_name=%s, node_count=%d",
                        cloud_region_id, cloud_region_name, len(region_nodes))

            access_point = cls._pick_access_point(cloud_region_id, run=run)
            if access_point:
                logger.debug("[NodeMgmtSync] 云区域接入点: cloud_region_id=%d, access_point_id=%s",
                             cloud_region_id, access_point.get("id"))
            else:
                logger.warning("[NodeMgmtSync] 云区域无接入点: cloud_region_id=%d", cloud_region_id)

            team = cls._normalize_org_ids(
                [org_id for node in region_nodes for org_id in node.get("organization_ids", [])])
            existing_map = cls._load_existing_host_map(task_id=0)
            logger.debug("[NodeMgmtSync] 加载已有主机映射, existing_count=%d", len(existing_map))

            desired_hosts = []
            for node in region_nodes:
                try:
                    cls.heartbeat_run(run)
                    payload = cls._build_host_instance_payload(node=node, collect_task_id=0)
                    detail["raw_data"]["data"].append(cls._host_display_payload(payload))
                    desired_hosts.append(payload)
                except NodeMgmtSyncError:
                    raise
                except Exception as node_exc:
                    message["add_error"] += 1
                    detail["todo"].append(
                        {"operation": "add", "error": f"HOST_PAYLOAD_FAILED: {type(node_exc).__name__}"}
                    )
                    logger.error("[NodeMgmtSync] 主机载荷构建失败, error_type=%s", type(node_exc).__name__)
                    continue

            persistence = cls._persist_hosts(
                desired_hosts,
                existing_hosts=existing_map,
                operator="system",
                operation_id=str(run.generation),
                run=run,
            )
            for key in ("add", "add_success", "add_error", "update", "update_success", "update_error"):
                message[key] += persistence[key]
            detail["add"]["data"].extend(persistence["add_data"])
            detail["update"]["data"].extend(persistence["update_data"])
            detail["todo"].extend(persistence["errors"])
            changed_instance_ids.extend(persistence["changed_instance_ids"])

            logger.info("[NodeMgmtSync] 云区域主机同步完成: cloud_region_id=%d, add=%d, update=%d",
                        cloud_region_id, persistence["add_success"], persistence["update_success"])

            cls.heartbeat_run(run)
            region_instances = cls._query_region_host_instances(
                cloud_region_id, region_nodes
            )
            cls.heartbeat_run(run)
            logger.debug("[NodeMgmtSync] 查询区域主机实例, cloud_region_id=%d, instance_count=%d",
                         cloud_region_id, len(region_instances))

            collect_task = cls._ensure_region_collect_task(
                cloud_region_id=cloud_region_id,
                cloud_region_name=cloud_region_name,
                access_point=access_point,
                team=team,
                instances=region_instances,
                interval_minutes=task_config.collect_interval_minutes,
                run=run,
            )

            collect_task.instances = region_instances
            collect_task.team = team
            collect_task.access_point = [access_point] if access_point else []
            if hasattr(collect_task, "save"):
                cls.heartbeat_run(run)
                collect_task.save()
                cls.heartbeat_run(run)

            if access_point is None:
                detail["todo"].append(
                    {
                        "cloud_region_id": cloud_region_id,
                        "message": f"TODO: region {cloud_region_id} has no container node access point",
                    }
                )

        if changed_instance_ids:
            from apps.cmdb.services.auto_relation_reconcile import schedule_instance_auto_relation_reconcile

            try:
                cls.heartbeat_run(run)
                schedule_instance_auto_relation_reconcile(list(dict.fromkeys(changed_instance_ids)))
                cls.heartbeat_run(run)
            except NodeMgmtSyncError:
                raise
            except Exception as relation_exc:
                message["association_error"] += 1
                detail["todo"].append(
                    {"operation": "relation", "error": f"RELATION_RECONCILE_FAILED: {type(relation_exc).__name__}"}
                )
                logger.error("[NodeMgmtSync] 关联对账调度失败, error_type=%s", type(relation_exc).__name__)

        for key in ("add", "update", "delete", "relation", "raw_data"):
            detail[key]["count"] = len(detail[key]["data"])
        message["all"] = detail["raw_data"]["count"]
        message["delete_success"] = message["delete"]
        message["association"] = detail["relation"]["count"]
        message["association_success"] = message["association"]

        has_errors = any(
            message.get(key) for key in ("add_error", "update_error", "delete_error", "association_error")
        )
        final_status = (
            NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
            if detail["todo"] or has_errors
            else NodeMgmtSyncRun.STATUS_SUCCESS
        )
        cls.finish_run(
            run,
            status=final_status,
            summary_json=message,
            detail_json=detail,
        )
        task_config.last_sync_at = run.finished_at
        task_config.save(update_fields=["last_sync_at", "updated_at"])

        logger.info("[NodeMgmtSync] ========== 同步完成 ==========")
        logger.info("[NodeMgmtSync] 同步结果: status=%s, all=%d, add=%d, update=%d, delete=%d, todo_count=%d",
                    run.status, message["all"], message["add"], message["update"], message["delete"], len(detail["todo"]))
        return cls.serialize_run(run)

    @classmethod
    def collect_hosts(cls) -> dict[str, Any]:
        logger.info("[NodeMgmtSync] ========== 开始采集节点管理主机 ==========")
        task_config = cls.get_task()
        logger.info("[NodeMgmtSync] 采集配置: auto_collect_enabled=%s, collect_interval=%d分钟",
                    task_config.auto_collect_enabled, task_config.collect_interval_minutes)
        run = cls._build_collect_run(task=task_config)
        logger.debug("[NodeMgmtSync] 创建采集运行记录, run_id=%d", run.id)
        if run.status == NodeMgmtSyncRun.STATUS_BLOCKED:
            return cls.serialize_run(run)

        try:
            return cls._do_collect_hosts(run, task_config)
        except Exception as exc:
            cls._mark_run_failed(run, exc)
            logger.error(
                "[NodeMgmtSync] 采集失败, run_id=%s, error_type=%s",
                run.id,
                type(exc).__name__,
            )
            raise

    @classmethod
    def _do_collect_hosts(cls, run: NodeMgmtSyncRun, task_config: NodeMgmtSyncConfig) -> dict[str, Any]:
        detail = {"todo": [], "executed": [], "failed": []}
        message = cls._empty_display_message()

        collect_tasks = cls._list_region_collect_tasks()
        logger.info("[NodeMgmtSync] 获取区域采集任务列表, task_count=%d", len(collect_tasks))

        for collect_task in collect_tasks:
            cls.heartbeat_run(run)
            message["all"] += 1
            access_point = collect_task.access_point if isinstance(collect_task.access_point, list) else []
            logger.debug("[NodeMgmtSync] 检查采集任务: task_id=%d, task_name=%s, has_access_point=%s",
                         collect_task.id, collect_task.name, bool(access_point))
            if not access_point:
                logger.warning("[NodeMgmtSync] 采集任务无接入点, 跳过执行: task_id=%d, task_name=%s",
                               collect_task.id, collect_task.name)
                detail["todo"].append(
                    {
                        "task_id": collect_task.id,
                        "message": f"TODO: task {collect_task.id} has no available container node access point",
                    }
                )
                continue
            logger.info("[NodeMgmtSync] 开始执行采集任务: task_id=%d, task_name=%s", collect_task.id, collect_task.name)
            try:
                cls.heartbeat_run(run)
                cls._execute_collect_task(collect_task)
                cls.heartbeat_run(run)
            except NodeMgmtSyncError:
                raise
            except Exception as task_exc:
                # 单个采集任务下发失败不中断其余任务。
                detail["failed"].append(
                    {
                        "task_id": collect_task.id,
                        "message": f"COLLECT_SUBMIT_FAILED: {type(task_exc).__name__}",
                    }
                )
                logger.error(
                    "[NodeMgmtSync] 采集任务下发失败, task_id=%s, error_type=%s",
                    collect_task.id,
                    type(task_exc).__name__,
                )
                continue
            detail["executed"].append({"task_id": collect_task.id, "name": collect_task.name})
            logger.info("[NodeMgmtSync] 采集任务已提交: task_id=%d", collect_task.id)

        final_status = (
            NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
            if detail["todo"] or detail["failed"]
            else NodeMgmtSyncRun.STATUS_SUCCESS
        )
        cls.finish_run(
            run,
            status=final_status,
            summary_json=message,
            detail_json=detail,
        )
        task_config.last_collect_at = run.finished_at
        task_config.save(update_fields=["last_collect_at", "updated_at"])

        logger.info("[NodeMgmtSync] ========== 采集完成 ==========")
        logger.info("[NodeMgmtSync] 采集结果: status=%s, total_tasks=%d, executed=%d, skipped=%d",
                    run.status, message["all"], len(detail["executed"]), len(detail["todo"]))
        return cls.serialize_run(run)

    @classmethod
    def trigger_sync(cls) -> dict[str, Any]:
        data = cls.sync_hosts()
        return data

    @classmethod
    def trigger_collect(cls) -> dict[str, Any]:
        return cls.collect_hosts()
