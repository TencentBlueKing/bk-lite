import ipaddress
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils.timezone import now

from apps.cmdb.constants.constants import OPERATOR_COLLECT_TASK, CollectRunStatusType
from apps.cmdb.models import EXECUTE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE
from apps.cmdb.models.collect_access_check import CollectAccessCheck, CollectAccessCheckRow
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.stargazer_collect_trigger import AccessCheckRemoteError, StargazerCollectTriggerClient
from apps.cmdb.utils.change_record import create_change_record
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.web_utils import WebUtils

ACCESS_CHECK_MODEL_IDS = frozenset(
    {
        "mysql",
        "postgresql",
        "mssql",
        "influxdb",
        "aliyun_account",
        "qcloud",
        "hwcloud",
        "fusioninsight",
        "vmware_vc",
        "hyperv_host",
        "storage",
        "netapp_ontap",
    }
)
CONCLUSIONS = frozenset(
    {
        "pending",
        "network_unreachable",
        "not_tested",
        "credential_ok",
        "credential_rejected",
        "permission_denied",
        "no_response",
        "protocol_or_tls",
        "service_unavailable",
        "rate_limited",
        "unsupported",
        "probe_error",
        "system_error",
        "no_credential",
    }
)
_BATCHES_COMPLETE = "batches_complete"
_FAIL_CONCLUSION = {
    "stargazer_timeout": "no_response",
    "stargazer_unavailable": "system_error",
    "result_persist_failed": "system_error",
    "check_busy": "no_response",
}
_DETAIL_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
_ACTIVE_COLLECT = frozenset({CollectRunStatusType.RUNNING, CollectRunStatusType.WRITING})
_ADMISSION_HTTP = {
    "check_busy": 429,
    "stargazer_timeout": 503,
    "stargazer_unavailable": 503,
}
_ROW_FIELDS = ("target", "credential_id", "credential_name", "conclusion", "detail_code", "attempted")


def _expand_host_token(token: str) -> list[str]:
    """把 192.168.0.1-192.168.0.3 拆成单个地址。非法网段保持原样。"""
    text = token.strip()
    if "-" not in text or text.count(".") < 3:
        return [text] if text else []
    start_text, end_text = text.split("-", 1)
    try:
        start_ip = ipaddress.IPv4Address(start_text.strip())
        end_ip = ipaddress.IPv4Address(end_text.strip())
    except (ValueError, ipaddress.AddressValueError):
        return [text]
    if int(end_ip) < int(start_ip):
        return [text]
    return [str(ipaddress.IPv4Address(value)) for value in range(int(start_ip), int(end_ip) + 1)]


def _expand_targets(raw_hosts) -> list[str]:
    if isinstance(raw_hosts, (list, tuple)):
        parts = [str(item).strip() for item in raw_hosts if str(item).strip()]
    else:
        parts = [part.strip() for part in str(raw_hosts or "").split(",") if part.strip()]
    expanded: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for host in _expand_host_token(part):
            if host in seen:
                continue
            seen.add(host)
            expanded.append(host)
    return expanded


