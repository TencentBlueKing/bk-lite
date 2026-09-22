import hashlib
import json
import uuid
from datetime import timedelta

from django.db import transaction
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
    ACTIVE = ("queued", "running", "interrupted")
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
            if CmdbTransferTask.objects.filter(owner=owner, status__in=cls.ACTIVE).exists():
                raise TransferError("active_task_limit", "已有进行中或待核对任务，请先查看任务记录", 429)
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
            visible = list(cls.list(owner).values_list("pk", flat=True))
            if len(visible) > 5:
                CmdbTransferTask.objects.filter(pk__in=visible[5:], status__in=cls.TERMINAL).update(delete_pending=True)
            return task

    @classmethod
    def replayed_retry(cls, owner, task_id, idempotency_key):
        # 旧记录已隐藏甚至已日清后，同一重提请求仍返回已接纳的新任务。
        return cls.list(owner).filter(idempotency_key=idempotency_key, params__retry_of=str(uuid.UUID(str(task_id)))).first()

    @classmethod
    def list(cls, owner):
        return CmdbTransferTask.objects.filter(owner=owner, delete_pending=False, expires_at__gt=now()).order_by("-created_at", "-id")

    @classmethod
    def get(cls, owner, task_id):
        task = cls.list(owner).filter(pk=task_id).first()
        if task is None:
            raise TransferError("task_not_found", "任务不存在或已过期", 404)
        return task

    @classmethod
    def cancel(cls, owner, task_id):
        task = cls.get(owner, task_id)
        if not CmdbTransferTask.objects.filter(pk=task.pk, status="queued").update(status="cancelled", phase="finished", finished_at=now()):
            raise TransferError("state_conflict", "任务已开始，无法取消", 409)

    @classmethod
    def request_delete(cls, owner, task_id):
        task = cls.get(owner, task_id)
        if not CmdbTransferTask.objects.filter(pk=task.pk, status__in=cls.TERMINAL, holds_slot=False).update(delete_pending=True):
            raise TransferError("state_conflict", "进行中或待核对任务不能删除", 409)

    @classmethod
    def claim(cls, task_id):
        with transaction.atomic():
            CmdbTransferGuard.objects.get_or_create(key="scheduler")
            CmdbTransferGuard.objects.select_for_update().get(key="scheduler")
            task = CmdbTransferTask.objects.select_for_update().filter(pk=task_id).first()
            if not task or task.status != "queued" or task.delete_pending or task.expires_at <= now():
                return None
            if task.created_at + timedelta(minutes=30) <= now():
                cls.expire_queued(task.pk)
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
    def progress(cls, task_id, token, phase, processed=0, total=None, summary=None):
        values = dict(phase=phase, processed_rows=processed, lease_expires_at=now() + timedelta(minutes=2))
        if total is not None:
            values["total_rows"] = total
        if summary is not None:
            values["summary"] = summary
        updated = CmdbTransferTask.objects.filter(
            pk=task_id, execution_token=token, status="running", deadline_at__gt=now(), lease_expires_at__gt=now()
        ).update(**values)
        if not updated:
            raise TransferError("execution_lost", "执行已超时或被回收，结果需要核对", 409)

    @classmethod
    def finish(cls, task_id, token, status, *, summary=None, artifacts=None, code="", message=""):
        if status not in cls.TERMINAL:
            raise ValueError("invalid transfer terminal state")
        values = dict(
            status=status, phase="finished", finished_at=now(), holds_slot=False, lease_expires_at=None, error_code=code, message=message[:512]
        )
        if summary is not None:
            values["summary"] = summary
        if artifacts is not None:
            values["artifacts"] = artifacts
        return bool(
            CmdbTransferTask.objects.filter(
                pk=task_id, execution_token=token, status="running", deadline_at__gt=now(), lease_expires_at__gt=now()
            ).update(**values)
        )

    @classmethod
    def interrupt(cls, task_id, token, code):
        # 占用保留，防止尚未确认的图库写入与后续导入并发。
        return bool(
            CmdbTransferTask.objects.filter(pk=task_id, execution_token=token, status="running").update(
                status="interrupted",
                phase="interrupted",
                error_code=code,
                message="执行中断，可能已有部分写入，请联系管理员核对后解除占用",
                finished_at=now(),
            )
        )

    @staticmethod
    def expire_queued(task_id):
        return CmdbTransferTask.objects.filter(pk=task_id, status="queued").update(
            status="failed", phase="finished", error_code="queue_timeout", message="排队超过 30 分钟，请稍后重新提交", finished_at=now()
        )

    @classmethod
    def reconcile_interrupted(cls, task_id, *, verified_stopped, summary):
        """供管理员在核实进程退出及副作用之后显式解除占用，绝不重放写入。"""
        if not verified_stopped:
            raise TransferError("verification_required", "必须确认旧执行已经停止并核对写入结果", 409)
        return bool(
            CmdbTransferTask.objects.filter(pk=task_id, status="interrupted").update(
                status="failed",
                holds_slot=False,
                lease_expires_at=None,
                summary=summary,
                message="管理员已核对执行结果并解除占用；未自动重跑",
                phase="finished",
            )
        )
