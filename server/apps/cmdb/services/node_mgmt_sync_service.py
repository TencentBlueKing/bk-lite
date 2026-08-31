from __future__ import annotations

import copy
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import localtime, now

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRegionSnapshot, NodeMgmtSyncRegionState, NodeMgmtSyncRun, NodeMgmtSyncSnapshotRow
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.host_sync_identity import (
    build_host_inst_name,
    host_lookup_key,
    is_node_mgmt_sidecar_id,
    is_unique_conflict,
    node_id_to_write,
    normalize_link_id,
    resolve_host_identity,
)
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.node_mgmt_sync_raw import (
    RAW_DATA_FIELDS,
    RAW_DATA_METRIC_MODEL_IDS,
    RAW_DEFAULT_TEXT_LIMIT,
    RAW_TEXT_LIMITS,
    sanitize_node_mgmt_raw_data_item,
    sanitize_node_mgmt_raw_text,
)
from apps.core.logger import cmdb_logger as logger
from apps.rpc.node_mgmt import NodeMgmt

# 推送联动与拉同步共用身份后，默认允许拉取；紧急硬关可改回 True。
PUSH_LINKAGE_REPLACES_PULL_SYNC = False


def _get_positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _get_bounded_positive_int_env(name, default, hard_max):
    return min(_get_positive_int_env(name, default), hard_max)


class NodeMgmtSyncError(RuntimeError):
    """节点管理同步的稳定、可安全外显错误。"""


