import hashlib

from django.db import transaction

from apps.cmdb.models.scan_model import (
    SCAN_DATABASE_TYPES,
    ScanExecution,
    ScanFamilyRun,
    ScanFamilyRunProgress,
    ScanHit,
    scan_driver_type_for_model,
)
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
_DISCOVERY_STAGES = frozenset({"port", "process", "collect"})
_SCAN_DONE_STAGE = "done"
_STAGE_CONFIDENCE = {
    "port": ScanHit.CONFIDENCE_LOW,
    "process": ScanHit.CONFIDENCE_MEDIUM,
    "collect": ScanHit.CONFIDENCE_HIGH,
}
_STAGE_EVIDENCE = {
    "port": "port",
    "process": "process",
    "collect": "collect",
}
_CONFIDENCE_RANK = {
    ScanHit.CONFIDENCE_LOW: 1,
    ScanHit.CONFIDENCE_MEDIUM: 2,
    ScanHit.CONFIDENCE_HIGH: 3,
}


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


def _merge_confidence(current: str, incoming: str) -> str:
    current_rank = _CONFIDENCE_RANK.get(str(current or ""), 0)
    incoming_rank = _CONFIDENCE_RANK.get(str(incoming or ""), 0)
    if incoming_rank > current_rank:
        return incoming
    return current or incoming or ScanHit.CONFIDENCE_LOW


def _merge_evidence(current, token: str) -> list:
    items = [str(item) for item in (current or []) if str(item or "").strip()]
    marker = str(token or "").strip()
    if marker and marker not in items:
        items.append(marker)
    return items


