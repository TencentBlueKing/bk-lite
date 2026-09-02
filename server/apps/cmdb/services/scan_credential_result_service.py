import hashlib

from django.db import transaction

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit
from apps.core.logger import cmdb_logger as logger

_STATUS_MAP = {
    "success": ScanHit.STATUS_SUCCESS,
    "failed": ScanHit.STATUS_FAILED,
    "unreachable": ScanHit.STATUS_UNREACHABLE,
}
_EMPTY_CREDENTIAL_IDS = frozenset({"", "-", "null", "none", "nil"})
_EVENT_VERSION = "2"
_MODERN_STATUSES = frozenset({"success", "failed", "unreachable", "deferred"})
_CREDENTIAL_FAILURE_ERROR_CODES = frozenset(
    {
        "auth_failed",
        "authentication_failed",
        "capability_denied",
        "snmp_error_status",
        "snmp_authorization_failed",
        "unauthorized",
    }
)


def _validate_v2_identity(data: dict) -> str:
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


def _normalize_scan_outcome(data: dict):
    event_version = data.get("event_version")
    if event_version is not None and str(event_version) != _EVENT_VERSION:
        return None, f"unsupported event_version: {event_version}"
    if event_version is not None and "status" not in data:
        return None, f"status is required for event_version: {event_version}"
    if event_version is not None:
        identity_error = _validate_v2_identity(data)
        if identity_error:
            return None, identity_error
    if "status" not in data:
        if "success" not in data:
            return None, "status or success is required"
        return {
            "success": bool(data.get("success")),
            "failure_kind": data.get("failure_kind") or "task",
            "error_message": data.get("error_message") or "",
        }, ""

    status = str(data.get("status") or "").strip().lower()
    if status not in _MODERN_STATUSES:
        return None, f"unsupported status: {status or '<empty>'}"
    success = status == "success"
    if "success" in data and bool(data.get("success")) != success:
        return None, "status conflicts with success"
    error_code = str(data.get("error_code") or "").strip()
    if success and error_code:
        return None, "status conflicts with error_code"
    if status in {"deferred", "unreachable"} and error_code in _CREDENTIAL_FAILURE_ERROR_CODES:
        return None, "status conflicts with error_code"
    failure_kind = "credential" if status == "failed" and error_code in _CREDENTIAL_FAILURE_ERROR_CODES else "task"
    if success:
        failure_kind = ""
        if data.get("failure_kind") or data.get("error_message"):
            return None, "success conflicts with failure fields"
    elif "failure_kind" in data and (data.get("failure_kind") or "task") != failure_kind:
        return None, "error_code conflicts with failure_kind"
    return {
        "success": success,
        "failure_kind": failure_kind,
        "error_message": str(data.get("error_message") or error_code),
    }, ""


