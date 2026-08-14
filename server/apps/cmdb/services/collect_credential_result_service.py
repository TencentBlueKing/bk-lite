import hashlib

from django.utils import timezone

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_hit_state_service import CollectHitStateService
from apps.core.logger import cmdb_logger as logger


class CollectCredentialResultService:
    EVENT_VERSION = "2"
    MODERN_STATUSES = frozenset({"success", "failed", "unreachable", "deferred"})
    CREDENTIAL_FAILURE_ERROR_CODES = frozenset(
        {
            "auth_failed",
            "authentication_failed",
            "capability_denied",
            "snmp_error_status",
            "snmp_authorization_failed",
            "unauthorized",
        }
    )

    @classmethod
    def _normalize_outcome(cls, data: dict):
        event_version = data.get("event_version")
        if event_version is not None and str(event_version) != cls.EVENT_VERSION:
            return None, f"unsupported event_version: {event_version}"

        if event_version is not None and "status" not in data:
            return None, f"status is required for event_version: {event_version}"

        if event_version is not None:
            identity_error = cls._validate_v2_identity(data)
            if identity_error:
                return None, identity_error

        if "status" in data:
            status = str(data.get("status") or "").strip().lower()
            if status not in cls.MODERN_STATUSES:
                return None, f"unsupported status: {status or '<empty>'}"

            success = status == "success"
            if "success" in data and bool(data.get("success")) != success:
                return None, "status conflicts with success"

            error_code = str(data.get("error_code") or "").strip()
            if success and error_code:
                return None, "status conflicts with error_code"
            if (
                status in {"deferred", "unreachable"}
                and error_code in cls.CREDENTIAL_FAILURE_ERROR_CODES
            ):
                return None, "status conflicts with error_code"

            failure_kind = (
                "credential"
                if status == "failed"
                and error_code in cls.CREDENTIAL_FAILURE_ERROR_CODES
                else "task"
            )
            if success:
                failure_kind = ""
                if data.get("failure_kind") or data.get("error_message"):
                    return None, "success conflicts with failure fields"
            elif (
                "failure_kind" in data
                and (data.get("failure_kind") or "task") != failure_kind
            ):
                return None, "error_code conflicts with failure_kind"

            return {
                "success": success,
                "failure_kind": failure_kind,
                "error_message": str(data.get("error_message") or error_code),
            }, ""

        if "success" not in data:
            return None, "status or success is required"

        return {
            "success": bool(data.get("success")),
            "failure_kind": data.get("failure_kind") or "task",
            "error_message": data.get("error_message") or "",
        }, ""

    @classmethod
    def _validate_v2_identity(cls, data: dict) -> str:
        required = (
            "collect_task_id",
            "event_id",
            "event_index",
            "finished_at",
            "plugin_ref",
            "producer_instance",
            "result_id",
            "run_attempt_id",
            "run_id",
        )
        missing = [key for key in required if data.get(key) in (None, "")]
        if missing:
            return "v2 identity fields are required: " + ", ".join(missing)
        if data.get("producer") != "stargazer":
            return "unsupported producer"
        if str(data.get("scope_id") or "") != str(data.get("collect_task_id")):
            return "scope_id conflicts with collect_task_id"
        try:
            fence = int(data.get("fence"))
            event_index = int(data.get("event_index"))
        except (TypeError, ValueError):
            return "fence and event_index must be integers"
        if fence <= 0 or event_index < 0:
            return "fence must be positive and event_index must be non-negative"
        result_identity = "\0".join(
            (
                str(data.get("run_id")),
                str(data.get("plugin_ref")),
                str(data.get("host")),
                str(fence),
                str(data.get("run_attempt_id")),
            )
        )
        expected_result_id = hashlib.sha256(result_identity.encode("utf-8")).hexdigest()
        if str(data.get("result_id")) != expected_result_id:
            return "result_id conflicts with run identity"
        event_identity = "\0".join(
            (
                expected_result_id,
                str(event_index),
                str(data.get("credential_id") or ""),
                str(data.get("status") or ""),
                str(data.get("error_code") or ""),
            )
        )
        expected_event_id = hashlib.sha256(event_identity.encode("utf-8")).hexdigest()
        if str(data.get("event_id")) != expected_event_id:
            return "event_id conflicts with event identity"
        return ""

    @staticmethod
    def process_result(data: dict, parse_datetime=None):
        """处理 Stargazer 单 host 单凭据执行结果并回写 CollectTaskCredentialHit。"""
        if not isinstance(data, dict):
            return {"result": False, "message": "event must be an object"}
        task_id = data.get("collect_task_id") or data.get("task_id")
        if not task_id:
            logger.warning("[CollectCredentialResult] 回调缺少 collect_task_id，已忽略")
            return {"result": False, "message": "collect_task_id is required"}

        host = str(data.get("host") or "").strip()
        credential_id = str(data.get("credential_id") or "").strip()
        if not host or not credential_id:
            logger.warning(
                "[CollectCredentialResult] 回调缺少 host 或 credential_id，已忽略 task_id=%s, host=%s, credential_id=%s",
                task_id,
                host,
                credential_id,
            )
            return {"result": False, "message": "host and credential_id are required"}

        object_key = f"host:{host}"
        raw_snapshot = data.get("snapshot") or {}
        if not isinstance(raw_snapshot, dict):
            return {"result": False, "message": "snapshot must be an object"}
        snapshot = dict(raw_snapshot)
        snapshot.setdefault("host", host)
        try:
            event_at = (
                parse_datetime(data.get("observed_at") or data.get("finished_at"))
                if parse_datetime
                else None
            )
        except (TypeError, ValueError, OverflowError):
            return {"result": False, "message": "event time is invalid"}
        event_at = event_at or timezone.now()
        outcome, error = CollectCredentialResultService._normalize_outcome(data)
        if error:
            logger.warning(
                "[CollectCredentialResult] 回调事件契约无效，已忽略 task_id=%s, host=%s, credential_id=%s, error=%s",
                task_id,
                host,
                credential_id,
                error,
            )
            return {"result": False, "message": error}
        try:
            task = CollectModels.objects.filter(pk=task_id).only("id").first()
        except (TypeError, ValueError, OverflowError):
            task = None
        if task is None:
            return {"result": False, "message": "collect_task_id does not exist"}

        if outcome["success"]:
            logger.info(
                "[CollectCredentialResult] 凭据采集成功回写 task_id=%s, object_key=%s, credential_id=%s",
                task_id,
                object_key,
                credential_id,
            )
            CollectHitStateService.mark_success(
                task_id,
                object_key,
                credential_id,
                snapshot,
                event_at,
                event_id=data.get("event_id") or "",
                result_id=data.get("result_id") or "",
                event_index=data.get("event_index", -1),
            )
        else:
            logger.warning(
                "[CollectCredentialResult] 凭据采集失败回写 task_id=%s, object_key=%s, credential_id=%s, " "failure_kind=%s, error=%s",
                task_id,
                object_key,
                credential_id,
                outcome["failure_kind"],
                outcome["error_message"][:500],
            )
            CollectHitStateService.mark_failure(
                task_id,
                object_key,
                credential_id,
                snapshot,
                outcome["failure_kind"],
                outcome["error_message"],
                event_at,
                event_id=data.get("event_id") or "",
                result_id=data.get("result_id") or "",
                event_index=data.get("event_index", -1),
            )

        return {"result": True, "task_id": task_id, "object_key": object_key, "credential_id": credential_id}

    @staticmethod
    def process_batch(data: dict, parse_datetime=None):
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            return CollectCredentialResultService.process_result(data or {}, parse_datetime=parse_datetime)

        processed = 0
        failures = []
        for item in events:
            result = CollectCredentialResultService.process_result(item or {}, parse_datetime=parse_datetime)
            if result.get("result"):
                processed += 1
            else:
                failures.append(result)

        if failures:
            logger.warning(
                "[CollectCredentialResult] 批量回写存在失败事件 processed=%s, failed=%s",
                processed,
                len(failures),
            )
        else:
            logger.info("[CollectCredentialResult] 批量回写完成 processed=%s", processed)

        return {
            "result": not failures,
            "processed": processed,
            "failed": len(failures),
            "next_since": data.get("next_since") or "",
            "errors": failures,
        }