def _resolve_family_run(task_id, *, stage: str, target_type: str):
    family_run = ScanFamilyRun.objects.select_related("execution").filter(pk=task_id).first()
    if not stage:
        return family_run, ""
    execution = ScanExecution.objects.filter(pk=task_id).first()
    if execution is None and family_run is not None:
        execution = family_run.execution
    if execution is None:
        return None, "collect_task_id does not exist"
    model_id = target_type
    if not model_id and family_run is not None and family_run.execution_id == execution.id:
        model_id = family_run.model_id
    if not model_id:
        return None, "target_type is required"
    family_run, _created = ScanFamilyRun.objects.get_or_create(
        execution=execution,
        model_id=model_id,
        driver_type=scan_driver_type_for_model(model_id),
        batch_index=0,
        defaults={
            "target_count": execution.target_count,
            "admit_status": ScanFamilyRun.ADMIT_ACCEPTED,
        },
    )
    return family_run, ""


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

        stage = str(data.get("stage") or "").strip().lower()
        if stage == _SCAN_DONE_STAGE:
            return cls._mark_scan_done(task_id)
        return cls._process_hit_result(data, task_id, stage, parse_datetime=parse_datetime)

    @classmethod
    def _process_hit_result(cls, data: dict, task_id, stage, parse_datetime=None):
        host = str(data.get("host") or "").strip()
        credential_id = str(data.get("credential_id") or "").strip()
        if credential_id.lower() in _EMPTY_CREDENTIAL_IDS:
            credential_id = ""

        raw_status = str(data.get("status") or "").strip().lower()
        if not raw_status:
            raw_status = "success" if data.get("success") else "failed"
        target_type = str(data.get("target_type") or "").strip()

        if not host:
            return {"result": False, "message": "host is required"}

        # 凭据采集 success 必须带凭据；port/process/collect 发现事件允许空凭据落清单。
        wants_success = raw_status == "success" or bool(data.get("success"))
        if wants_success and not credential_id and stage not in _DISCOVERY_STAGES:
            return {"result": False, "message": "host and credential_id are required"}

        try:
            family_run, resolve_error = _resolve_family_run(task_id, stage=stage, target_type=target_type)
        except (TypeError, ValueError, OverflowError):
            family_run, resolve_error = None, "collect_task_id does not exist"
        if resolve_error:
            return {"result": False, "message": resolve_error}
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
            _progress, created = ScanFamilyRunProgress.objects.get_or_create(family_run=family_run, host=host)
            execution = family_run.execution
            if created:
                family_run.received_count += 1
                family_run.save(update_fields=["received_count", "updated_at"])
                execution.received_count = (
                    ScanFamilyRunProgress.objects.filter(family_run__execution=execution).values("host").distinct().count()
                )
                execution.save(update_fields=["received_count", "updated_at"])

            # 大网段×多凭据场景下失败/不可达默认不进清单；三库鉴权失败例外写入一条空凭据占位。
            # 发现阶段 success 允许空凭据；collect 失败不得覆盖或删除已有发现行。
            if hit_status == ScanHit.STATUS_SUCCESS and (credential_id or stage in _DISCOVERY_STAGES):
                if credential_id:
                    ScanHit.objects.filter(
                        family_run=family_run,
                        host=host,
                        port=port,
                        credential_id="",
                        status=ScanHit.STATUS_FAILED,
                    ).delete()
                hit_id = cls._upsert_success_hit(
                    family_run=family_run,
                    host=host,
                    port=port,
                    credential_id=credential_id,
                    soid=soid,
                    snapshot=snapshot,
                    target_type=target_type,
                    stage=stage,
                )
            elif (
                hit_status == ScanHit.STATUS_FAILED
                and family_run.model_id in SCAN_DATABASE_TYPES
                and str(data.get("error_code") or "").strip() in _CREDENTIAL_FAILURE_ERROR_CODES
            ):
                existing = ScanHit.objects.filter(
                    family_run=family_run,
                    host=host,
                    port=port,
                    credential_id="",
                ).first()
                if existing is not None and existing.status == ScanHit.STATUS_SUCCESS:
                    hit_id = existing.id
                elif stage != "collect":
                    hit, _created = ScanHit.objects.update_or_create(
                        family_run=family_run,
                        host=host,
                        port=port,
                        credential_id="",
                        defaults={
                            "execution": family_run.execution,
                            "protocol": family_run.model_id,
                            "status": ScanHit.STATUS_FAILED,
                            "soid": soid,
                            "error_code": str(data.get("error_code") or "").strip(),
                            "snapshot": snapshot,
                        },
                    )
                    hit_id = hit.id
                elif existing is not None:
                    hit_id = existing.id

            should_finalize = execution.status == ScanExecution.STATUS_RUNNING and cls._pipeline_done(execution)

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
    def _upsert_success_hit(*, family_run, host, port, credential_id, soid, snapshot, target_type, stage):
        if stage in _DISCOVERY_STAGES:
            hit = ScanHit.objects.filter(family_run=family_run, host=host, port=port).order_by("id").first()
            if hit is None and stage == "process" and not port:
                hit = ScanHit.objects.filter(family_run=family_run, host=host).order_by("id").first()
        else:
            hit = ScanHit.objects.filter(
                family_run=family_run,
                host=host,
                port=port,
                credential_id=credential_id,
            ).first()
        incoming_confidence = _STAGE_CONFIDENCE.get(stage, "")
        incoming_evidence = _STAGE_EVIDENCE.get(stage, "")
        model_id = target_type or family_run.model_id
        if hit is None:
            hit = ScanHit.objects.create(
                execution=family_run.execution,
                family_run=family_run,
                protocol=family_run.model_id,
                host=host,
                port=port,
                credential_id=credential_id,
                status=ScanHit.STATUS_SUCCESS,
                soid=soid,
                cmdb_model_id=model_id,
                error_code="",
                snapshot=snapshot,
                confidence=incoming_confidence or ScanHit.CONFIDENCE_LOW,
                evidence=_merge_evidence([], incoming_evidence),
            )
            return hit.id
        merged_snapshot = dict(hit.snapshot or {})
        merged_snapshot.update(snapshot or {})
        hit.status = ScanHit.STATUS_SUCCESS
        hit.soid = soid or hit.soid
        hit.error_code = ""
        hit.snapshot = merged_snapshot
        if credential_id and not hit.credential_id:
            hit.credential_id = credential_id
        if model_id and not hit.cmdb_model_id:
            hit.cmdb_model_id = model_id
        if incoming_confidence:
            hit.confidence = _merge_confidence(hit.confidence, incoming_confidence)
        if incoming_evidence:
            hit.evidence = _merge_evidence(hit.evidence, incoming_evidence)
        hit.save(
            update_fields=[
                "status",
                "soid",
                "error_code",
                "snapshot",
                "cmdb_model_id",
                "credential_id",
                "confidence",
                "evidence",
                "updated_at",
            ]
        )
        return hit.id

    @staticmethod
    def _parse_port(value):
        try:
            port = int(value)
        except (TypeError, ValueError):
            return 0
        return port if port > 0 else 0

    @classmethod
    def _mark_scan_done(cls, task_id):
        try:
            execution = ScanExecution.objects.filter(pk=task_id).first()
        except (TypeError, ValueError, OverflowError):
            execution = None
        if execution is None:
            return {"result": False, "message": "collect_task_id does not exist"}
        if execution.status in {
            ScanExecution.STATUS_COMPLETED,
            ScanExecution.STATUS_FAILED,
            ScanExecution.STATUS_TIMED_OUT,
            ScanExecution.STATUS_FINALIZING,
        }:
            return {"result": True, "scan_done": True, "listed": False, "task_id": execution.id}

        should_finalize = False
        with transaction.atomic():
            execution = ScanExecution.objects.select_for_update().get(pk=execution.pk)
            schedule = dict(execution.schedule or {})
            schedule["scan_done"] = True
            execution.schedule = schedule
            execution.save(update_fields=["schedule", "updated_at"])
            should_finalize = execution.status == ScanExecution.STATUS_RUNNING and cls._pipeline_done(execution)
        logger.info("event=scan_done_received execution=%s", execution.id)

        if should_finalize:
            cls._kick_finalize(execution)
        return {"result": True, "scan_done": True, "listed": False, "task_id": execution.id}

    @staticmethod
    def _pipeline_done(execution):
        from apps.cmdb.services.scan_trigger_service import scan_pipeline_done

        return scan_pipeline_done(execution)

    @staticmethod
    def _kick_finalize(execution):
        from apps.cmdb.tasks.celery_tasks import finalize_scan_execution

        logger.info(
            "event=scan_pipeline_ready execution=%s received=%s target=%s",
            execution.id,
            execution.received_count,
            execution.target_count,
        )
        finalize_scan_execution.delay(execution.id, execution.claim_token)