class NodeMgmtSyncService:
    ACTIVE_SCOPE = "node_mgmt_sync"
    RUN_TIMEOUT_MINUTES = 30
    CONFIG_UPDATE_MAX_RETRIES = 4
    CONFIG_UPDATE_RETRY_BASE_SECONDS = 0.05
    COLLECT_DISPATCH_MAX_RETRIES = 3
    COLLECT_DISPATCH_CLAIM_TIMEOUT_SECONDS = 120
    REASON_ALREADY_ACTIVE = "RUN_ALREADY_ACTIVE"
    REASON_TIMEOUT = "RUN_TIMEOUT"
    REASON_NODE_SOURCE_EMPTY = "NODE_SOURCE_EMPTY"
    REASON_NO_VALID_NODES = "NO_VALID_NODES"
    REASON_PUSH_LINKAGE_REPLACES_PULL = "PUSH_LINKAGE_REPLACES_PULL"
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
    HARD_MAX_NODE_COUNT = NODE_PAGE_SIZE * MAX_NODE_PAGES
    HARD_MAX_NODE_BYTES = 128 * 1024 * 1024
    SNAPSHOT_MAX_ROWS = _get_bounded_positive_int_env("CMDB_NODE_MGMT_SNAPSHOT_MAX_ROWS", 20_000, 50_000)
    SNAPSHOT_MAX_BYTES = _get_bounded_positive_int_env(
        "CMDB_NODE_MGMT_SNAPSHOT_MAX_BYTES",
        32 * 1024 * 1024,
        64 * 1024 * 1024,
    )
    SNAPSHOT_INPUT_MAX_ROWS = 50_000
    SNAPSHOT_BULK_BATCH_SIZE = 500
    SNAPSHOT_CAPTURE_LEASE_SECONDS = 60
    MAX_NODE_COUNT = _get_bounded_positive_int_env(
        "CMDB_NODE_MGMT_MAX_NODE_COUNT",
        HARD_MAX_NODE_COUNT,
        HARD_MAX_NODE_COUNT,
    )
    MAX_NODE_BYTES = _get_bounded_positive_int_env(
        "CMDB_NODE_MGMT_MAX_NODE_BYTES",
        HARD_MAX_NODE_BYTES,
        HARD_MAX_NODE_BYTES,
    )
    MAX_EXISTING_HOSTS = _get_positive_int_env("CMDB_NODE_MGMT_MAX_EXISTING_HOSTS", 100_000)
    MAX_EXISTING_HOST_BYTES = _get_positive_int_env("CMDB_NODE_MGMT_MAX_EXISTING_HOST_BYTES", 128 * 1024 * 1024)
    EXISTING_HOST_PAGE_SIZE = _get_positive_int_env("CMDB_NODE_MGMT_EXISTING_HOST_PAGE_SIZE", 500)
    SYSTEM_NODE_QUERY = {
        "skip_permission": True,
        "legacy_callsite": "cmdb.node_sync",
    }
    RAW_DATA_FIELDS = RAW_DATA_FIELDS
    RAW_DATA_METRIC_MODEL_IDS = RAW_DATA_METRIC_MODEL_IDS
    RAW_TEXT_LIMITS = RAW_TEXT_LIMITS
    RAW_DEFAULT_TEXT_LIMIT = RAW_DEFAULT_TEXT_LIMIT
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
            "raw_total": 0,
            "raw_host": 0,
            "raw_process": 0,
            "raw_dropped": 0,
            "raw_retained": 0,
            "raw_truncated": False,
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
        return sanitize_node_mgmt_raw_data_item(item)

    @staticmethod
    def _sanitize_raw_text(value: str, *, limit: int) -> str:
        return sanitize_node_mgmt_raw_text(value, limit=limit)

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
        for key in ("raw_total", "raw_host", "raw_process", "raw_dropped", "raw_retained"):
            message[key] = cls._safe_count(summary.get(key))
        message["raw_truncated"] = summary.get("raw_truncated") is True
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
        normalized["relation"] = cls._normalize_detail_bucket(detail.get("relation") or detail.get("association") or detail.get("conflict"))
        normalized["raw_data"] = cls._normalize_detail_bucket(detail.get("raw_data") or detail.get("__raw_data__"))

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
        return any(cls._safe_count((detail.get(key) or {}).get("count")) for key in ("add", "update", "delete", "relation", "raw_data")) or bool(
            detail.get("todo")
        )

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
        try:
            # 固定唯一键是空库并发初始化的仲裁点；内层 savepoint 避免冲突后
            # 污染调用方事务，再回读已经获胜的记录。
            with transaction.atomic():
                task, _ = NodeMgmtSyncConfig.objects.get_or_create(
                    singleton_key="default",
                    defaults={"name": cls.TASK_NAME, "is_builtin": True},
                )
        except IntegrityError:
            # 只有固定 singleton_key 的赢家真实存在时，才能把异常判定为
            # 初始化竞争；否则保留原 IntegrityError，不能用 DoesNotExist 覆盖根因。
            task = NodeMgmtSyncConfig.objects.filter(singleton_key="default").first()
            if task is None:
                raise

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
        for field in ("auto_sync_enabled", "auto_collect_enabled"):
            if field in validated and not isinstance(validated[field], bool):
                raise ValueError(f"{field} 必须是布尔值")
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
        task = None
        old_auto_sync_enabled = False
        old_auto_collect_enabled = False
        for attempt in range(cls.CONFIG_UPDATE_MAX_RETRIES):
            claim_contended = False
            try:
                task_id = cls.get_task().pk
                with transaction.atomic():
                    snapshot = NodeMgmtSyncConfig.objects.select_for_update().get(pk=task_id)
                    claim_contended = cls._has_live_collect_dispatch_claim(snapshot)
                    if claim_contended:
                        updated = 0
                    else:
                        old_auto_sync_enabled = snapshot.auto_sync_enabled
                        old_auto_collect_enabled = snapshot.auto_collect_enabled
                        auto_sync_enabled = data.get("auto_sync_enabled", snapshot.auto_sync_enabled)
                        auto_collect_enabled = data.get("auto_collect_enabled", snapshot.auto_collect_enabled)
                        next_version = snapshot.version + 1
                        updates = {
                            "auto_sync_enabled": auto_sync_enabled,
                            "auto_collect_enabled": auto_collect_enabled,
                            "sync_interval_minutes": data.get("sync_interval_minutes", snapshot.sync_interval_minutes),
                            "collect_interval_minutes": data.get(
                                "collect_interval_minutes",
                                snapshot.collect_interval_minutes,
                            ),
                            "name": cls.TASK_NAME,
                            "is_builtin": True,
                            "version": next_version,
                            "updated_at": now(),
                            "collect_dispatch_claim_token": None,
                            "collect_dispatch_claim_version": None,
                            "collect_dispatch_claimed_at": None,
                        }
                        if auto_collect_enabled and not auto_sync_enabled:
                            updates["node_config_status"] = "waiting_sync"
                        updated = NodeMgmtSyncConfig.objects.filter(pk=task_id, version=snapshot.version).update(**updates)
                if updated and not claim_contended:
                    task = NodeMgmtSyncConfig.objects.get(pk=task_id, version=next_version)
                    break
            except OperationalError:
                if attempt + 1 == cls.CONFIG_UPDATE_MAX_RETRIES:
                    raise NodeMgmtSyncError("CONFIG_UPDATE_CONTENDED") from None
            if attempt + 1 < cls.CONFIG_UPDATE_MAX_RETRIES:
                time.sleep(cls.CONFIG_UPDATE_RETRY_BASE_SECONDS * (2**attempt))
        if task is None:
            raise NodeMgmtSyncError("CONFIG_UPDATE_CONTENDED")

        from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

        switches_changed = old_auto_sync_enabled != task.auto_sync_enabled or old_auto_collect_enabled != task.auto_collect_enabled
        has_delivery_intent = NodeMgmtSyncRegionState.objects.filter(
            config=task,
            node_config_status__in=(
                "delete_pending",
                "delete_in_progress",
                "push_pending",
                "push_in_progress",
            ),
        ).exists()
        NodeMgmtSyncReconciler.reconcile(
            task,
            reconcile_node_configs=switches_changed or has_delivery_intent,
        )

        return NodeMgmtSyncConfig.objects.get(pk=task.pk)

    @classmethod
    def _has_live_collect_dispatch_claim(cls, config, *, at=None):
        if not config.collect_dispatch_claim_token or not config.collect_dispatch_claimed_at:
            return False
        at = at or now()
        return config.collect_dispatch_claimed_at >= at - timedelta(seconds=cls.COLLECT_DISPATCH_CLAIM_TIMEOUT_SECONDS)

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
                "reason_code": "",
                "started_at": None,
                "submitted_at": None,
                "finished_at": None,
                "deadline_at": None,
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
            "reason_code": run.reason_code,
            "started_at": cls._serialize_dt(run.started_at),
            "submitted_at": cls._serialize_dt(run.submitted_at),
            "finished_at": cls._serialize_dt(run.finished_at),
            "deadline_at": cls._serialize_dt(run.deadline_at),
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
    def acquire_run(cls, run_type: str, task: NodeMgmtSyncConfig | None = None) -> NodeMgmtSyncRun:
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
                    deadline_at=current_time + timedelta(minutes=cls.RUN_TIMEOUT_MINUTES),
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
            updates["error_message"] = f"{reason_code or 'RUN_FAILED'}: {type(error).__name__}"[:255]
        guard_lease = status in (
            NodeMgmtSyncRun.STATUS_SUCCESS,
            NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        ) or (status == NodeMgmtSyncRun.STATUS_FAILED and (run.active_scope is not None or run.deadline_at is not None))
        with transaction.atomic():
            lease = NodeMgmtSyncRun.objects.filter(
                pk=run.pk,
                generation=run.generation,
                status__in=cls.ACTIVE_STATUSES,
            )
            if guard_lease:
                lease = lease.filter(
                    active_scope=cls.ACTIVE_SCOPE,
                    deadline_at__gt=current_time,
                )
            updated = lease.update(**updates)

            if updated and status in (
                NodeMgmtSyncRun.STATUS_SUCCESS,
                NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
            ):
                timestamp_field = "last_sync_at" if run.run_type == NodeMgmtSyncRun.RUN_TYPE_SYNC else "last_collect_at"
                NodeMgmtSyncConfig.objects.filter(pk=run.task_id).filter(
                    Q(**{f"{timestamp_field}__isnull": True}) | Q(**{f"{timestamp_field}__lt": current_time})
                ).update(
                    **{
                        timestamp_field: current_time,
                        "updated_at": current_time,
                    }
                )

            expired = 0
            if not updated and guard_lease:
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
        if not updated:
            if expired or (run.status == NodeMgmtSyncRun.STATUS_TIMEOUT and run.reason_code == cls.REASON_TIMEOUT):
                raise NodeMgmtSyncError(cls.REASON_TIMEOUT)
            raise NodeMgmtSyncError("RUN_NOT_ACTIVE")
        return run

    @classmethod
    def heartbeat_run(cls, run: NodeMgmtSyncRun) -> None:
        if run.active_scope is None and run.deadline_at is None:
            # 内部 helper 的无执行上下文调用不参与运行租约；正式入口必有两字段。
            return
        current_time = now()
        updated = (
            NodeMgmtSyncRun.objects.filter(
                pk=run.pk,
                generation=run.generation,
                active_scope=cls.ACTIVE_SCOPE,
                deadline_at__gt=current_time,
            )
            .exclude(status__in=cls.TERMINAL_STATUSES)
            .update(
                heartbeat_at=current_time,
                updated_at=current_time,
            )
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
        if expired or (run.status == NodeMgmtSyncRun.STATUS_TIMEOUT and run.reason_code == cls.REASON_TIMEOUT):
            raise NodeMgmtSyncError(cls.REASON_TIMEOUT)
        raise NodeMgmtSyncError("RUN_NOT_ACTIVE")

    @classmethod
    def recover_stale_runs(cls) -> int:
        current_time = now()
        stale_ids = list(
            NodeMgmtSyncRun.objects.filter(
                active_scope=cls.ACTIVE_SCOPE,
                status__in=cls.ACTIVE_STATUSES,
                deadline_at__lte=current_time,
            ).values_list("id", flat=True)
        )
        recovered = NodeMgmtSyncRun.objects.filter(
            id__in=stale_ids,
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
        for run in NodeMgmtSyncRun.objects.filter(
            id__in=stale_ids,
            run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
            status=NodeMgmtSyncRun.STATUS_TIMEOUT,
            snapshot_schema_version=2,
        ):
            states = list(run.region_states.all())
            if run.expected_region_count != len(states):
                run.expected_region_count = len(states)
                run.save(update_fields=["expected_region_count", "updated_at"])
            for state in states:
                snapshot = getattr(state, "snapshot", None)
                if snapshot is not None and snapshot.capture_status == NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE:
                    continue
                state.status = NodeMgmtSyncRun.STATUS_FAILED
                state.reason_code = cls.REASON_TIMEOUT
                state.error_message = ""
                state.finished_at = current_time
                state.save(update_fields=["status", "reason_code", "error_message", "finished_at", "updated_at"])
                cls._capture_placeholder_snapshot(
                    state,
                    status=NodeMgmtSyncRun.STATUS_FAILED,
                    reason_code=cls.REASON_TIMEOUT,
                )
            cls._finalize_collect_snapshot_run(
                run,
                status=NodeMgmtSyncRun.STATUS_TIMEOUT,
                reason_code=cls.REASON_TIMEOUT,
            )
        return recovered

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
                NodeMgmtSyncRun.objects.filter(pk=run.pk).update(error_message=page_message)
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
    def _cloud_region_name_map(cls, run: NodeMgmtSyncRun | None = None) -> dict[int, str]:
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
            is_valid_nodes = isinstance(nodes, list) and all(isinstance(node, dict) for node in nodes)
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
        encoded_bytes = 2  # JSON 数组的方括号；节点正文使用流式编码，避免整页二次拷贝。
        encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
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
            if len(nodes) + len(page_nodes) > cls.MAX_NODE_COUNT:
                raise NodeMgmtSyncError("NODE_COUNT_LIMIT_EXCEEDED")
            for node in page_nodes:
                if encoded_bytes > 2:
                    encoded_bytes += 1
                for chunk in encoder.iterencode(node):
                    encoded_bytes += len(chunk.encode("utf-8"))
                    if encoded_bytes > cls.MAX_NODE_BYTES:
                        raise NodeMgmtSyncError("NODE_BYTES_LIMIT_EXCEEDED")
            nodes.extend(page_nodes)
            count = cls._safe_count(rows.get("count") if isinstance(rows, dict) else len(page_nodes))
            if not page_nodes or (count > 0 and len(nodes) >= count) or len(page_nodes) < page_size:
                return nodes
        raise NodeMgmtSyncError("NODE_PAGE_LIMIT_EXCEEDED")

    @classmethod
    def _fetch_non_container_nodes(
        cls,
        run: NodeMgmtSyncRun | None = None,
        *,
        source_stats: dict[str, int] | None = None,
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
        if source_stats is not None:
            source_stats["source_total"] = total_nodes
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
                    "cloud_region_name": str(node.get("cloud_region_name") or cloud_region_names.get(cloud_region_id) or ""),
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
        if source_stats is not None:
            source_stats["invalid_node_count"] = skipped_count
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
        cloud_region_name = cls._cloud_region_name_map(run=run).get(int(cloud_region_id), "")
        nodes = cls._fetch_node_mgmt_pages(
            {"cloud_region_id": cloud_region_id, "is_container": True},
            deadline_at=getattr(run, "deadline_at", None),
            run=run,
        )
        if not nodes:
            logger.warning("[NodeMgmtSync] 云区域无可用容器节点作为接入点, cloud_region_id=%d", cloud_region_id)
            return None
        node = max(nodes, key=lambda item: str(item.get("updated_at") or ""))
        logger.debug("[NodeMgmtSync] 选中接入点, cloud_region_id=%d, node_id=%s, node_name=%s", cloud_region_id, node.get("id"), node.get("name"))
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
            "is_interval": bool(getattr(old_task, "is_interval", False)),
        }
        new_snapshot = {
            "instances": cls._normalize_sync_snapshot(getattr(new_task, "instances", [])),
            "access_point": cls._normalize_sync_snapshot(getattr(new_task, "access_point", [])),
            "is_interval": bool(getattr(new_task, "is_interval", False)),
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

        logger.debug(
            "[NodeMgmtSync] 确保区域采集任务存在, cloud_region_id=%d, cloud_region_name=%s, instances_count=%d",
            cloud_region_id,
            cloud_region_name,
            len(instances),
        )
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
            needs_delivery = (
                auto_collect_enabled
                and CollectModelService.should_sync_node_params(task)
                and cls._should_repush_collect_task_node_params(old_task, task)
            )
            if needs_delivery:
                from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

                logger.info("[NodeMgmtSync] 采集任务参数变更, 登记节点参数交付, task_id=%d", task.id)
                NodeMgmtSyncReconciler.mark_region_delivery_pending(
                    cls.get_task(),
                    cloud_region_id=cloud_region_id,
                    collect_task=task,
                )
            return task
        logger.info("[NodeMgmtSync] 创建新采集任务, cloud_region_id=%d, cloud_region_name=%s", cloud_region_id, cloud_region_name)
        if run is not None:
            cls.heartbeat_run(run)
        try:
            with transaction.atomic():
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
        except IntegrityError:
            if not CollectModels.objects.filter(system_code=cls._system_code(cloud_region_id)).exists():
                raise
            return cls._ensure_region_collect_task(
                cloud_region_id=cloud_region_id,
                cloud_region_name=cloud_region_name,
                access_point=access_point,
                team=team,
                instances=instances,
                interval_minutes=interval_minutes,
                run=run,
            )
        if run is not None:
            cls.heartbeat_run(run)
        logger.info("[NodeMgmtSync] 采集任务创建成功, task_id=%d, cloud_region_id=%d", task.id, cloud_region_id)
        if auto_collect_enabled and CollectModelService.should_sync_node_params(task):
            from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

            logger.debug("[NodeMgmtSync] 登记新任务节点参数交付, task_id=%d", task.id)
            NodeMgmtSyncReconciler.mark_region_delivery_pending(
                cls.get_task(),
                cloud_region_id=cloud_region_id,
                collect_task=task,
            )
        return task

    @classmethod
    def _load_existing_host_map(cls, task_id: int, run: NodeMgmtSyncRun | None = None) -> dict[tuple[str, int], dict[str, Any]]:
        inst_list: list[dict[str, Any]] = []
        encoded_size = 0
        page = 1
        page_size = min(cls.EXISTING_HOST_PAGE_SIZE, cls.MAX_EXISTING_HOSTS)
        while True:
            if run is not None:
                cls.heartbeat_run(run)
            rows, total = InstanceManage.search_inst(
                model_id="host",
                page=page,
                page_size=page_size,
            )
            if run is not None:
                cls.heartbeat_run(run)
            if not isinstance(rows, list):
                raise NodeMgmtSyncError("HOST_SCAN_INVALID_RESPONSE")
            total_count = cls._safe_count(total)
            if total_count > cls.MAX_EXISTING_HOSTS:
                logger.error(
                    "[NodeMgmtSync] 主机快照超过资源预算 code=HOST_SCAN_LIMIT_EXCEEDED, count=%d, limit=%d",
                    total_count,
                    cls.MAX_EXISTING_HOSTS,
                )
                raise NodeMgmtSyncError("HOST_SCAN_LIMIT_EXCEEDED")
            for item in rows:
                if len(inst_list) >= cls.MAX_EXISTING_HOSTS:
                    raise NodeMgmtSyncError("HOST_SCAN_LIMIT_EXCEEDED")
                encoded_size += len(
                    json.dumps(
                        item,
                        ensure_ascii=False,
                        default=str,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                if encoded_size > cls.MAX_EXISTING_HOST_BYTES:
                    logger.error(
                        "[NodeMgmtSync] 主机快照超过资源预算 code=HOST_SCAN_BYTES_EXCEEDED, limit=%d",
                        cls.MAX_EXISTING_HOST_BYTES,
                    )
                    raise NodeMgmtSyncError("HOST_SCAN_BYTES_EXCEEDED")
                inst_list.append(item)
            if not rows or (total_count and len(inst_list) >= total_count):
                break
            if len(rows) < page_size:
                break
            if len(inst_list) >= cls.MAX_EXISTING_HOSTS:
                raise NodeMgmtSyncError("HOST_SCAN_LIMIT_EXCEEDED")
            page += 1

        result: dict[tuple[str, int], dict[str, Any]] = {}
        for item in inst_list:
            ip = str(item.get("ip_addr") or "").strip()
            cloud = item.get("cloud") or item.get("cloud_id")
            if not ip or cloud in (None, ""):
                continue
            result[(ip, int(cloud))] = item
        return result

    @classmethod
    def _query_region_host_instances(
        cls,
        cloud_region_id: int,
        region_nodes: list[dict[str, Any]],
        existing_map: dict[tuple[str, int], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if existing_map is None:
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
    def _host_os_type_options(cls, host_attr_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        attr = host_attr_map.get("os_type") or {}
        options = ModelManage.resolve_runtime_enum_options(attr) if attr else []
        return options if isinstance(options, list) else []

    @classmethod
    def _map_host_os_type(
        cls,
        operating_system: Any,
        *,
        host_attr_map: dict[str, dict[str, Any]] | None = None,
        os_type_options: list[dict[str, Any]] | None = None,
    ) -> str:
        raw_value = str(operating_system or "").strip()
        if not raw_value:
            return "other"

        if os_type_options is None:
            host_attr_map = host_attr_map if host_attr_map is not None else cls._host_attr_map()
            os_type_options = cls._host_os_type_options(host_attr_map)

        normalized = raw_value.lower()
        for option in os_type_options:
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
        host_attr_map: dict[str, dict[str, Any]] | None = None,
        os_type_options: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        cloud_region_id = int(node["cloud_region_id"])
        cloud_region_name = node.get("cloud_region_name") or ""
        ip = str(node.get("ip") or node.get("ip_addr") or "").strip()
        inst_name = build_host_inst_name(
            ip=ip,
            cloud_name=cloud_region_name,
            cloud_id=cloud_region_id,
        )
        return {
            "id": node.get("id"),
            "model_id": "host",
            "inst_name": inst_name,
            "ip_addr": ip,
            "organization": cls._normalize_org_ids(node.get("organization_ids") or node.get("organization")),
            "cloud": cloud_region_id,
            "cloud_id": cloud_region_id,
            "cloud_name": cloud_region_name,
            "os_type": cls._map_host_os_type(
                node.get("operating_system") or node.get("os_type"),
                host_attr_map=host_attr_map,
                os_type_options=os_type_options,
            ),
            "collect_task": collect_task_id,
            "node_id": node.get("id"),
            "cmdb_id": node.get("cmdb_id") or "",
            "source": cls.SYSTEM_SOURCE,
            "_status": node.get("_status") or "success",
            "_error": node.get("_error") or "",
        }

    @classmethod
    def _changed_host_attrs(cls, existing: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
        return {field: desired.get(field) for field in cls.HOST_SYNC_UPDATE_FIELDS if field in desired and desired.get(field) != existing.get(field)}

    @classmethod
    def _host_persistence_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        result = {field: payload.get(field) for field in cls.HOST_SYNC_UPDATE_FIELDS if field in payload}
        node_id = normalize_link_id(payload.get("node_id"))
        if node_id:
            result["node_id"] = node_id
        return result

    @classmethod
    def _host_display_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        result = {field: payload.get(field) for field in cls.HOST_SYNC_UPDATE_FIELDS if field in payload}
        if payload.get("_id") is not None:
            result["_id"] = payload["_id"]
        return result

    @staticmethod
    def _host_lookup_key(payload: dict[str, Any]) -> tuple[str, int | None]:
        return host_lookup_key(ip_addr=payload.get("ip_addr"), cloud=payload.get("cloud"))

    @classmethod
    def _hosts_by_node_id(cls, existing_hosts: dict[Any, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for host in existing_hosts.values():
            node_id = normalize_link_id((host or {}).get("node_id"))
            if node_id:
                indexed[node_id] = host
        return indexed

    @classmethod
    def _match_existing_host(
        cls,
        desired: dict[str, Any],
        *,
        existing_hosts: dict[Any, dict[str, Any]],
        by_node_id: dict[str, dict[str, Any]],
    ):
        ip_addr, cloud = cls._host_lookup_key(desired)

        def find_by_node_id(node_id: str):
            return by_node_id.get(node_id)

        def find_by_cmdb_id(cmdb_id: str):
            for host in existing_hosts.values():
                if str(host.get("_id")) == str(cmdb_id):
                    return host
            return None

        def find_by_ip_cloud(ip: str, cloud_id: int):
            tuple_key = (ip, cloud_id)
            if tuple_key in existing_hosts:
                return existing_hosts[tuple_key]
            return existing_hosts.get(ip)

        return resolve_host_identity(
            node_id=desired.get("node_id"),
            cmdb_id=desired.get("cmdb_id"),
            ip=ip_addr,
            cloud=cloud,
            find_by_node_id=find_by_node_id,
            find_by_cmdb_id=find_by_cmdb_id,
            find_by_ip_cloud=find_by_ip_cloud,
        )

    @classmethod
    def _remember_host(
        cls,
        existing_hosts: dict[Any, dict[str, Any]],
        by_node_id: dict[str, dict[str, Any]],
        host: dict[str, Any],
        *,
        ip_addr: str,
        cloud: int | None,
    ) -> None:
        if ip_addr and cloud is not None:
            existing_hosts[(ip_addr, cloud)] = host
        node_id = normalize_link_id(host.get("node_id"))
        if node_id:
            by_node_id[node_id] = host

    @classmethod
    def _ensure_host_node_id_attr(cls, *, operator: str) -> None:
        from apps.cmdb.services.module_ingest import ensure_model_node_id_attr

        try:
            ensure_model_node_id_attr("host", username=operator or "admin")
        except Exception:
            logger.exception("[NodeMgmtSync] ensure host.node_id attr failed")

    @classmethod
    def _backfill_node_cmdb_id(cls, *, node_id: Any, cmdb_id: Any, ip: Any, cloud: Any) -> None:
        node_id_str = normalize_link_id(node_id)
        if not node_id_str or cmdb_id in (None, ""):
            return
        try:
            from apps.node_mgmt.services.module_link import NodeAssociationService

            NodeAssociationService.best_effort_associate_cmdb_host(
                cmdb_id=cmdb_id,
                ip=ip,
                cloud=cloud,
                existing_node_id=node_id_str,
            )
        except Exception:
            logger.exception(
                "[NodeMgmtSync] backfill Node.cmdb_id failed node_id=%s cmdb_id=%s",
                node_id_str,
                cmdb_id,
            )

    @classmethod
    def _recover_host_after_unique_conflict(cls, desired: dict[str, Any]) -> dict[str, Any] | None:
        node_id = normalize_link_id(desired.get("node_id"))
        ip_addr, cloud = cls._host_lookup_key(desired)
        try:
            if node_id:
                found = InstanceManage.query_entity_by_identity("host", {"node_id": node_id})
                if found:
                    return found
            if ip_addr and cloud is not None:
                found = InstanceManage.query_entity_by_identity(
                    "host",
                    {"ip_addr": ip_addr, "cloud": cloud},
                )
                if found:
                    existing_node_id = normalize_link_id(found.get("node_id"))
                    if node_id and existing_node_id and existing_node_id != node_id:
                        return None
                    return found
        except Exception:
            logger.exception("[NodeMgmtSync] 唯一冲突后回查主机失败")
        return None

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
        by_node_id = cls._hosts_by_node_id(existing_hosts)
        ensured_node_id_attr = False

        for desired in desired_hosts:
            if run is not None:
                cls.heartbeat_run(run)
            ip_addr, cloud = cls._host_lookup_key(desired)
            match = cls._match_existing_host(
                desired,
                existing_hosts=existing_hosts,
                by_node_id=by_node_id,
            )
            if match.conflict:
                logger.warning(
                    "[NodeMgmtSync] skip link_conflict incoming_node_id=%s existing_id=%s existing_node_id=%s",
                    desired.get("node_id"),
                    (match.instance or {}).get("_id"),
                    (match.instance or {}).get("node_id"),
                )
                continue
            if match.skipped:
                logger.info("[NodeMgmtSync] skip host missing ip/cloud node_id=%s", desired.get("node_id"))
                continue

            existing = match.instance
            incoming_node_id = normalize_link_id(desired.get("node_id"))
            fill_node_id = node_id_to_write(existing, incoming_node_id)
            if fill_node_id and not ensured_node_id_attr:
                cls._ensure_host_node_id_attr(operator=operator)
                ensured_node_id_attr = True

            if existing is None:
                persistence_payload = cls._host_persistence_payload(desired)
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
                    if is_unique_conflict(exc):
                        recovered = cls._recover_host_after_unique_conflict(desired)
                        if recovered:
                            existing = recovered
                        else:
                            error = {"operation": "add", "error": f"HOST_CREATE_FAILED: {type(exc).__name__}"}
                            result["add_error"] += 1
                            result["errors"].append(error)
                            logger.error("[NodeMgmtSync] 主机创建失败, error_type=%s", type(exc).__name__)
                            continue
                    else:
                        error = {"operation": "add", "error": f"HOST_CREATE_FAILED: {type(exc).__name__}"}
                        result["add_error"] += 1
                        result["errors"].append(error)
                        logger.error("[NodeMgmtSync] 主机创建失败, error_type=%s", type(exc).__name__)
                        continue
                else:
                    persisted = created if isinstance(created, dict) else persistence_payload
                    cls._remember_host(existing_hosts, by_node_id, persisted, ip_addr=ip_addr, cloud=cloud)
                    result["add"] += 1
                    result["add_success"] += 1
                    result["add_data"].append(cls._host_display_payload(persisted))
                    if persisted.get("_id") is not None:
                        result["changed_instance_ids"].append(persisted["_id"])
                    cls._backfill_node_cmdb_id(
                        node_id=incoming_node_id or persisted.get("node_id"),
                        cmdb_id=persisted.get("_id"),
                        ip=ip_addr,
                        cloud=cloud,
                    )
                    continue

            fill_node_id = node_id_to_write(existing, incoming_node_id)
            changes = cls._changed_host_attrs(existing, desired)
            if fill_node_id:
                if not ensured_node_id_attr:
                    cls._ensure_host_node_id_attr(operator=operator)
                    ensured_node_id_attr = True
                changes["node_id"] = fill_node_id
            if not changes:
                cls._backfill_node_cmdb_id(
                    node_id=incoming_node_id or existing.get("node_id"),
                    cmdb_id=existing.get("_id"),
                    ip=ip_addr,
                    cloud=cloud,
                )
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
            cls._remember_host(existing_hosts, by_node_id, persisted, ip_addr=ip_addr, cloud=cloud)
            result["update_success"] += 1
            result["update_data"].append(cls._host_display_payload(persisted))
            if persisted.get("_id") is not None:
                result["changed_instance_ids"].append(persisted["_id"])
            cls._backfill_node_cmdb_id(
                node_id=incoming_node_id or persisted.get("node_id"),
                cmdb_id=persisted.get("_id"),
                ip=ip_addr,
                cloud=cloud,
            )

        return result

    @classmethod
    def _unlink_stale_host_node_ids(
        cls,
        existing_hosts: dict[Any, dict[str, Any]],
        *,
        live_node_ids: set[str],
        operator: str,
        operation_id: str,
        run: NodeMgmtSyncRun | None = None,
    ) -> dict[str, Any]:
        """源侧已消失的 sidecar node_id 是脏指针：只清字段，不删 CMDB 主机。

        IPMI/RPC 等合成 node_id 不在节点管理源里，不得误清。
        """
        result = {"unlink_success": 0, "unlink_error": 0}
        live = {nid for nid in (normalize_link_id(item) for item in live_node_ids) if nid}
        seen: set[Any] = set()
        ensured = False
        for host in list(existing_hosts.values()):
            inst_id = (host or {}).get("_id")
            if inst_id is None or inst_id in seen:
                continue
            seen.add(inst_id)
            nid = normalize_link_id(host.get("node_id"))
            if not nid or nid in live or not is_node_mgmt_sidecar_id(nid):
                continue
            if not ensured:
                cls._ensure_host_node_id_attr(operator=operator)
                ensured = True
            try:
                if run is not None:
                    cls.heartbeat_run(run)
                from apps.cmdb.services.module_ingest import write_system_link_fields

                write_system_link_fields(inst_id, {"node_id": ""})
            except NodeMgmtSyncError:
                raise
            except Exception as exc:
                result["unlink_error"] += 1
                logger.error(
                    "[NodeMgmtSync] 清除悬挂 node_id 失败 inst=%s error_type=%s",
                    inst_id,
                    type(exc).__name__,
                )
                continue
            host["node_id"] = ""
            result["unlink_success"] += 1
        return result

    @classmethod
    def _list_region_collect_tasks(cls, *, active_only: bool = True) -> list[CollectModels]:
        queryset = CollectModels.objects.filter(
            is_system=True,
            system_code__startswith=cls.SYSTEM_TASK_PREFIX,
        )
        if active_only:
            queryset = queryset.filter(is_interval=True)
        return list(queryset.order_by("id"))

    @classmethod
    def _retire_missing_region_collect_tasks(
        cls,
        task_config: NodeMgmtSyncConfig,
        *,
        desired_region_ids: set[int],
    ) -> bool:
        """暂停已从节点源消失的区域，并登记可补偿的节点配置删除。"""
        from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

        desired_codes = {cls._system_code(region_id) for region_id in desired_region_ids}
        retired_any = False
        for collect_task in cls._list_region_collect_tasks(active_only=False):
            system_code = str(collect_task.system_code or "")
            if system_code in desired_codes:
                continue
            raw_region_id = system_code.removeprefix(cls.SYSTEM_TASK_PREFIX)
            if not raw_region_id.isascii() or not raw_region_id.isdecimal():
                continue
            region_id = int(raw_region_id)
            scope_key = NodeMgmtSyncReconciler._node_config_scope(region_id)
            with transaction.atomic():
                collect_task = CollectModels.objects.select_for_update().get(pk=collect_task.pk)
                state = NodeMgmtSyncRegionState.objects.filter(
                    config=task_config,
                    scope_key=scope_key,
                ).first()
                needs_intent = (
                    collect_task.is_interval
                    or state is None
                    or state.node_config_status
                    not in (
                        "delete_pending",
                        "delete_in_progress",
                        "disabled",
                    )
                )
                if collect_task.is_interval:
                    collect_task.is_interval = False
                    collect_task.save(update_fields=["is_interval", "updated_at"])
                if needs_intent:
                    NodeMgmtSyncReconciler.mark_region_delivery_pending(
                        task_config,
                        cloud_region_id=region_id,
                        collect_task=collect_task,
                    )
            retired_any = True
        return retired_any

    @staticmethod
    def _execute_collect_task(task, operator):
        from apps.cmdb.services.collect_service import CollectModelService

        logger.info("[NodeMgmtSync] 执行采集任务, task_id=%d, task_name=%s", task.id, task.name)
        result = CollectModelService.exec_task(
            task,
            operator,
        )
        logger.info("[NodeMgmtSync] 采集任务执行完成, task_id=%d", task.id)
        return result

    @classmethod
    def _claim_collect_dispatch_version(cls, *, run_id, config_id, config_version):
        """按配置版本领取短生命周期持久化下发 claim。"""
        for attempt in range(cls.COLLECT_DISPATCH_MAX_RETRIES):
            try:
                with transaction.atomic():
                    current = NodeMgmtSyncConfig.objects.select_for_update().get(pk=config_id)
                    if current.version != config_version or not current.auto_collect_enabled:
                        return None
                    if cls._has_live_collect_dispatch_claim(current):
                        return None
                    if not NodeMgmtSyncRun.objects.filter(
                        pk=run_id,
                        task_id=config_id,
                        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                        active_scope=cls.ACTIVE_SCOPE,
                        status=NodeMgmtSyncRun.STATUS_RUNNING,
                    ).exists():
                        return None
                    claim_token = uuid.uuid4().hex
                    current.collect_dispatch_claim_token = claim_token
                    current.collect_dispatch_claim_version = config_version
                    current.collect_dispatch_claimed_at = now()
                    current.save(
                        update_fields=(
                            "collect_dispatch_claim_token",
                            "collect_dispatch_claim_version",
                            "collect_dispatch_claimed_at",
                            "updated_at",
                        )
                    )
                    return claim_token
            except OperationalError:
                if attempt + 1 == cls.COLLECT_DISPATCH_MAX_RETRIES:
                    return None
                time.sleep(cls.CONFIG_UPDATE_RETRY_BASE_SECONDS * (2**attempt))
        return None

    @classmethod
    def _release_collect_dispatch_claim(cls, config_id, claim_token):
        for attempt in range(cls.COLLECT_DISPATCH_MAX_RETRIES):
            try:
                return bool(
                    NodeMgmtSyncConfig.objects.filter(
                        pk=config_id,
                        collect_dispatch_claim_token=claim_token,
                    ).update(
                        collect_dispatch_claim_token=None,
                        collect_dispatch_claim_version=None,
                        collect_dispatch_claimed_at=None,
                    )
                )
            except OperationalError:
                if attempt + 1 < cls.COLLECT_DISPATCH_MAX_RETRIES:
                    time.sleep(cls.CONFIG_UPDATE_RETRY_BASE_SECONDS * (2**attempt))
        logger.warning("[NodeMgmtSync] 采集下发 claim 释放失败, config_id=%s", config_id)
        return False

    @classmethod
    def _execute_collect_task_with_claim(
        cls,
        task,
        operator,
        *,
        config_id,
        config_version,
        claim_token,
    ):
        """在真正下发点再次校验 owner fence，阻止过期 worker 恢复执行。"""
        with transaction.atomic():
            current = NodeMgmtSyncConfig.objects.select_for_update().get(pk=config_id)
            if (
                current.version != config_version
                or not current.auto_collect_enabled
                or current.collect_dispatch_claim_token != claim_token
                or current.collect_dispatch_claim_version != config_version
            ):
                return False, None
            task.node_mgmt_config_id = config_id
            task.node_mgmt_config_version = config_version
        # 远程下发不得占用配置行锁；claim 已持久化，配置更新可在 RPC
        # 期间读取它并稳定返回 CONFIG_UPDATE_CONTENDED。
        return True, cls._execute_collect_task(task, operator)

    @classmethod
    def _build_collect_display_payload(cls, source: str) -> dict[str, Any] | None:
        collect_tasks = cls._list_region_collect_tasks()
        if not collect_tasks:
            return None

        detail = cls._empty_display_detail()
        message = cls._empty_display_message()
        collect_statuses: list[int | None] = []
        error_messages: list[str] = []
        collect_times: list[Any] = []

        for collect_task in collect_tasks:
            collect_statuses.append(collect_task.exec_status)
            task_info = collect_task.info
            task_digest = collect_task.collect_digest if isinstance(collect_task.collect_digest, dict) else {}
            task_instances = collect_task.instances if isinstance(collect_task.instances, list) else []

            for key in ("add", "update", "delete", "relation", "raw_data"):
                bucket = task_info.get(key, {"data": [], "count": 0})
                cls._merge_detail_bucket(detail[key], cls._normalize_detail_bucket(bucket))

            info_has_data = any(task_info.get(k, {}).get("count", 0) for k in ("add", "update", "delete", "raw_data"))
            if not info_has_data and task_instances:
                fallback_rows = cls._fallback_collect_raw_data(collect_task)
                if fallback_rows:
                    cls._merge_detail_bucket(detail["raw_data"], {"data": fallback_rows, "count": len(fallback_rows)})

            for key in (
                "all",
                "add",
                "update",
                "delete",
                "association",
                "add_error",
                "add_success",
                "update_error",
                "update_success",
                "delete_error",
                "delete_success",
                "association_error",
                "association_success",
            ):
                message[key] += cls._safe_count(task_digest.get(key))
            if task_digest.get("last_time"):
                collect_times.append(task_digest["last_time"])
            if task_digest.get("message"):
                message["message"] = task_digest["message"]
                if collect_task.exec_status != CollectRunStatusType.SUCCESS:
                    error_messages.append(str(task_digest["message"]))

        latest_collect_time = cls._latest_collect_time(collect_times)
        if latest_collect_time:
            message["last_time"] = latest_collect_time

        if detail["raw_data"]["count"] == 0 and message.get("all"):
            derived_raw_data = []
            for key in ("add", "update", "delete"):
                derived_raw_data.extend(detail[key]["data"])
            detail["raw_data"] = {"data": derived_raw_data, "count": len(derived_raw_data)}

        if message["all"] == 0:
            message["all"] = detail["raw_data"]["count"]

        legacy_raw_rows = detail["raw_data"]["data"]
        message["raw_total"] = len(legacy_raw_rows)
        message["raw_process"] = sum(1 for row in legacy_raw_rows if isinstance(row, dict) and row.get("model_id") == "host_proc_usage")
        message["raw_host"] = message["raw_total"] - message["raw_process"]
        message["raw_retained"] = message["raw_total"]
        message["raw_dropped"] = 0
        message["raw_truncated"] = False

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
            "status": cls._aggregate_collect_status(collect_statuses),
            "started_at": cls._serialize_dt(latest_collect_task.exec_time),
            "finished_at": cls._serialize_dt(latest_collect_task.updated_at),
            "message": message,
            "summary": message,
            "detail": detail,
            "error_message": "; ".join(dict.fromkeys(error_messages)),
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
                "error_message": (task.collect_digest or {}).get("message", "") if isinstance(task.collect_digest, dict) else "",
            },
        }

    @staticmethod
    def _collect_status_to_text(status: int | None) -> str:
        status_map = {
            CollectRunStatusType.NOT_START: "unexecuted",
            CollectRunStatusType.RUNNING: "running",
            CollectRunStatusType.SUCCESS: "success",
            CollectRunStatusType.PARTIAL_SUCCESS: "partial_success",
            CollectRunStatusType.ERROR: "error",
            CollectRunStatusType.TIME_OUT: "timeout",
            CollectRunStatusType.WRITING: "writing",
            CollectRunStatusType.FORCE_STOP: "force_stop",
        }
        return status_map.get(status, "unknown")

    @classmethod
    def _aggregate_collect_status(cls, statuses: list[int | None]) -> str:
        if not statuses:
            return "unknown"
        if all(status == CollectRunStatusType.SUCCESS for status in statuses):
            return NodeMgmtSyncRun.STATUS_SUCCESS
        failed_statuses = {
            CollectRunStatusType.ERROR,
            CollectRunStatusType.TIME_OUT,
            CollectRunStatusType.FORCE_STOP,
        }
        if all(status in failed_statuses for status in statuses):
            return NodeMgmtSyncRun.STATUS_FAILED
        if len(set(statuses)) == 1:
            return cls._collect_status_to_text(statuses[0])
        return NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS

    @staticmethod
    def _latest_collect_time(values: list[Any]) -> str:
        parsed_values = []
        for value in values:
            if not isinstance(value, str) or not value:
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                continue
            parsed_values.append(parsed.astimezone(dt_timezone.utc))
        if not parsed_values:
            return ""
        return max(parsed_values).strftime("%Y-%m-%d %H:%M:%S%z")

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
            "display_schema": "host_collect_v2" if run.snapshot_schema_version == 2 else "host_collect",
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
            latest_complete_run = (
                NodeMgmtSyncRun.objects.filter(
                    task=task,
                    run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                    snapshot_schema_version=2,
                    snapshot_status="complete",
                    status__in=cls.TERMINAL_STATUSES,
                )
                .order_by("-finished_at", "-id")
                .first()
            )
            if latest_complete_run is not None:
                payload = cls._display_payload_from_sync_run(
                    latest_complete_run,
                    cls.DISPLAY_SOURCE_COLLECT,
                )
                payload["task"] = cls.serialize_task(task)
                return payload
            collect_payload = cls._build_collect_display_payload(cls.DISPLAY_SOURCE_COLLECT)
            collect_has_data = bool(collect_payload and cls._has_display_data(collect_payload.get("detail")))
            collect_status = (collect_payload.get("run") or {}).get("status") if collect_payload else None
            if collect_has_data and collect_status != "unexecuted":
                payload = collect_payload
                payload["task"] = cls.serialize_task(task)
                return payload
            latest_collect_run = cls.get_latest_run(NodeMgmtSyncRun.RUN_TYPE_COLLECT, task=task)
            if latest_collect_run and (latest_collect_run.detail_json or latest_collect_run.summary_json):
                payload = cls._display_payload_from_sync_run(latest_collect_run, cls.DISPLAY_SOURCE_COLLECT)
                payload["task"] = cls.serialize_task(task)
                return payload
            latest_sync_run = cls.get_latest_run(NodeMgmtSyncRun.RUN_TYPE_SYNC, task=task)
            if latest_sync_run:
                payload = cls._display_payload_from_sync_run(latest_sync_run, cls.DISPLAY_SOURCE_SYNC_FALLBACK)
                payload["task"] = cls.serialize_task(task)
                return payload
            if collect_has_data:
                payload = collect_payload
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
    def get_snapshot_rows(
        cls,
        *,
        run_id: Any,
        bucket: Any = "raw_data",
        page: Any = 1,
        page_size: Any = 20,
        search: Any = "",
    ) -> dict[str, Any]:
        try:
            parsed_run_id = int(run_id)
            parsed_page = int(page)
            parsed_page_size = int(page_size)
        except (TypeError, ValueError):
            raise ValueError("分页参数无效") from None
        if parsed_run_id <= 0 or parsed_page <= 0 or not 1 <= parsed_page_size <= 100:
            raise ValueError("分页参数无效")
        if bucket != "raw_data":
            raise ValueError("bucket 无效")
        search_text = str(search or "").strip()
        if len(search_text) > 255:
            raise ValueError("搜索条件过长")

        task = cls.get_task()
        current_run = (
            NodeMgmtSyncRun.objects.filter(
                task=task,
                run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                snapshot_schema_version=2,
                snapshot_status="complete",
                status__in=cls.TERMINAL_STATUSES,
            )
            .order_by("-finished_at", "-id")
            .first()
        )
        if current_run is None or current_run.pk != parsed_run_id:
            raise ValueError("run_id 不是当前可展示批次")

        retained_query = NodeMgmtSyncSnapshotRow.objects.filter(
            snapshot__run=current_run,
            bucket=bucket,
            snapshot__detail_retained=True,
        )
        retained_count = retained_query.count()
        matched_query = retained_query
        if search_text:
            matched_query = matched_query.filter(
                Q(inst_name__icontains=search_text)
                | Q(ip_addr__icontains=search_text)
                | Q(cloud_name__icontains=search_text)
                | Q(pid__icontains=search_text)
                | Q(process_name__icontains=search_text)
            )
        matched_retained_count = matched_query.count()
        offset = (parsed_page - 1) * parsed_page_size
        data = list(
            matched_query.order_by("snapshot__cloud_region_id", "snapshot_id", "ordinal").values_list("payload_json", flat=True)[
                offset : offset + parsed_page_size
            ]
        )
        summary = current_run.summary_json if isinstance(current_run.summary_json, dict) else {}
        return {
            "total_count": cls._safe_count(summary.get("raw_total")),
            "retained_count": retained_count,
            "matched_retained_count": matched_retained_count,
            "truncated": summary.get("raw_truncated") is True,
            "page": parsed_page,
            "page_size": parsed_page_size,
            "data": data,
        }

    @classmethod
    def sync_hosts(cls) -> dict[str, Any]:
        if PUSH_LINKAGE_REPLACES_PULL_SYNC:
            logger.info(
                "[NodeMgmtSync] 拉取同步已关闭（推送联动已接管），跳过 sync_hosts reason=%s",
                cls.REASON_PUSH_LINKAGE_REPLACES_PULL,
            )
            task_config = cls.get_task()
            current_time = now()
            run = NodeMgmtSyncRun.objects.create(
                task=task_config,
                run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code=cls.REASON_PUSH_LINKAGE_REPLACES_PULL,
                started_at=current_time,
                finished_at=current_time,
                summary_json={"skipped": True},
                detail_json={"message": "拉取同步已由推送联动替代，已跳过"},
            )
            return cls.serialize_run(run)

        logger.info("[NodeMgmtSync] ========== 开始同步节点管理主机 ==========")
        task_config = cls.get_task()
        logger.info(
            "[NodeMgmtSync] 同步配置: auto_sync_enabled=%s, sync_interval=%d分钟, auto_collect_enabled=%s",
            task_config.auto_sync_enabled,
            task_config.sync_interval_minutes,
            task_config.auto_collect_enabled,
        )
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
        source_stats: dict[str, int] = {}
        nodes = cls._fetch_non_container_nodes(run=run, source_stats=source_stats)
        source_total = source_stats.get("source_total", len(nodes))
        invalid_node_count = source_stats.get("invalid_node_count", max(source_total - len(nodes), 0))
        logger.info("[NodeMgmtSync] 获取节点完成, total_nodes=%d", len(nodes))

        grouped_nodes = cls._group_nodes_by_region(nodes)
        logger.info("[NodeMgmtSync] 节点按云区域分组完成, region_count=%d", len(grouped_nodes))

        detail = cls._empty_display_detail()
        detail["config_version"] = task_config.version
        detail["source_total"] = source_total
        detail["invalid_node_count"] = invalid_node_count
        message = cls._empty_display_message()
        if not grouped_nodes:
            reason_code = cls.REASON_NODE_SOURCE_EMPTY if source_total == 0 else cls.REASON_NO_VALID_NODES
            current_config = cls.get_task()
            cls._retire_missing_region_collect_tasks(current_config, desired_region_ids=set())
            latest_config = cls.get_task()
            cls.finish_run(
                run,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code=reason_code,
                summary_json=message,
                detail_json=detail,
            )
            logger.warning(
                "[NodeMgmtSync] 节点源不可用于同步, reason_code=%s, source_total=%d, invalid_count=%d",
                reason_code,
                source_total,
                invalid_node_count,
            )
            from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

            NodeMgmtSyncReconciler.reconcile(
                latest_config,
                reconcile_node_configs=True,
            )
            return cls.serialize_run(run)

        changed_instance_ids: list[int] = []
        # 模型结构与动态枚举属于本轮同步快照：每轮读取一次，在所有节点间复用；
        # 下一轮完整重试重新读取，避免进程级缓存导致结构陈旧。
        host_attr_map = cls._host_attr_map()
        os_type_options = cls._host_os_type_options(host_attr_map)
        # 每次完整同步读取一次新鲜快照，并在本次 run 的所有区域间复用。
        # _persist_hosts 会把本轮新增/更新写回该映射，区域任务因此能立即引用。
        existing_map = cls._load_existing_host_map(task_id=0, run=run)
        logger.debug("[NodeMgmtSync] 加载已有主机映射, existing_count=%d", len(existing_map))
        live_node_ids = {nid for region_nodes in grouped_nodes.values() for node in region_nodes if (nid := normalize_link_id(node.get("id")))}

        for cloud_region_id, region_nodes in grouped_nodes.items():
            cls.heartbeat_run(run)
            cloud_region_name = str(region_nodes[0].get("cloud_region_name") or cloud_region_id)
            logger.info(
                "[NodeMgmtSync] 处理云区域: cloud_region_id=%d, cloud_region_name=%s, node_count=%d", cloud_region_id, cloud_region_name, len(region_nodes)
            )

            access_point = cls._pick_access_point(cloud_region_id, run=run)
            if access_point:
                logger.debug("[NodeMgmtSync] 云区域接入点: cloud_region_id=%d, access_point_id=%s", cloud_region_id, access_point.get("id"))
            else:
                logger.warning("[NodeMgmtSync] 云区域无接入点: cloud_region_id=%d", cloud_region_id)

            team = cls._normalize_org_ids([org_id for node in region_nodes for org_id in node.get("organization_ids", [])])
            desired_hosts = []
            for node in region_nodes:
                try:
                    cls.heartbeat_run(run)
                    payload = cls._build_host_instance_payload(
                        node=node,
                        collect_task_id=0,
                        host_attr_map=host_attr_map,
                        os_type_options=os_type_options,
                    )
                    detail["raw_data"]["data"].append(cls._host_display_payload(payload))
                    desired_hosts.append(payload)
                except NodeMgmtSyncError:
                    raise
                except Exception as node_exc:
                    message["add_error"] += 1
                    detail["todo"].append({"operation": "add", "error": f"HOST_PAYLOAD_FAILED: {type(node_exc).__name__}"})
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

            logger.info(
                "[NodeMgmtSync] 云区域主机同步完成: cloud_region_id=%d, add=%d, update=%d",
                cloud_region_id,
                persistence["add_success"],
                persistence["update_success"],
            )

            cls.heartbeat_run(run)
            region_instances = cls._query_region_host_instances(
                cloud_region_id,
                region_nodes,
                existing_map=existing_map,
            )
            cls.heartbeat_run(run)
            logger.debug("[NodeMgmtSync] 查询区域主机实例, cloud_region_id=%d, instance_count=%d", cloud_region_id, len(region_instances))

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

        unlink = cls._unlink_stale_host_node_ids(
            existing_map,
            live_node_ids=live_node_ids,
            operator="system",
            operation_id=str(run.generation),
            run=run,
        )
        if unlink["unlink_success"] or unlink["unlink_error"]:
            detail["unlink_stale_node_id"] = unlink
            logger.info(
                "[NodeMgmtSync] 清除悬挂 node_id unlink_success=%d unlink_error=%d",
                unlink["unlink_success"],
                unlink["unlink_error"],
            )

        current_config = cls.get_task()
        retired_regions = cls._retire_missing_region_collect_tasks(
            current_config,
            desired_region_ids=set(grouped_nodes),
        )
        latest_config = cls.get_task()
        has_delivery_intent = NodeMgmtSyncRegionState.objects.filter(
            config=latest_config,
            node_config_status__in=(
                "delete_pending",
                "delete_in_progress",
                "push_pending",
                "push_in_progress",
            ),
        ).exists()

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
                detail["todo"].append({"operation": "relation", "error": f"RELATION_RECONCILE_FAILED: {type(relation_exc).__name__}"})
                logger.error("[NodeMgmtSync] 关联对账调度失败, error_type=%s", type(relation_exc).__name__)

        for key in ("add", "update", "delete", "relation", "raw_data"):
            detail[key]["count"] = len(detail[key]["data"])
        message["all"] = detail["raw_data"]["count"]
        message["delete_success"] = message["delete"]
        message["association"] = detail["relation"]["count"]
        message["association_success"] = message["association"]

        has_errors = any(message.get(key) for key in ("add_error", "update_error", "delete_error", "association_error"))
        final_status = NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS if detail["todo"] or has_errors else NodeMgmtSyncRun.STATUS_SUCCESS
        cls.finish_run(
            run,
            status=final_status,
            summary_json=message,
            detail_json=detail,
        )
        from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler

        NodeMgmtSyncReconciler.reconcile(
            latest_config,
            reconcile_node_configs=latest_config.auto_sync_enabled or retired_regions or has_delivery_intent,
        )
        logger.info("[NodeMgmtSync] ========== 同步完成 ==========")
        logger.info(
            "[NodeMgmtSync] 同步结果: status=%s, all=%d, add=%d, update=%d, delete=%d, todo_count=%d",
            run.status,
            message["all"],
            message["add"],
            message["update"],
            message["delete"],
            len(detail["todo"]),
        )
        return cls.serialize_run(run)

    @classmethod
    def _has_current_successful_sync(cls, task_config: NodeMgmtSyncConfig) -> bool:
        authoritative_run = (
            task_config.runs.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC)
            .filter(
                Q(
                    status__in=(
                        NodeMgmtSyncRun.STATUS_SUCCESS,
                        NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
                    )
                )
                | Q(
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code__in=(
                        cls.REASON_NODE_SOURCE_EMPTY,
                        cls.REASON_NO_VALID_NODES,
                    ),
                )
            )
            .order_by("-created_at", "-pk")
            .first()
        )
        if authoritative_run is None or authoritative_run.status == NodeMgmtSyncRun.STATUS_BLOCKED:
            return False
        detail = authoritative_run.detail_json if isinstance(authoritative_run.detail_json, dict) else {}
        return detail.get("config_version") == task_config.version

    @classmethod
    def _upsert_waiting_sync_run_locked(
        cls,
        task_config: NodeMgmtSyncConfig,
        *,
        operator: str,
        trigger: str,
    ) -> NodeMgmtSyncRun:
        current_time = now()
        detail = {
            "config_version": task_config.version,
            "operator": str(operator)[:128],
            "trigger": trigger if trigger in ("manual", "periodic") else "periodic",
        }
        waiting_runs = list(
            NodeMgmtSyncRun.objects.filter(
                task=task_config,
                run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                status=NodeMgmtSyncRun.STATUS_WAITING_SYNC,
            ).order_by("created_at", "id")
        )
        if waiting_runs:
            waiting_run = waiting_runs[0]
            duplicate_ids = [run.pk for run in waiting_runs[1:]]
            if duplicate_ids:
                NodeMgmtSyncRun.objects.filter(pk__in=duplicate_ids).update(
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="SYNC_REQUIRED",
                    finished_at=current_time,
                    updated_at=current_time,
                )
            NodeMgmtSyncRun.objects.filter(
                pk=waiting_run.pk,
                status=NodeMgmtSyncRun.STATUS_WAITING_SYNC,
            ).update(
                reason_code="SYNC_REQUIRED",
                started_at=current_time,
                detail_json=detail,
                updated_at=current_time,
            )
            waiting_run.refresh_from_db()
            return waiting_run
        return NodeMgmtSyncRun.objects.create(
            task=task_config,
            run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
            status=NodeMgmtSyncRun.STATUS_WAITING_SYNC,
            reason_code="SYNC_REQUIRED",
            started_at=current_time,
            detail_json=detail,
        )

    @classmethod
    def _build_waiting_sync_run(
        cls,
        task_config: NodeMgmtSyncConfig,
        *,
        operator: str = "system",
        trigger: str = "periodic",
    ) -> NodeMgmtSyncRun:
        with transaction.atomic():
            task_config = NodeMgmtSyncConfig.objects.select_for_update().get(pk=task_config.pk)
            if cls._has_current_successful_sync(task_config):
                return cls._build_collect_run(task=task_config)
            return cls._upsert_waiting_sync_run_locked(task_config, operator=operator, trigger=trigger)

    @classmethod
    def _prepare_collect_run(cls, *, operator: str, trigger: str) -> tuple[NodeMgmtSyncConfig, NodeMgmtSyncRun]:
        task_id = cls.get_task().pk
        with transaction.atomic():
            task_config = NodeMgmtSyncConfig.objects.select_for_update().get(pk=task_id)
            if not cls._has_current_successful_sync(task_config):
                run = cls._upsert_waiting_sync_run_locked(task_config, operator=operator, trigger=trigger)
            else:
                run = cls._build_collect_run(task=task_config)
            return task_config, run

    @classmethod
    def execute_collect(cls, operator: str = "system", trigger: str = "periodic") -> NodeMgmtSyncRun:
        task_config, run = cls._prepare_collect_run(operator=operator, trigger=trigger)
        if run.status in (
            NodeMgmtSyncRun.STATUS_WAITING_SYNC,
            NodeMgmtSyncRun.STATUS_BLOCKED,
        ):
            return run

        try:
            cls._do_collect_hosts(run, task_config, operator=operator)
        except Exception as exc:
            cls._mark_run_failed(run, exc)
            logger.error(
                "[NodeMgmtSync] 采集失败, run_id=%s, error_type=%s",
                run.id,
                type(exc).__name__,
            )
            raise
        run.refresh_from_db()
        return run

    @classmethod
    def collect_hosts(cls, operator: str = "system", trigger: str = "periodic") -> dict[str, Any]:
        logger.info("[NodeMgmtSync] ========== 开始采集节点管理主机 ==========")
        task_config = cls.get_task()
        logger.info(
            "[NodeMgmtSync] 采集配置: auto_collect_enabled=%s, collect_interval=%d分钟",
            task_config.auto_collect_enabled,
            task_config.collect_interval_minutes,
        )
        return cls.serialize_run(cls.execute_collect(operator=operator, trigger=trigger))

    @classmethod
    def _region_state_for_collect_task(
        cls,
        *,
        run: NodeMgmtSyncRun,
        task_config: NodeMgmtSyncConfig,
        collect_task: CollectModels,
    ) -> tuple[NodeMgmtSyncRegionState, bool]:
        system_code = collect_task.system_code
        raw_region_id = (
            system_code[len(cls.SYSTEM_TASK_PREFIX) :] if isinstance(system_code, str) and system_code.startswith(cls.SYSTEM_TASK_PREFIX) else ""
        )
        valid_region = bool(raw_region_id and raw_region_id.isascii() and raw_region_id.isdecimal())
        if valid_region:
            cloud_region_id = str(int(raw_region_id))
            scope_suffix = f"region:{cloud_region_id}"
        else:
            cloud_region_id = f"invalid:{collect_task.pk}"
            scope_suffix = f"task:{collect_task.pk}"
        finished_at = None if valid_region else now()
        state, _ = NodeMgmtSyncRegionState.objects.update_or_create(
            scope_key=f"collect-run:{run.pk}:{scope_suffix}",
            defaults={
                "config": task_config,
                "run": run,
                "cloud_region_id": cloud_region_id,
                "config_version": task_config.version,
                "collect_task": collect_task,
                "status": "pending" if valid_region else NodeMgmtSyncRun.STATUS_BLOCKED,
                "reason_code": "" if valid_region else "INVALID_REGION_CODE",
                "error_message": "",
                "child_execution_id": "",
                "submitted_at": None,
                "finished_at": finished_at,
            },
        )
        return state, valid_region

    @staticmethod
    def _collect_response_accepted(response: Any) -> bool:
        try:
            payload = json.loads(response.content)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return response.status_code < 400 and payload.get("result") is True

    @classmethod
    def _region_snapshot_quota(cls, state: NodeMgmtSyncRegionState) -> tuple[int, int]:
        state_ids = list(state.run.region_states.order_by("cloud_region_id", "id").values_list("id", flat=True))
        if not state_ids:
            return 0, 0
        position = state_ids.index(state.pk)
        row_base, row_remainder = divmod(cls.SNAPSHOT_MAX_ROWS, len(state_ids))
        byte_base, byte_remainder = divmod(cls.SNAPSHOT_MAX_BYTES, len(state_ids))
        return (
            row_base + (1 if position < row_remainder else 0),
            byte_base + (1 if position < byte_remainder else 0),
        )

    @classmethod
    def _capture_placeholder_snapshot(
        cls,
        state: NodeMgmtSyncRegionState,
        *,
        status: str,
        reason_code: str,
    ) -> NodeMgmtSyncRegionSnapshot:
        row_quota, byte_quota = cls._region_snapshot_quota(state)
        with transaction.atomic():
            snapshot, created = NodeMgmtSyncRegionSnapshot.objects.select_for_update().get_or_create(
                region_state=state,
                defaults={
                    "run": state.run,
                    "cloud_region_id": state.cloud_region_id,
                    "child_execution_id": state.child_execution_id,
                    "status": status,
                },
            )
            if not created and snapshot.capture_status == NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE:
                return snapshot
            snapshot.rows.all().delete()
            snapshot.run = state.run
            snapshot.cloud_region_id = state.cloud_region_id
            snapshot.child_execution_id = state.child_execution_id
            snapshot.status = status
            snapshot.reason_code = reason_code
            snapshot.capture_status = NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE
            snapshot.capture_token = ""
            snapshot.capture_deadline = None
            snapshot.capture_attempt += 1
            snapshot.row_quota = row_quota
            snapshot.byte_quota = byte_quota
            snapshot.summary_json = {
                "raw_total": 0,
                "raw_host": 0,
                "raw_process": 0,
                "raw_dropped": 0,
                "raw_retained": 0,
                "raw_truncated": False,
            }
            snapshot.detail_retained = True
            snapshot.cleanup_status = NodeMgmtSyncRegionSnapshot.CLEANUP_RETAINED
            snapshot.byte_size = 0
            snapshot.truncated = False
            snapshot.save()
            return snapshot

    @classmethod
    def _mark_collect_region_blocked(cls, state: NodeMgmtSyncRegionState, reason_code: str) -> None:
        state.status = NodeMgmtSyncRun.STATUS_BLOCKED
        state.reason_code = reason_code
        state.error_message = ""
        state.finished_at = now()
        state.save(
            update_fields=[
                "status",
                "reason_code",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        cls._capture_placeholder_snapshot(
            state,
            status=NodeMgmtSyncRun.STATUS_BLOCKED,
            reason_code=reason_code,
        )

    @classmethod
    def _snapshot_row_payloads(
        cls,
        *,
        run: NodeMgmtSyncRun,
        state: NodeMgmtSyncRegionState,
        collect_task: CollectModels,
        row_quota: int,
        byte_quota: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
        task_info = collect_task.info if isinstance(collect_task.format_data, dict) else {}
        raw_bucket = task_info.get("raw_data") if isinstance(task_info, dict) else {}
        source_rows = raw_bucket.get("data", []) if isinstance(raw_bucket, dict) else []
        source_rows = source_rows if isinstance(source_rows, list) else []

        normalized_rows: list[tuple[str, dict[str, Any], str]] = []
        raw_host = 0
        raw_process = 0
        raw_dropped = max(len(source_rows) - cls.SNAPSHOT_INPUT_MAX_ROWS, 0)
        for item in source_rows[: cls.SNAPSHOT_INPUT_MAX_ROWS]:
            if not isinstance(item, dict):
                raw_dropped += 1
                continue
            metric_name = item.get("__name__")
            if metric_name not in cls.RAW_DATA_METRIC_MODEL_IDS:
                raw_dropped += 1
                continue
            payload = cls._sanitize_raw_data_item(item)
            if payload.get("model_id") == "host_proc_usage":
                row_type = "process"
                raw_process += 1
            else:
                row_type = "host"
                raw_host += 1
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            normalized_rows.append((canonical, payload, row_type))

        normalized_rows.sort(key=lambda row: row[0])
        retained: list[dict[str, Any]] = []
        retained_bytes = 0
        occurrences: dict[str, int] = {}
        for canonical, payload, row_type in normalized_rows:
            if len(retained) >= row_quota:
                break
            occurrence = occurrences.get(canonical, 0)
            occurrences[canonical] = occurrence + 1
            row_key = hashlib.sha256(
                (f"{run.generation}|{state.cloud_region_id}|{state.child_execution_id}|" f"raw_data|{canonical}|{occurrence}").encode()
            ).hexdigest()
            row_payload = dict(payload)
            row_payload["_row_key"] = row_key
            encoded_size = len(json.dumps(row_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode())
            if retained_bytes + encoded_size > byte_quota:
                break
            retained.append({"payload": row_payload, "row_type": row_type, "byte_size": encoded_size})
            retained_bytes += encoded_size

        task_digest = collect_task.collect_digest if isinstance(collect_task.collect_digest, dict) else {}
        has_persisted_input_summary = all(key in task_digest for key in ("raw_total", "raw_host", "raw_process", "raw_dropped"))
        if has_persisted_input_summary:
            raw_total = cls._safe_count(task_digest.get("raw_total"))
            raw_host = cls._safe_count(task_digest.get("raw_host"))
            raw_process = cls._safe_count(task_digest.get("raw_process"))
            raw_dropped = cls._safe_count(task_digest.get("raw_dropped"))
        else:
            raw_total = len(source_rows)
        summary = cls._normalize_display_message(task_digest)
        summary.update(
            {
                "raw_total": raw_total,
                "raw_host": raw_host,
                "raw_process": raw_process,
                "raw_dropped": raw_dropped,
                "raw_retained": len(retained),
                "raw_truncated": task_digest.get("raw_input_truncated") is True or len(retained) < raw_host + raw_process,
            }
        )
        return retained, summary, retained_bytes

    @classmethod
    def _capture_terminal_region(
        cls,
        state: NodeMgmtSyncRegionState,
        *,
        status: str,
        reason_code: str,
    ) -> NodeMgmtSyncRegionState:
        current_time = now()
        capture_token = uuid.uuid4().hex
        with transaction.atomic():
            collect_task = CollectModels.objects.select_for_update().get(pk=state.collect_task_id)
            locked_run = NodeMgmtSyncRun.objects.select_for_update().get(pk=state.run_id)
            locked_state = NodeMgmtSyncRegionState.objects.select_for_update().get(pk=state.pk)
            if (
                locked_run.generation != state.run.generation
                or locked_run.status != NodeMgmtSyncRun.STATUS_SUBMITTED
                or locked_run.active_scope != cls.ACTIVE_SCOPE
                or locked_run.deadline_at is None
                or locked_run.deadline_at <= current_time
            ):
                raise NodeMgmtSyncError("RUN_NOT_ACTIVE")
            if locked_state.status != NodeMgmtSyncRun.STATUS_SUBMITTED or str(collect_task.task_id or "") != locked_state.child_execution_id:
                raise NodeMgmtSyncError("COLLECT_EXECUTION_SUPERSEDED")

            row_quota, byte_quota = cls._region_snapshot_quota(locked_state)
            snapshot, created = NodeMgmtSyncRegionSnapshot.objects.get_or_create(
                region_state=locked_state,
                defaults={
                    "run": locked_run,
                    "cloud_region_id": locked_state.cloud_region_id,
                    "child_execution_id": locked_state.child_execution_id,
                    "status": status,
                    "reason_code": reason_code,
                    "capture_status": NodeMgmtSyncRegionSnapshot.CAPTURE_CAPTURING,
                    "capture_token": capture_token,
                    "capture_deadline": min(
                        locked_run.deadline_at,
                        current_time + timedelta(seconds=cls.SNAPSHOT_CAPTURE_LEASE_SECONDS),
                    ),
                    "capture_attempt": 1,
                    "row_quota": row_quota,
                    "byte_quota": byte_quota,
                },
            )
            if not created and snapshot.capture_status == NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE:
                return locked_state
            if (
                not created
                and snapshot.capture_status == NodeMgmtSyncRegionSnapshot.CAPTURE_CAPTURING
                and snapshot.capture_token
                and snapshot.capture_deadline is not None
                and snapshot.capture_deadline > current_time
            ):
                return locked_state
            if not created:
                snapshot.status = status
                snapshot.reason_code = reason_code
                snapshot.capture_status = NodeMgmtSyncRegionSnapshot.CAPTURE_CAPTURING
                snapshot.capture_token = capture_token
                snapshot.capture_deadline = min(
                    locked_run.deadline_at,
                    current_time + timedelta(seconds=cls.SNAPSHOT_CAPTURE_LEASE_SECONDS),
                )
                snapshot.capture_attempt += 1
                snapshot.row_quota = row_quota
                snapshot.byte_quota = byte_quota
                snapshot.save(
                    update_fields=[
                        "status",
                        "reason_code",
                        "capture_status",
                        "capture_token",
                        "capture_deadline",
                        "capture_attempt",
                        "row_quota",
                        "byte_quota",
                        "updated_at",
                    ]
                )

        retained, summary, retained_bytes = cls._snapshot_row_payloads(
            run=locked_run,
            state=locked_state,
            collect_task=collect_task,
            row_quota=row_quota,
            byte_quota=byte_quota,
        )

        with transaction.atomic():
            collect_task = CollectModels.objects.select_for_update().get(pk=state.collect_task_id)
            locked_run = NodeMgmtSyncRun.objects.select_for_update().get(pk=state.run_id)
            locked_state = NodeMgmtSyncRegionState.objects.select_for_update().get(pk=state.pk)
            snapshot = NodeMgmtSyncRegionSnapshot.objects.select_for_update().get(region_state=locked_state)
            committed_at = now()
            if (
                snapshot.capture_status != NodeMgmtSyncRegionSnapshot.CAPTURE_CAPTURING
                or snapshot.capture_token != capture_token
                or locked_run.generation != state.run.generation
                or locked_run.status != NodeMgmtSyncRun.STATUS_SUBMITTED
                or locked_run.active_scope != cls.ACTIVE_SCOPE
                or locked_run.deadline_at is None
                or locked_run.deadline_at <= committed_at
                or locked_state.status != NodeMgmtSyncRun.STATUS_SUBMITTED
                or str(collect_task.task_id or "") != locked_state.child_execution_id
            ):
                return locked_state

            NodeMgmtSyncSnapshotRow.objects.filter(snapshot=snapshot).delete()
            rows = []
            for ordinal, retained_row in enumerate(retained):
                payload = retained_row["payload"]
                rows.append(
                    NodeMgmtSyncSnapshotRow(
                        snapshot=snapshot,
                        bucket="raw_data",
                        ordinal=ordinal,
                        row_type=retained_row["row_type"],
                        row_key=payload["_row_key"],
                        inst_name=str(payload.get("inst_name") or ""),
                        ip_addr=str(payload.get("ip_addr") or payload.get("ip") or ""),
                        cloud_name=str(payload.get("cloud_name") or ""),
                        pid=str(payload.get("pid") or ""),
                        process_name=str(payload.get("name") or ""),
                        payload_json=payload,
                        byte_size=retained_row["byte_size"],
                    )
                )
            NodeMgmtSyncSnapshotRow.objects.bulk_create(rows, batch_size=cls.SNAPSHOT_BULK_BATCH_SIZE)
            snapshot.status = status
            snapshot.reason_code = reason_code
            snapshot.capture_status = NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE
            snapshot.capture_token = ""
            snapshot.capture_deadline = None
            snapshot.summary_json = summary
            snapshot.byte_size = retained_bytes
            snapshot.truncated = summary["raw_truncated"]
            snapshot.save(
                update_fields=[
                    "status",
                    "reason_code",
                    "capture_status",
                    "capture_token",
                    "capture_deadline",
                    "summary_json",
                    "byte_size",
                    "truncated",
                    "updated_at",
                ]
            )
            locked_state.status = status
            locked_state.reason_code = reason_code
            locked_state.error_message = ""
            locked_state.finished_at = current_time
            locked_state.save(update_fields=["status", "reason_code", "error_message", "finished_at", "updated_at"])
            return locked_state

    @classmethod
    def _cas_collect_region_terminal(
        cls,
        state: NodeMgmtSyncRegionState,
        *,
        status: str,
        reason_code: str,
    ) -> NodeMgmtSyncRegionState:
        current_time = now()
        updated = NodeMgmtSyncRegionState.objects.filter(
            pk=state.pk,
            run_id=state.run_id,
            status=NodeMgmtSyncRun.STATUS_SUBMITTED,
            child_execution_id=state.child_execution_id,
        ).update(
            status=status,
            reason_code=reason_code,
            error_message="",
            finished_at=current_time,
            updated_at=current_time,
        )
        state.refresh_from_db()
        if updated:
            return state
        if state.status == status and state.reason_code == reason_code:
            return state
        raise NodeMgmtSyncError("COLLECT_REGION_STATE_CONFLICT")

    @classmethod
    def _aggregate_collect_terminal_status(cls, run: NodeMgmtSyncRun) -> str | None:
        statuses = list(run.region_states.values_list("status", flat=True))
        if not statuses or NodeMgmtSyncRun.STATUS_SUBMITTED in statuses:
            return None
        if all(status == NodeMgmtSyncRun.STATUS_SUCCESS for status in statuses):
            return NodeMgmtSyncRun.STATUS_SUCCESS
        if all(status in (NodeMgmtSyncRun.STATUS_FAILED, NodeMgmtSyncRun.STATUS_BLOCKED) for status in statuses):
            return NodeMgmtSyncRun.STATUS_FAILED
        return NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS

    @classmethod
    def _collect_snapshot_reason_code(
        cls,
        *,
        status: str,
        snapshots: list[NodeMgmtSyncRegionSnapshot],
        explicit: str = "",
    ) -> str:
        if explicit:
            return explicit
        if status == NodeMgmtSyncRun.STATUS_SUCCESS:
            return ""
        codes = [snapshot.reason_code for snapshot in snapshots if snapshot.reason_code]
        unique = list(dict.fromkeys(codes))
        if len(unique) == 1:
            return unique[0]
        return ""

    @classmethod
    def _finalize_collect_snapshot_run(
        cls,
        run: NodeMgmtSyncRun,
        *,
        status: str,
        reason_code: str = "",
    ) -> NodeMgmtSyncRun:
        snapshots = list(run.region_snapshots.order_by("cloud_region_id", "id"))
        if len(snapshots) != run.expected_region_count or any(
            snapshot.capture_status != NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE for snapshot in snapshots
        ):
            raise NodeMgmtSyncError("COLLECT_SNAPSHOT_INCOMPLETE")
        reason_code = cls._collect_snapshot_reason_code(
            status=status,
            snapshots=snapshots,
            explicit=reason_code,
        )

        message = cls._empty_display_message()
        times = []
        errors = []
        for snapshot in snapshots:
            summary = snapshot.summary_json if isinstance(snapshot.summary_json, dict) else {}
            for key in (
                "all",
                "add",
                "update",
                "delete",
                "association",
                "add_error",
                "add_success",
                "update_error",
                "update_success",
                "delete_error",
                "delete_success",
                "association_error",
                "association_success",
                "raw_total",
                "raw_host",
                "raw_process",
                "raw_dropped",
                "raw_retained",
            ):
                message[key] += cls._safe_count(summary.get(key))
            message["raw_truncated"] = message["raw_truncated"] or summary.get("raw_truncated") is True
            if summary.get("last_time"):
                times.append(summary["last_time"])
            if snapshot.reason_code:
                errors.append(f"{snapshot.cloud_region_id}:{snapshot.reason_code}")
        latest_time = cls._latest_collect_time(times)
        if latest_time:
            message["last_time"] = latest_time
        message["message"] = "; ".join(errors)

        raw_rows = list(
            NodeMgmtSyncSnapshotRow.objects.filter(snapshot__run=run, bucket="raw_data")
            .order_by("snapshot__cloud_region_id", "snapshot_id", "ordinal")
            .values_list("payload_json", flat=True)[:20]
        )
        detail = cls._empty_display_detail()
        detail["raw_data"] = {
            "data": raw_rows,
            "count": message["raw_retained"],
            "total_count": message["raw_total"],
            "retained_count": message["raw_retained"],
            "truncated": message["raw_truncated"],
        }
        run.refresh_from_db()
        if run.status == status and run.active_scope is None:
            NodeMgmtSyncRun.objects.filter(pk=run.pk, generation=run.generation).update(
                reason_code=reason_code,
                summary_json=message,
                detail_json=detail,
                updated_at=now(),
            )
        else:
            cls.finish_run(
                run,
                status=status,
                reason_code=reason_code,
                summary_json=message,
                detail_json=detail,
            )
        updated = NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            status=status,
        ).update(
            snapshot_schema_version=2,
            snapshot_status="complete",
            error_message=message["message"][:255],
            updated_at=now(),
        )
        if not updated:
            raise NodeMgmtSyncError("COLLECT_SNAPSHOT_FINALIZE_CONFLICT")
        run.refresh_from_db()
        try:
            cls.cleanup_old_snapshot_rows(task_id=run.task_id, keep_run_id=run.pk)
        except Exception:
            logger.exception(
                "[NodeMgmtSync] 旧快照明细清理失败 code=SNAPSHOT_CLEANUP_FAILED, run_id=%s",
                run.pk,
            )
        return run

    @classmethod
    def cleanup_old_snapshot_rows(
        cls,
        *,
        task_id: int,
        keep_run_id: int,
        batch_size: int = 100,
    ) -> dict[str, int]:
        latest_complete_run = (
            NodeMgmtSyncRun.objects.filter(
                task_id=task_id,
                run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                snapshot_schema_version=2,
                snapshot_status="complete",
            )
            .order_by("-finished_at", "-id")
            .first()
        )
        if latest_complete_run is None:
            return {"pending": 0, "cleaned": 0, "failed": 0}
        keep_run_id = latest_complete_run.pk
        snapshot_ids = list(
            NodeMgmtSyncRegionSnapshot.objects.filter(
                run__task_id=task_id,
                run__run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                run__snapshot_schema_version=2,
                run__snapshot_status="complete",
                detail_retained=True,
            )
            .exclude(run_id=keep_run_id)
            .order_by("run__finished_at", "run_id", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        if not snapshot_ids:
            return {"pending": 0, "cleaned": 0, "failed": 0}
        NodeMgmtSyncRegionSnapshot.objects.filter(pk__in=snapshot_ids).update(
            cleanup_status=NodeMgmtSyncRegionSnapshot.CLEANUP_PENDING,
            updated_at=now(),
        )
        try:
            with transaction.atomic():
                NodeMgmtSyncSnapshotRow.objects.filter(snapshot_id__in=snapshot_ids).delete()
                cleaned = NodeMgmtSyncRegionSnapshot.objects.filter(pk__in=snapshot_ids).update(
                    detail_retained=False,
                    cleanup_status=NodeMgmtSyncRegionSnapshot.CLEANUP_SUMMARY_ONLY,
                    updated_at=now(),
                )
        except Exception:
            NodeMgmtSyncRegionSnapshot.objects.filter(pk__in=snapshot_ids).update(
                cleanup_status=NodeMgmtSyncRegionSnapshot.CLEANUP_FAILED,
                updated_at=now(),
            )
            raise
        return {"pending": len(snapshot_ids), "cleaned": cleaned, "failed": 0}

    @classmethod
    def recover_snapshot_cleanup(cls, task_id: int) -> dict[str, int]:
        keep_run = (
            NodeMgmtSyncRun.objects.filter(
                task_id=task_id,
                run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                snapshot_schema_version=2,
                snapshot_status="complete",
            )
            .order_by("-finished_at", "-id")
            .first()
        )
        if keep_run is None:
            return {"pending": 0, "cleaned": 0, "failed": 0}
        try:
            return cls.cleanup_old_snapshot_rows(task_id=task_id, keep_run_id=keep_run.pk)
        except Exception:
            logger.exception(
                "[NodeMgmtSync] 快照清理补偿失败 code=SNAPSHOT_CLEANUP_RECOVERY_FAILED",
            )
            return {"pending": 0, "cleaned": 0, "failed": 1}

    @classmethod
    def _mark_collect_run_submitted(
        cls,
        run: NodeMgmtSyncRun,
        *,
        summary_json: dict[str, Any],
        detail_json: dict[str, Any],
    ) -> None:
        submitted_at = now()
        updated = NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            active_scope=cls.ACTIVE_SCOPE,
            status=NodeMgmtSyncRun.STATUS_RUNNING,
            deadline_at__gt=submitted_at,
        ).update(
            status=NodeMgmtSyncRun.STATUS_SUBMITTED,
            submitted_at=submitted_at,
            summary_json=summary_json,
            detail_json=detail_json,
            updated_at=submitted_at,
        )
        if not updated:
            cls.heartbeat_run(run)
            raise NodeMgmtSyncError("RUN_NOT_ACTIVE")
        run.refresh_from_db()

    @classmethod
    def _do_collect_hosts(
        cls,
        run: NodeMgmtSyncRun,
        task_config: NodeMgmtSyncConfig,
        *,
        operator: str = "system",
    ) -> NodeMgmtSyncRun:
        detail = {
            "config_version": task_config.version,
            "todo": [],
            "executed": [],
            "failed": [],
        }
        message = cls._empty_display_message()
        accepted_count = 0

        collect_tasks = cls._list_region_collect_tasks()
        logger.info("[NodeMgmtSync] 获取区域采集任务列表, task_count=%d", len(collect_tasks))
        task_states = [
            (
                collect_task,
                *cls._region_state_for_collect_task(
                    run=run,
                    task_config=task_config,
                    collect_task=collect_task,
                ),
            )
            for collect_task in collect_tasks
        ]
        NodeMgmtSyncRun.objects.filter(
            pk=run.pk,
            generation=run.generation,
            status=NodeMgmtSyncRun.STATUS_RUNNING,
        ).update(
            snapshot_schema_version=2,
            snapshot_status="capturing",
            expected_region_count=len(task_states),
            updated_at=now(),
        )
        run.refresh_from_db()
        if not NodeMgmtSyncConfig.objects.filter(pk=task_config.pk, version=task_config.version).exists():
            detail["failed"].append({"reason_code": "SYNC_REQUIRED", "message": "配置版本已变化"})
            for _, state, _ in task_states:
                cls._mark_collect_region_blocked(state, "SYNC_REQUIRED")
            cls._finalize_collect_snapshot_run(
                run,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code="COLLECT_SUBMISSION_BLOCKED",
            )
            return run

        for collect_task, state, valid_region in task_states:
            cls.heartbeat_run(run)
            message["all"] += 1
            if not valid_region:
                cls._capture_placeholder_snapshot(
                    state,
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="INVALID_REGION_CODE",
                )
                detail["failed"].append({"task_id": collect_task.id, "reason_code": "INVALID_REGION_CODE"})
                continue
            access_point = collect_task.access_point if isinstance(collect_task.access_point, list) else []
            logger.debug(
                "[NodeMgmtSync] 检查采集任务: task_id=%d, task_name=%s, has_access_point=%s",
                collect_task.id,
                collect_task.name,
                bool(access_point),
            )
            if not access_point:
                logger.warning(
                    "[NodeMgmtSync] 采集任务无接入点, 跳过执行: task_id=%d, task_name=%s",
                    collect_task.id,
                    collect_task.name,
                )
                detail["todo"].append(
                    {
                        "task_id": collect_task.id,
                        "message": f"TODO: task {collect_task.id} has no available container node access point",
                    }
                )
                cls._mark_collect_region_blocked(state, "NO_ACCESS_POINT")
                continue
            logger.info(
                "[NodeMgmtSync] 开始执行采集任务: task_id=%d, task_name=%s",
                collect_task.id,
                collect_task.name,
            )
            if not NodeMgmtSyncConfig.objects.filter(pk=task_config.pk, version=task_config.version).exists():
                detail["failed"].append(
                    {
                        "task_id": collect_task.id,
                        "reason_code": "SYNC_REQUIRED",
                    }
                )
                cls._mark_collect_region_blocked(state, "SYNC_REQUIRED")
                break
            try:
                cls.heartbeat_run(run)
                claim_token = cls._claim_collect_dispatch_version(
                    run_id=run.pk,
                    config_id=task_config.pk,
                    config_version=task_config.version,
                )
                if not claim_token:
                    detail["failed"].append(
                        {
                            "task_id": collect_task.id,
                            "reason_code": "SYNC_REQUIRED",
                        }
                    )
                    cls._mark_collect_region_blocked(state, "SYNC_REQUIRED")
                    break
                try:
                    fenced, response = cls._execute_collect_task_with_claim(
                        collect_task,
                        operator,
                        config_id=task_config.pk,
                        config_version=task_config.version,
                        claim_token=claim_token,
                    )
                finally:
                    cls._release_collect_dispatch_claim(task_config.pk, claim_token)
                if not fenced:
                    detail["failed"].append(
                        {
                            "task_id": collect_task.id,
                            "reason_code": "SYNC_REQUIRED",
                        }
                    )
                    cls._mark_collect_region_blocked(state, "SYNC_REQUIRED")
                    break
                submitted_execution_id = str(collect_task.task_id or "")
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
                cls._mark_collect_region_blocked(state, "COLLECT_SUBMIT_FAILED")
                continue
            if not cls._collect_response_accepted(response):
                detail["failed"].append(
                    {
                        "task_id": collect_task.id,
                        "reason_code": "COLLECT_ALREADY_RUNNING",
                    }
                )
                cls._mark_collect_region_blocked(state, "COLLECT_ALREADY_RUNNING")
                continue
            if not submitted_execution_id:
                detail["failed"].append(
                    {
                        "task_id": collect_task.id,
                        "reason_code": "COLLECT_EXECUTION_ID_MISSING",
                    }
                )
                cls._mark_collect_region_blocked(state, "COLLECT_EXECUTION_ID_MISSING")
                continue

            state.status = NodeMgmtSyncRun.STATUS_SUBMITTED
            state.reason_code = ""
            state.error_message = ""
            state.child_execution_id = submitted_execution_id
            state.submitted_at = now()
            state.finished_at = None
            state.save(
                update_fields=[
                    "status",
                    "reason_code",
                    "error_message",
                    "child_execution_id",
                    "submitted_at",
                    "finished_at",
                    "updated_at",
                ]
            )
            accepted_count += 1
            detail["executed"].append(
                {
                    "task_id": collect_task.id,
                    "name": collect_task.name,
                    "child_execution_id": state.child_execution_id,
                }
            )
            logger.info("[NodeMgmtSync] 采集任务已提交: task_id=%d", collect_task.id)

        for pending_state in run.region_states.filter(status="pending"):
            cls._mark_collect_region_blocked(pending_state, "SYNC_REQUIRED")

        if accepted_count:
            cls._mark_collect_run_submitted(run, summary_json=message, detail_json=detail)
            return run

        blocked_reason_codes = list(run.region_states.exclude(reason_code="").values_list("reason_code", flat=True))
        if blocked_reason_codes and all(reason == "NO_ACCESS_POINT" for reason in blocked_reason_codes):
            reason_code = "NO_ACCESS_POINT"
        elif blocked_reason_codes and all(reason == "COLLECT_ALREADY_RUNNING" for reason in blocked_reason_codes):
            reason_code = "COLLECT_ALREADY_RUNNING"
        else:
            reason_code = "COLLECT_SUBMISSION_BLOCKED"
        if run.expected_region_count == run.region_snapshots.filter(capture_status=NodeMgmtSyncRegionSnapshot.CAPTURE_COMPLETE).count():
            cls._finalize_collect_snapshot_run(
                run,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code=reason_code,
            )
        else:
            cls.finish_run(
                run,
                status=NodeMgmtSyncRun.STATUS_BLOCKED,
                reason_code=reason_code,
                summary_json=message,
                detail_json=detail,
            )
        return run

    @classmethod
    def refresh_collect_run(cls, run_id: int) -> NodeMgmtSyncRun:
        run = NodeMgmtSyncRun.objects.get(pk=run_id, run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT)
        if run.status != NodeMgmtSyncRun.STATUS_SUBMITTED:
            return run

        try:
            cls.heartbeat_run(run)
        except NodeMgmtSyncError as error:
            if str(error) != "RUN_NOT_ACTIVE":
                raise
            run.refresh_from_db()
            expected_status = cls._aggregate_collect_terminal_status(run)
            if expected_status is not None and run.status == expected_status:
                return run
            raise
        terminal_states = []
        for state in run.region_states.select_related("collect_task").all():
            if state.status != NodeMgmtSyncRun.STATUS_SUBMITTED:
                terminal_states.append(state.status)
                continue
            collect_task = state.collect_task
            if collect_task is None:
                cls._capture_placeholder_snapshot(
                    state,
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="COLLECT_TASK_MISSING",
                )
                state = cls._cas_collect_region_terminal(
                    state,
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="COLLECT_TASK_MISSING",
                )
                terminal_states.append(state.status)
                continue
            collect_task.refresh_from_db(fields=("task_id", "exec_status"))
            if str(collect_task.task_id or "") != state.child_execution_id:
                cls._capture_placeholder_snapshot(
                    state,
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="COLLECT_EXECUTION_SUPERSEDED",
                )
                state = cls._cas_collect_region_terminal(
                    state,
                    status=NodeMgmtSyncRun.STATUS_BLOCKED,
                    reason_code="COLLECT_EXECUTION_SUPERSEDED",
                )
                terminal_states.append(state.status)
                continue

            status_map = {
                CollectRunStatusType.SUCCESS: NodeMgmtSyncRun.STATUS_SUCCESS,
                CollectRunStatusType.PARTIAL_SUCCESS: NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
                CollectRunStatusType.ERROR: NodeMgmtSyncRun.STATUS_FAILED,
                CollectRunStatusType.TIME_OUT: NodeMgmtSyncRun.STATUS_FAILED,
                CollectRunStatusType.FORCE_STOP: NodeMgmtSyncRun.STATUS_FAILED,
            }
            child_status = status_map.get(collect_task.exec_status)
            if child_status is None:
                continue
            state = cls._capture_terminal_region(
                state,
                status=child_status,
                reason_code=("" if child_status == NodeMgmtSyncRun.STATUS_SUCCESS else "COLLECT_CHILD_FAILED"),
            )
            terminal_states.append(state.status)

        if run.region_states.filter(status=NodeMgmtSyncRun.STATUS_SUBMITTED).exists():
            run.refresh_from_db()
            return run

        final_status = cls._aggregate_collect_terminal_status(run)
        if final_status is None:
            run.refresh_from_db()
            return run
        try:
            cls._finalize_collect_snapshot_run(run, status=final_status)
        except NodeMgmtSyncError as error:
            if str(error) != "RUN_NOT_ACTIVE":
                raise
            run.refresh_from_db()
            if run.status != final_status:
                raise
        return run

    @classmethod
    def refresh_submitted_collect_runs(cls) -> int:
        run_ids = list(
            NodeMgmtSyncRun.objects.filter(
                run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
                status=NodeMgmtSyncRun.STATUS_SUBMITTED,
                active_scope=cls.ACTIVE_SCOPE,
            ).values_list("id", flat=True)
        )
        for run_id in run_ids:
            try:
                cls.refresh_collect_run(run_id)
            except Exception as error:
                logger.error(
                    "[NodeMgmtSync] 采集运行刷新失败 code=COLLECT_REFRESH_FAILED, run_id=%s, error_type=%s",
                    run_id,
                    type(error).__name__,
                )
        return len(run_ids)

    @classmethod
    def trigger_sync(cls) -> dict[str, Any]:
        data = cls.sync_hosts()
        return data

    @classmethod
    def trigger_collect(cls, operator: str = "system", trigger: str = "periodic") -> dict[str, Any]:
        return cls.collect_hosts(operator=operator, trigger=trigger)
