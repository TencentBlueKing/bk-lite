from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.utils.timezone import now

from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_hit_state_service import CollectHitStateService
from apps.cmdb.services.collect_target_service import CanonicalCollectTarget, CollectTargetService
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.core.logger import cmdb_logger as logger


@dataclass
class DispatchAttemptResult:
    """单次凭据尝试的归一化结果。"""

    object_key: str
    credential_id: str
    success: bool
    failure_kind: str
    error_message: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


class CollectDispatchService:
    """负责目标分组、凭据选择、复用现有采集链路并聚合结果。"""

    SUPPORTED_TASK_TYPES = {
        CollectPluginTypes.HOST,
        CollectPluginTypes.DB,
        CollectPluginTypes.MIDDLEWARE,
        CollectPluginTypes.CONFIG_FILE,
        CollectPluginTypes.SNMP,
        CollectPluginTypes.PROTOCOL,
    }

    CREDENTIAL_ERROR_KEYWORDS = (
        "auth",
        "password",
        "credential",
        "login",
        "denied",
        "unauthorized",
        "community",
        "privkey",
        "authkey",
        "access denied",
    )

    @classmethod
    def should_dispatch(cls, task) -> bool:
        """仅在首期支持任务且凭据池大于 1 时启用多凭据派发。"""
        pool = CollectCredentialPoolService.normalize_pool(cls._resolve_task_credentials(task))
        return len(pool) > 1 and task.task_type in cls.SUPPORTED_TASK_TYPES

    @classmethod
    def execute_task(cls, task) -> tuple[dict[str, Any], dict[str, Any]]:
        """执行多凭据派发并返回兼容 sync_collect_task 的输出。"""
        credential_pool = CollectCredentialPoolService.normalize_pool(cls._resolve_task_credentials(task))
        targets = CollectTargetService.build_targets(task)
        states = CollectHitStateService.list_states(task.id)
        target_map = {CollectTargetService.build_object_key(target): target for target in targets}
        pending_object_keys = list(target_map.keys())
        attempts: list[DispatchAttemptResult] = []

        while pending_object_keys:
            pending_targets = [target_map[object_key] for object_key in pending_object_keys if object_key in target_map]
            plan = cls.plan_dispatch(task, pending_targets, credential_pool, states)
            if not plan:
                break

            next_pending = []
            for credential_id, credential_targets in plan.items():
                credential = next(item for item in credential_pool if item.get("credential_id") == credential_id)
                if task.is_job:
                    batch_attempts = cls.run_job_batch(task, credential, credential_targets)
                else:
                    batch_attempts = cls.run_protocol_batch(task, credential, credential_targets)

                current_time = now()
                for attempt in batch_attempts:
                    attempts.append(attempt)
                    target = target_map[attempt.object_key]
                    snapshot = CollectTargetService.build_target_snapshot(target)
                    logger.info(
                        "[CollectDispatch] attempt result task_id=%s object_key=%s credential_id=%s success=%s failure_kind=%s",
                        task.id,
                        attempt.object_key,
                        attempt.credential_id,
                        attempt.success,
                        attempt.failure_kind,
                    )
                    if attempt.success:
                        CollectHitStateService.mark_success(
                            task.id,
                            attempt.object_key,
                            attempt.credential_id,
                            snapshot,
                            current_time,
                        )
                        continue

                    CollectHitStateService.mark_failure(
                        task.id,
                        attempt.object_key,
                        attempt.credential_id,
                        snapshot,
                        attempt.failure_kind,
                        attempt.error_message,
                        current_time,
                    )
                    if attempt.failure_kind == "credential":
                        next_pending.append(attempt.object_key)

                states = CollectHitStateService.list_states(task.id)

            pending_object_keys = list(dict.fromkeys(next_pending))

        return cls.merge_attempt_results(task, attempts)

    @classmethod
    def plan_dispatch(cls, task, targets, pool, states) -> dict[str, list[CanonicalCollectTarget]]:
        """按 credential_id 聚合本轮可尝试的目标列表。"""
        plan: dict[str, list[CanonicalCollectTarget]] = {}
        current_time = now()
        for target in targets:
            object_key = CollectTargetService.build_object_key(target)
            success_credential = cls._find_success_credential(object_key, pool, states)
            if success_credential:
                plan.setdefault(success_credential, []).append(target)
                continue

            for credential in pool:
                credential_id = credential.get("credential_id")
                state = states.get((object_key, credential_id))
                if state and not CollectHitStateService.is_retryable(state, current_time):
                    continue
                plan.setdefault(credential_id, []).append(target)
                break
        return plan

    @classmethod
    def run_job_batch(cls, task, credential, targets) -> list[DispatchAttemptResult]:
        """逐目标复用现有 JOB 采集链路执行单凭据批次。"""
        return [cls._run_single_target(task, credential, target, JobCollect) for target in targets]

    @classmethod
    def run_protocol_batch(cls, task, credential, targets) -> list[DispatchAttemptResult]:
        """逐目标复用现有 SNMP / PROTOCOL 采集链路执行单凭据批次。"""
        return [cls._run_single_target(task, credential, target, ProtocolCollect) for target in targets]

    @classmethod
    def merge_attempt_results(cls, task, attempts) -> tuple[dict[str, Any], dict[str, Any]]:
        """合并最终成功结果，保持 sync_collect_task 的消费口径。"""
        if task.task_type == CollectPluginTypes.CONFIG_FILE:
            success_attempts = [attempt for attempt in attempts if attempt.success]
            if success_attempts:
                return ConfigFileService.build_pending_result(task)

        final_attempts: dict[str, DispatchAttemptResult] = {}
        for attempt in attempts:
            final_attempts[attempt.object_key] = attempt

        collect_data: dict[str, Any] = {}
        format_data: dict[str, Any] = {"add": [], "update": [], "delete": [], "association": []}
        raw_data = []
        total = 0

        for attempt in final_attempts.values():
            if not attempt.success:
                continue
            payload = attempt.raw_payload or {}
            collect_data = cls._deep_merge_dict(collect_data, payload.get("collect_data") or {})
            payload_format = payload.get("format_data") or {}
            for key in ("add", "update", "delete", "association"):
                format_data[key].extend(payload_format.get(key, []))
            raw_data.extend(payload_format.get("__raw_data__", []))
            total += int(payload_format.get("all") or 0)

        if raw_data:
            format_data["__raw_data__"] = raw_data
        if total:
            format_data["all"] = total
        return collect_data, format_data

    @classmethod
    def _run_single_target(cls, task, credential, target, collect_cls) -> DispatchAttemptResult:
        object_key = CollectTargetService.build_object_key(target)
        credential_id = credential.get("credential_id")
        task_override = cls._build_task_override(task, credential, target)
        try:
            collect_data, format_data = collect_cls(task=task_override).main()
        except Exception as err:  # noqa: BLE001 - 采集异常转派发结果
            error_message = str(err)
            return DispatchAttemptResult(
                object_key=object_key,
                credential_id=credential_id,
                success=False,
                failure_kind=cls._classify_failure_kind(error_message),
                error_message=error_message,
            )

        success, error_message = cls._classify_payload_success(task, collect_data, format_data)
        return DispatchAttemptResult(
            object_key=object_key,
            credential_id=credential_id,
            success=success,
            failure_kind="" if success else cls._classify_failure_kind(error_message),
            error_message=error_message,
            raw_payload={"collect_data": collect_data, "format_data": format_data},
        )

    @classmethod
    def _build_task_override(cls, task, credential, target):
        task_override = copy.copy(task)
        task_override.credential = copy.deepcopy(credential)
        task_override.instances = [] if not target.instance_id else [copy.deepcopy(target.snapshot)]
        task_override.ip_range = "" if target.instance_id else target.host
        return task_override

    @classmethod
    def _classify_payload_success(cls, task, collect_data, format_data) -> tuple[bool, str]:
        if task.task_type == CollectPluginTypes.CONFIG_FILE:
            config_state = (collect_data or {}).get("config_file") or {}
            if config_state.get("status") == "pending":
                return True, ""

        for key in ("add", "update", "delete", "association"):
            rows = format_data.get(key, []) if isinstance(format_data, dict) else []
            if any(row.get("_status") != "failed" for row in rows if isinstance(row, dict)):
                return True, ""

        if (format_data or {}).get("__raw_data__"):
            return True, ""

        error_message = cls._extract_error_message(format_data)
        return False, error_message

    @classmethod
    def _extract_error_message(cls, format_data) -> str:
        if not isinstance(format_data, dict):
            return ""
        for key in ("add", "update", "delete", "association"):
            for row in format_data.get(key, []):
                if isinstance(row, dict) and row.get("_error"):
                    return str(row["_error"])
        return ""

    @classmethod
    def _classify_failure_kind(cls, error_message: str) -> str:
        message = (error_message or "").lower()
        if any(keyword in message for keyword in cls.CREDENTIAL_ERROR_KEYWORDS):
            return "credential"
        return "task"

    @staticmethod
    def _find_success_credential(object_key, pool, states) -> str | None:
        for credential in pool:
            credential_id = credential.get("credential_id")
            state = states.get((object_key, credential_id))
            if state and state.status == "success":
                return credential_id
        return None

    @staticmethod
    def _resolve_task_credentials(task):
        return getattr(task, "decrypt_credentials", None) or getattr(task, "credential", None)

    @classmethod
    def _deep_merge_dict(cls, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(left)
        for key, value in (right or {}).items():
            if key not in merged:
                merged[key] = copy.deepcopy(value)
                continue
            existing = merged[key]
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = cls._deep_merge_dict(existing, value)
            elif isinstance(existing, list) and isinstance(value, list):
                merged[key] = existing + value
            else:
                merged[key] = copy.deepcopy(value)
        return merged