class CollectAccessCheckService:
    @staticmethod
    def in_scope(task) -> bool:
        return getattr(task, "model_id", "") in ACCESS_CHECK_MODEL_IDS

    @classmethod
    def get(cls, task):
        check = CollectAccessCheck.objects.filter(task=task).first()
        if check is None:
            return WebUtils.response_error(
                {"error_code": "not_tested"},
                error_message="尚未测试",
                status_code=404,
            )
        cls._expire_if_stale(check, task)
        check.refresh_from_db()
        return WebUtils.response_success(cls.serialize(check))

    @classmethod
    def start(cls, task, operator):
        if not cls.in_scope(task):
            return WebUtils.response_error(
                {"error_code": "out_of_scope"},
                error_message="该采集对象不支持连通性测试",
                status_code=400,
            )
        try:
            pending = cls._pending_rows(task)
        except Exception as exc:  # noqa: BLE001 - 展开失败不连接目标
            logger.error(
                "event=access_check_expand_failed task_id=%s failed_stage=expand error_type=%s",
                task.pk,
                type(exc).__name__,
            )
            return WebUtils.response_error(
                {"error_code": "invalid_task"},
                error_message="采集任务无法展开目标",
                status_code=400,
            )
        if not pending:
            return WebUtils.response_error(
                {"error_code": "invalid_task"},
                error_message="采集任务没有目标",
                status_code=400,
            )

        limit = int(getattr(settings, "ACCESS_CHECK_MAX_ACTIVE", 4))
        with transaction.atomic():
            locked = CollectModels.objects.select_for_update().get(pk=task.pk)
            current = CollectAccessCheck.objects.select_for_update().filter(task=locked).first()
            if current is not None:
                cls._expire_if_stale(current, locked)
                current.refresh_from_db()
            if locked.exec_status in _ACTIVE_COLLECT:
                return WebUtils.response_error(
                    {"error_code": "collect_running"},
                    error_message="任务正在采集",
                    status_code=409,
                )
            if current is not None and current.status == "running":
                return WebUtils.response_success(cls.serialize(current))
            if CollectAccessCheck.objects.filter(status="running").count() >= limit:
                return WebUtils.response_error(
                    {"error_code": "check_busy"},
                    error_message="连通性测试繁忙",
                    status_code=429,
                )
            check = cls._replace_check(locked, operator, pending)
            if not any(item["conclusion"] == "pending" for item in pending):
                cls._finish_locally(check)
                return JsonResponse(
                    {"data": cls.serialize(check), "result": True, "message": ""},
                    status=202,
                )
        try:
            StargazerCollectTriggerClient().admit_access_check(task, check.id)
        except AccessCheckRemoteError as exc:
            cls.fail(check, exc.error_code)
            logger.error(
                "event=access_check_failed check_id=%s failed_stage=admit error_type=%s",
                check.id,
                type(exc).__name__,
            )
            return WebUtils.response_error(
                {"error_code": exc.error_code},
                error_message="连通性测试未能开始",
                status_code=_ADMISSION_HTTP.get(exc.error_code, 503),
            )
        return JsonResponse(
            {"data": cls.serialize(CollectAccessCheck.objects.get(pk=check.pk)), "result": True, "message": ""},
            status=202,
        )

    @classmethod
    def _replace_check(cls, task, operator, pending):
        CollectAccessCheck.objects.filter(task=task).delete()
        check = CollectAccessCheck.objects.create(
            task=task,
            status="running",
            total_count=len(pending),
            finished_count=0,
            started_at=now(),
            operator=str(operator or "")[:150],
        )
        CollectAccessCheckRow.objects.bulk_create(
            [
                CollectAccessCheckRow(
                    access_check=check,
                    position=index,
                    target=item["target"],
                    credential_id=item["credential_id"],
                    credential_name=item["credential_name"],
                    conclusion=item["conclusion"],
                    detail_code="",
                    attempted=False,
                )
                for index, item in enumerate(pending)
            ]
        )
        return check

    @classmethod
    def _expire_if_stale(cls, check, task):
        if check.status != "running" or check.started_at is None:
            return
        timeout = int(getattr(task, "timeout", 60) or 60)
        target_count = check.rows.values("target").distinct().count() or 1
        deadline = max(timeout, 1) * target_count + 30
        if check.started_at + timedelta(seconds=deadline) <= now():
            cls.fail(check, "stargazer_timeout")

    @staticmethod
    def _finish_locally(check):
        check.status = "finished"
        check.finished_at = now()
        check.finished_count = check.total_count
        check.save(update_fields=["status", "finished_at", "finished_count"])

    @classmethod
    def _pending_rows(cls, task):
        node = NodeParamsFactory.get_node_params(task, resolve_credentials=False)
        _field, raw_hosts = node.get_hosts()
        targets = _expand_targets(raw_hosts)
        credentials = task.credential if isinstance(task.credential, list) else []
        rows = []
        for target in targets:
            matched = []
            for index, credential in enumerate(credentials, 1):
                if not isinstance(credential, dict):
                    continue
                bound = str(credential.get("target_host") or credential.get("host") or "").strip()
                if bound and bound != target:
                    continue
                matched.append(
                    {
                        "target": target[:255],
                        "credential_id": str(credential.get("credential_id") or credential.get("id") or f"credential-{index}")[:64],
                        "credential_name": str(credential.get("name") or credential.get("credential_name") or f"凭据 {index}")[:255],
                        "conclusion": "pending",
                    }
                )
            if matched:
                rows.extend(matched)
            else:
                rows.append(
                    {
                        "target": target[:255],
                        "credential_id": "",
                        "credential_name": "",
                        "conclusion": "no_credential",
                    }
                )
        return rows

    @classmethod
    def _clean_remote_rows(cls, remote_rows):
        cleaned = []
        for raw in remote_rows:
            if not isinstance(raw, dict):
                continue
            conclusion = raw.get("conclusion")
            if conclusion not in CONCLUSIONS or conclusion == "pending":
                conclusion = "probe_error"
            detail_code = str(raw.get("detail_code") or "")
            if not _DETAIL_CODE.match(detail_code):
                detail_code = ""
            cleaned.append(
                {
                    "target": str(raw.get("target") or "")[:255],
                    "credential_id": str(raw.get("credential_id") or "")[:64],
                    "credential_name": str(raw.get("credential_name") or "")[:255],
                    "conclusion": conclusion,
                    "detail_code": detail_code,
                    "attempted": bool(raw.get("attempted")),
                }
            )
        return cleaned

    @classmethod
    def apply_remote_rows(cls, check, remote_rows):
        cls.merge_remote_rows(check, remote_rows, remote_done=True)

    @classmethod
    def merge_remote_rows(cls, check, remote_rows, *, remote_done):
        """按目标加凭据更新已有行。进行中的批次不结束测试，全部地址回来后才结束。"""
        cleaned = cls._clean_remote_rows(remote_rows)
        with transaction.atomic():
            locked = CollectAccessCheck.objects.select_for_update().get(pk=check.pk)
            if locked.status == "failed":
                return
            for item in cleaned:
                row = locked.rows.filter(target=item["target"], credential_id=item["credential_id"]).first()
                if row is None:
                    position = locked.rows.order_by("-position").values_list("position", flat=True).first()
                    CollectAccessCheckRow.objects.create(
                        access_check=locked,
                        position=0 if position is None else position + 1,
                        **item,
                    )
                    continue
                row.credential_name = item["credential_name"]
                row.conclusion = item["conclusion"]
                row.detail_code = item["detail_code"]
                row.attempted = item["attempted"]
                row.save(update_fields=["credential_name", "conclusion", "detail_code", "attempted"])
            pending = locked.rows.filter(conclusion="pending").exists()
            remote_complete = remote_done or locked.error_code == _BATCHES_COMPLETE
            locked.finished_count = locked.rows.exclude(conclusion="pending").count()
            if remote_complete and not pending:
                already_finished = locked.status == "finished"
                locked.status = "finished"
                locked.finished_at = locked.finished_at or now()
                locked.error_code = ""
                locked.save(update_fields=["status", "finished_at", "finished_count", "error_code"])
                if not already_finished:
                    cls._audit(locked)
                return
            if remote_done and pending:
                locked.error_code = _BATCHES_COMPLETE
            locked.save(update_fields=["finished_count", "error_code"])

    @classmethod
    def fail(cls, check, error_code):
        code = str(error_code or "")[:64]
        conclusion = _FAIL_CONCLUSION.get(code, "probe_error")
        detail_code = "system_error" if conclusion == "system_error" else code
        check.rows.filter(conclusion="pending").update(
            conclusion=conclusion,
            detail_code=detail_code,
            attempted=False,
        )
        check.status = "failed"
        check.finished_at = now()
        check.finished_count = check.rows.exclude(conclusion="pending").count()
        check.error_code = error_code[:64]
        check.save(update_fields=["status", "finished_at", "finished_count", "error_code"])

    @staticmethod
    def _audit(check):
        counts = {}
        for row in check.rows.all():
            counts[row.conclusion] = counts.get(row.conclusion, 0) + 1
        summary = ",".join(f"{key}={value}" for key, value in sorted(counts.items()))
        try:
            create_change_record(
                inst_id=check.task_id,
                model_id=check.task.model_id,
                label="采集任务",
                _type=EXECUTE,
                operator=check.operator,
                message=f"连通性测试完成. 任务名称: {check.task.name}. 总数: {check.total_count}. {summary}",
                model_object=OPERATOR_COLLECT_TASK,
                scenario=COLLECT_AUTOMATION_CHANGE,
            )
        except Exception as exc:  # noqa: BLE001 - 审计失败不改变测试结论
            logger.error(
                "event=access_check_audit_failed task_id=%s check_id=%s failed_stage=audit error_type=%s",
                check.task_id,
                check.id,
                type(exc).__name__,
            )

    @staticmethod
    def serialize(check):
        rows = [
            {
                "target": row.target,
                "credential_id": row.credential_id,
                "credential_name": row.credential_name,
                "conclusion": row.conclusion,
                "detail_code": row.detail_code,
                "attempted": row.attempted,
            }
            for row in check.rows.order_by("position", "id")
        ]
        return {
            "id": check.id,
            "task_id": check.task_id,
            "status": check.status,
            "total_count": check.total_count,
            "finished_count": check.finished_count,
            "started_at": check.started_at,
            "finished_at": check.finished_at,
            "error_code": check.error_code,
            "rows": rows,
        }