class ScanCredentialResultService:
    @classmethod
    def process_batch(cls, data: dict, parse_datetime=None):
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            return cls.process_result(data or {}, parse_datetime=parse_datetime)

        processed = 0
        failures = []
        for item in events:
            result = cls.process_result(item or {}, parse_datetime=parse_datetime)
            if result.get("result"):
                processed += 1
            else:
                failures.append(result)
        return {
            "result": not failures,
            "processed": processed,
            "failed": len(failures),
            "next_since": data.get("next_since") or "",
            "errors": failures,
        }

    @classmethod
    def process_result(cls, data: dict, parse_datetime=None):
        if not isinstance(data, dict):
            return {"result": False, "message": "event must be an object"}

        task_id = data.get("collect_task_id") or data.get("task_id")
        if not task_id:
            return {"result": False, "message": "collect_task_id is required"}

        host = str(data.get("host") or "").strip()
        credential_id = str(data.get("credential_id") or "").strip()
        if credential_id.lower() in _EMPTY_CREDENTIAL_IDS:
            credential_id = ""

        raw_status = str(data.get("status") or "").strip().lower()
        if not raw_status:
            raw_status = "success" if data.get("success") else "failed"

        if not host:
            return {"result": False, "message": "host is required"}

        # success 必须带凭据；failed / unreachable / credentials_exhausted 等可无凭据，只计进度。
        wants_success = raw_status == "success" or bool(data.get("success"))
        if wants_success and not credential_id:
            return {"result": False, "message": "host and credential_id are required"}

        try:
            family_run = ScanFamilyRun.objects.select_related("execution").filter(pk=task_id).first()
        except (TypeError, ValueError, OverflowError):
            family_run = None
        if family_run is None:
            return {"result": False, "message": "collect_task_id does not exist"}

        outcome, error = _normalize_scan_outcome(data)
        if error:
            if wants_success:
                return {"result": False, "message": error}
            # 失败类事件身份不完整时仍计进度，避免大网段卡在墙钟。
            logger.info(
                "[ScanCredentialResult] 失败事件契约不完整，仅计进度 task_id=%s host=%s error=%s",
                task_id,
                host,
                error,
            )
            outcome = {
                "success": False,
                "failure_kind": "task",
                "error_message": str(data.get("error_code") or data.get("error_message") or error),
            }
        if outcome is None:
            outcome = {
                "success": False,
                "failure_kind": "task",
                "error_message": str(data.get("error_code") or data.get("error_message") or ""),
            }

        hit_status = _STATUS_MAP.get(raw_status, ScanHit.STATUS_FAILED)
        if outcome.get("success"):
            hit_status = ScanHit.STATUS_SUCCESS
        else:
            # credentials_exhausted 等非现代 status 一律当失败，不写清单。
            hit_status = ScanHit.STATUS_UNREACHABLE if raw_status == "unreachable" else ScanHit.STATUS_FAILED

        snapshot = data.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot = dict(snapshot)
        snapshot.setdefault("host", host)

        port = cls._parse_port(data.get("port", snapshot.get("port")))
        soid = str(snapshot.get("sysobjectid") or snapshot.get("sysObjectID") or data.get("sysobjectid") or "")

        hit_id = None
        with transaction.atomic():
            family_run = ScanFamilyRun.objects.select_for_update().select_related("execution").get(pk=family_run.pk)
            progress_hosts = list(family_run.progress_hosts or [])
            if host not in progress_hosts:
                progress_hosts.append(host)
                family_run.progress_hosts = progress_hosts
                family_run.received_count = len(progress_hosts)
                family_run.save(update_fields=["progress_hosts", "received_count", "updated_at"])
                execution = family_run.execution
                execution.received_count = sum(ScanFamilyRun.objects.filter(execution=execution).values_list("received_count", flat=True))
                execution.save(update_fields=["received_count", "updated_at"])
            else:
                execution = family_run.execution

            # 大网段×多凭据场景下失败/不可达不进清单，只计入进度。
            if hit_status == ScanHit.STATUS_SUCCESS and credential_id:
                hit, _created = ScanHit.objects.update_or_create(
                    family_run=family_run,
                    host=host,
                    port=port,
                    credential_id=credential_id,
                    defaults={
                        "execution": family_run.execution,
                        "protocol": family_run.model_id,
                        "status": ScanHit.STATUS_SUCCESS,
                        "soid": soid,
                        "error_code": "",
                        "snapshot": snapshot,
                    },
                )
                hit_id = hit.id

            should_finalize = (
                execution.target_count > 0 and execution.received_count >= execution.target_count and execution.status == ScanExecution.STATUS_RUNNING
            )

        if should_finalize:
            cls._kick_finalize(execution)
        return {
            "result": True,
            "task_id": family_run.id,
            "object_key": f"host:{host}",
            "credential_id": credential_id,
            "hit_id": hit_id,
            "listed": hit_id is not None,
        }

    @staticmethod
    def _parse_port(value):
        try:
            port = int(value)
        except (TypeError, ValueError):
            return 0
        return port if port > 0 else 0

    @staticmethod
    def _kick_finalize(execution):
        from apps.cmdb.tasks.celery_tasks import finalize_scan_execution

        logger.info(
            "[ScanCredentialResult] 回传已齐 execution=%s received=%s target=%s",
            execution.id,
            execution.received_count,
            execution.target_count,
        )
        finalize_scan_execution.delay(execution.id, execution.claim_token)
