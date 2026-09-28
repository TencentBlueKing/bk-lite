import hashlib
import json
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.models.transfer_task import CmdbTransferGuard, CmdbTransferTask
from apps.system_mgmt.models.user import User


class TransferError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class TransferService:
    ACTIVE = ("queued", "running")
    MAX_ACTIVE = 5
    HISTORY_LIMIT = 5
    TERMINAL = ("succeeded", "partial_success", "failed", "cancelled")

    @classmethod
    def submit(
        cls,
        *,
        owner,
        kind,
        model_id,
        team_id,
        include_children,
        params,
        authorization,
        schema_hash,
        idempotency_key,
        source_key="",
        source_hash="",
        filename="",
        model_name="",
        retry_of=None,
    ):
        if not idempotency_key or len(idempotency_key) > 128:
            raise TransferError("invalid_idempotency_key", "请提供有效的 Idempotency-Key")
        if retry_of is not None:
            params = dict(params, retry_of=str(retry_of))
        request_hash = fingerprint([kind, model_id, team_id, include_children, params, source_hash])
        with transaction.atomic():
            locked_owner = User.objects.select_for_update().get(pk=owner.pk)
            if locked_owner.disabled:
                raise TransferError("owner_disabled", "用户已停用", 403)
            previous = CmdbTransferTask.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
            if previous:
                if previous.request_hash != request_hash:
                    raise TransferError("idempotency_conflict", "该请求标识已用于不同的提交内容", 409)
                if previous.delete_pending or previous.expires_at <= now():
                    raise TransferError("request_expired", "原任务已过期或删除，请重新提交", 409)
                return previous
            if cls.active_count(owner) >= cls.MAX_ACTIVE:
                raise TransferError("active_task_limit", "已有 5 个排队或执行中的任务，请等待完成或取消排队任务", 429)
            if retry_of is not None:
                old = cls.get(owner, retry_of)
                if kind != "export" or old.kind != "export" or old.status != "failed" or old.holds_slot:
                    raise TransferError("state_conflict", "仅已失败的导出任务允许重新提交", 409)
            task = CmdbTransferTask.objects.create(
                owner=owner,
                kind=kind,
                model_id=model_id,
                model_name=model_name or model_id,
                team_id=team_id,
                include_children=include_children,
                params=params,
                authorization=authorization,
                schema_hash=schema_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                source_key=source_key,
                source_hash=source_hash,
                filename=filename,
                expires_at=now() + timedelta(days=7),
            )
            if retry_of is not None:
                replaced = CmdbTransferTask.objects.filter(pk=retry_of, owner=owner, status="failed", holds_slot=False, delete_pending=False).update(
                    delete_pending=True
                )
                if not replaced:
                    raise TransferError("state_conflict", "原任务状态已变化，请刷新后重试", 409)
            cls.trim_history(owner)
            return task

    @classmethod
    def replayed_retry(cls, owner, task_id, idempotency_key):
        # 旧记录已隐藏甚至已日清后，同一重提请求仍返回已接纳的新任务。
        return cls.list(owner).filter(idempotency_key=idempotency_key, params__retry_of=str(uuid.UUID(str(task_id)))).first()

    @classmethod
    def active_count(cls, owner):
        return CmdbTransferTask.objects.filter(owner=owner, status__in=cls.ACTIVE).count()

    @classmethod
    def trim_history(cls, owner):
        # 所有调用者持有用户行锁，已结束历史与排队/执行额度分开计算。
        expired = list(
            CmdbTransferTask.objects.filter(
                owner=owner,
                status__in=(*cls.TERMINAL, "interrupted"),
                holds_slot=False,
                delete_pending=False,
            )
            .order_by("-created_at", "-id")
            .values_list("pk", flat=True)[cls.HISTORY_LIMIT :]
        )
        CmdbTransferTask.objects.filter(pk__in=expired, holds_slot=False).update(delete_pending=True)

    @classmethod
    def list(cls, owner):
        return (
            CmdbTransferTask.objects.filter(owner=owner, delete_pending=False)
            .filter(Q(expires_at__gt=now()) | Q(holds_slot=True) | Q(status__in=cls.ACTIVE))
            .order_by("-created_at", "-id")
        )

    @classmethod
    def get(cls, owner, task_id):
        task = cls.list(owner).filter(pk=task_id).first()
        if task is None:
            raise TransferError("task_not_found", "任务不存在或已过期", 404)
        return task

    @classmethod
    @transaction.atomic
    def cancel(cls, owner, task_id):
        User.objects.select_for_update().get(pk=owner.pk)
        task = cls.get(owner, task_id)
        if not CmdbTransferTask.objects.filter(pk=task.pk, status="queued").update(status="cancelled", phase="finished", finished_at=now()):
            raise TransferError("state_conflict", "任务已开始，无法取消", 409)
        cls.trim_history(owner)

    @classmethod
    def request_delete(cls, owner, task_id):
        task = cls.get(owner, task_id)
        if not CmdbTransferTask.objects.filter(pk=task.pk, status__in=cls.TERMINAL, holds_slot=False).update(delete_pending=True):
            raise TransferError("state_conflict", "执行未停止的任务不能删除", 409)

    @classmethod
    def claim(cls, task_id):
        with transaction.atomic():
            owner_id = CmdbTransferTask.objects.filter(pk=task_id).values_list("owner_id", flat=True).first()
            if owner_id is None:
                return None
            User.objects.select_for_update().get(pk=owner_id)
            CmdbTransferGuard.objects.get_or_create(key="scheduler")
            CmdbTransferGuard.objects.select_for_update().get(key="scheduler")
            task = CmdbTransferTask.objects.select_for_update().filter(pk=task_id).first()
            if not task or task.status != "queued" or task.delete_pending or task.expires_at <= now():
                return None
            if task.created_at + timedelta(minutes=30) <= now():
                cls.expire_queued(task.pk)
                return None
            if (
                task.kind == "import"
                and CmdbTransferTask.objects.filter(
                    kind="import",
                    model_id=task.model_id,
                    status="queued",
                    delete_pending=False,
                    created_at__gt=now() - timedelta(minutes=30),
                    expires_at__gt=now(),
                )
                .filter(Q(created_at__lt=task.created_at) | Q(created_at=task.created_at, pk__lt=task.pk))
                .exists()
            ):
                return None
            occupied = CmdbTransferTask.objects.filter(holds_slot=True)
            if occupied.count() >= 2 or (task.kind == "import" and occupied.filter(kind="import", model_id=task.model_id).exists()):
                return None
            token = uuid.uuid4().hex
            task.status = "running"
            task.phase = "authorizing"
            task.execution_token = token
            task.holds_slot = True
            task.started_at = now()
            task.lease_expires_at = now() + timedelta(minutes=2)
            task.deadline_at = now() + timedelta(minutes=15)
            task.save(update_fields=["status", "phase", "execution_token", "holds_slot", "started_at", "lease_expires_at", "deadline_at"])
            return token

    @classmethod
    def progress(cls, task_id, token, phase, processed=None, total=None, summary=None):
        values = dict(phase=phase, lease_expires_at=now() + timedelta(minutes=2))
        if processed is not None:
            values["processed_rows"] = processed
        if total is not None:
            values["total_rows"] = total
        if summary is not None:
            values["summary"] = summary
        updated = CmdbTransferTask.objects.filter(
            pk=task_id, execution_token=token, status="running", deadline_at__gt=now(), lease_expires_at__gt=now()
        ).update(**values)
        if not updated:
            raise TransferError("execution_lost", "执行已超时或已终止", 409)

    @classmethod
    @transaction.atomic
    def finish(cls, task_id, token, status, *, summary=None, artifacts=None, code="", message=""):
        owner_id = CmdbTransferTask.objects.filter(pk=task_id).values_list("owner_id", flat=True).first()
        if owner_id is None:
            return False
        User.objects.select_for_update().get(pk=owner_id)
        if status not in cls.TERMINAL:
            raise ValueError("invalid transfer terminal state")
        values = dict(
            status=status, phase="finished", finished_at=now(), holds_slot=False, lease_expires_at=None, error_code=code, message=message[:512]
        )
        if summary is not None:
            values["summary"] = summary
        if artifacts is not None:
            values["artifacts"] = artifacts
        updated = bool(
            CmdbTransferTask.objects.filter(
                pk=task_id, execution_token=token, status="running", deadline_at__gt=now(), lease_expires_at__gt=now()
            ).update(**values)
        )

        if updated:
            cls.trim_history(owner_id)
        return updated

    @classmethod
    @transaction.atomic
    def fail_execution(cls, task_id, token, code, message, *, execution_stopped=False, error_type=""):
        owner_id = CmdbTransferTask.objects.filter(pk=task_id).values_list("owner_id", flat=True).first()
        if owner_id is None:
            return False
        User.objects.select_for_update().get(pk=owner_id)
        task = (
            CmdbTransferTask.objects.select_for_update()
            .filter(
                pk=task_id,
                execution_token=token,
                holds_slot=True,
                status__in=("running", "failed", "interrupted"),
            )
            .first()
        )
        if not task:
            return False
        summary = dict(task.summary)
        old_failure = summary.get("_failure", {})
        stage = old_failure.get("stage", task.phase)
        uncertain = old_failure.get("result_uncertain", task.kind == "import" and stage in ("writing_instances", "writing_relations", "interrupted"))
        summary["_failure"] = {"stage": stage, "error_type": error_type or old_failure.get("error_type", ""), "result_uncertain": uncertain}
        # 仅收尾释放时保留 watchdog 已记录的原因，避免覆盖成无诊断价值的“执行终止”。
        if task.status == "running" or code != "execution_stopped":
            task.error_code = code
            task.message = message[:512]
        task.status = "failed"
        task.summary = summary
        task.finished_at = task.finished_at or now()
        task.holds_slot = not execution_stopped
        task.lease_expires_at = None
        task.save(update_fields=["status", "error_code", "message", "summary", "finished_at", "holds_slot", "lease_expires_at"])
        cls.trim_history(owner_id)
        return True

    @classmethod
    def interrupt(cls, task_id, token, code):
        # watchdog 只能终止逻辑执行权，不能证明同步图库调用已经返回。
        return cls.fail_execution(task_id, token, code, "执行超时或 Worker 失联，任务已失败", execution_stopped=False)

    @classmethod
    @transaction.atomic
    def expire_queued(cls, task_id):
        owner_id = CmdbTransferTask.objects.filter(pk=task_id).values_list("owner_id", flat=True).first()
        if owner_id is None:
            return False
        User.objects.select_for_update().get(pk=owner_id)
        updated = CmdbTransferTask.objects.filter(pk=task_id, status="queued").update(
            status="failed", phase="finished", error_code="queue_timeout", message="排队超过 30 分钟，请稍后重新提交", finished_at=now()
        )

        if updated:
            cls.trim_history(owner_id)
        return bool(updated)

    @classmethod
    @transaction.atomic
    def reconcile_interrupted(cls, task_id, *, verified_stopped, summary):
        """供管理员在核实进程退出及副作用之后显式解除占用，绝不重放写入。"""
        if not verified_stopped:
            raise TransferError("verification_required", "必须确认旧执行已经停止并核对写入结果", 409)
        owner_id = CmdbTransferTask.objects.filter(pk=task_id).values_list("owner_id", flat=True).first()
        if owner_id is None:
            return False
        User.objects.select_for_update().get(pk=owner_id)
        task = CmdbTransferTask.objects.select_for_update().filter(pk=task_id, status__in=("interrupted", "failed"), holds_slot=True).first()
        if task is None:
            return False
        summary = dict(summary)
        summary["_failure"] = task.summary.get(
            "_failure",
            {
                "stage": task.phase,
                "error_type": "",
                "result_uncertain": task.kind == "import" and task.status == "interrupted",
            },
        )
        updated = CmdbTransferTask.objects.filter(pk=task.pk, holds_slot=True).update(
            status="failed",
            holds_slot=False,
            lease_expires_at=None,
            summary=summary,
            message="管理员已确认旧执行停止并解除占用；已写入数据保留，未自动重跑",
            phase="finished",
        )
        if updated:
            cls.trim_history(owner_id)
        return bool(updated)