def public_access_check_payload(data: dict) -> dict:
    """只保留回程约定字段，避免口令进入 Celery 参数。"""
    rows = []
    for raw in data.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        rows.append({field: raw.get(field) for field in _ROW_FIELDS})
    return {
        "collect_task_id": str(data.get("collect_task_id") or ""),
        "check_id": str(data.get("check_id") or ""),
        "status": str(data.get("status") or ""),
        "error_code": str(data.get("error_code") or ""),
        "rows": rows,
    }


def apply_access_check_callback(payload: dict) -> None:
    check_id = str((payload or {}).get("check_id") or "")
    task_id = str((payload or {}).get("collect_task_id") or "")
    check = CollectAccessCheck.objects.select_related("task").filter(pk=check_id).first() if check_id.isdigit() else None
    if check is None or str(check.task_id) != task_id or check.status == "failed":
        return
    status = str(payload.get("status") or "")
    if check.status == "finished" and status == "finished":
        return
    try:
        if status in {"running", "finished"}:
            CollectAccessCheckService.merge_remote_rows(
                check,
                payload.get("rows") or [],
                remote_done=status == "finished",
            )
            return
        if check.status != "running":
            return
        CollectAccessCheckService.fail(check, str(payload.get("error_code") or "stargazer_unavailable"))
    except Exception as exc:  # noqa: BLE001 - worker 边界持有这一次失败
        logger.error(
            "event=access_check_failed check_id=%s failed_stage=persist error_type=%s",
            check_id,
            type(exc).__name__,
        )
        check.refresh_from_db()
        if check.status == "running":
            CollectAccessCheckService.fail(check, "result_persist_failed")
