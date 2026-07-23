import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils.timezone import now

from apps.cmdb.models.ipam_models import IPAMReconcileRun, IPAMReconcileRunStatus
from apps.core.logger import cmdb_logger as logger


@dataclass(frozen=True)
class EnqueueResult:
    run: IPAMReconcileRun
    reused: bool


class IPAMReconcileJob:
    DEFAULT_LEASE_SECONDS = 7200

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return f"{exc.__class__.__name__}: IPAM 对账执行失败"

    @staticmethod
    def _dispatch(run_id) -> None:
        from apps.cmdb.tasks.celery_tasks import execute_ipam_reconcile_task

        execute_ipam_reconcile_task.delay(str(run_id))

    @classmethod
    def enqueue(cls, *, trigger: str, dispatch: bool = True) -> EnqueueResult:
        active_statuses = [IPAMReconcileRunStatus.PENDING, IPAMReconcileRunStatus.RUNNING]
        reused = False
        try:
            with transaction.atomic():
                run = IPAMReconcileRun.objects.filter(status__in=active_statuses).order_by("created_at").first()
                if run:
                    reused = True
                else:
                    run = IPAMReconcileRun.objects.create(trigger=trigger)
        except IntegrityError:
            run = IPAMReconcileRun.objects.filter(status__in=active_statuses).order_by("created_at").first()
            if not run:
                raise
            reused = True

        current_time = now()
        should_dispatch = run.status == IPAMReconcileRunStatus.PENDING or (
            run.status == IPAMReconcileRunStatus.RUNNING
            and run.lease_expires_at is not None
            and run.lease_expires_at <= current_time
        )
        if dispatch and should_dispatch:
            try:
                cls._dispatch(run.run_id)
            except Exception as exc:
                IPAMReconcileRun.objects.filter(id=run.id, status=IPAMReconcileRunStatus.PENDING).update(
                    last_error=cls._safe_error(exc),
                    updated_at=current_time,
                )
                logger.error(
                    "[IPAM] 对账任务派发失败 run_id=%s error_type=%s",
                    run.run_id,
                    exc.__class__.__name__,
                )
                run.refresh_from_db()
        return EnqueueResult(run=run, reused=reused)

    @classmethod
    def claim(cls, run_id, *, owner_token: str, lease_seconds: int | None = None) -> bool:
        current_time = now()
        lease_until = current_time + timedelta(seconds=lease_seconds or cls.DEFAULT_LEASE_SECONDS)
        run = IPAMReconcileRun.objects.filter(run_id=run_id).first()
        if not run:
            return False

        filters = {"id": run.id}
        if run.status == IPAMReconcileRunStatus.PENDING:
            filters["status"] = IPAMReconcileRunStatus.PENDING
        elif (
            run.status == IPAMReconcileRunStatus.RUNNING
            and run.lease_expires_at is not None
            and run.lease_expires_at <= current_time
        ):
            filters.update(
                status=IPAMReconcileRunStatus.RUNNING,
                owner_token=run.owner_token,
                lease_expires_at=run.lease_expires_at,
            )
        else:
            return False

        return bool(
            IPAMReconcileRun.objects.filter(**filters).update(
                status=IPAMReconcileRunStatus.RUNNING,
                owner_token=owner_token,
                lease_expires_at=lease_until,
                started_at=current_time,
                finished_at=None,
                last_error="",
                updated_at=current_time,
            )
        )

    @staticmethod
    def finish_success(run_id, *, owner_token: str, stats: dict) -> bool:
        current_time = now()
        return bool(
            IPAMReconcileRun.objects.filter(
                run_id=run_id,
                status=IPAMReconcileRunStatus.RUNNING,
                owner_token=owner_token,
            ).update(
                status=IPAMReconcileRunStatus.SUCCESS,
                active_scope=None,
                stats=stats,
                owner_token="",
                lease_expires_at=None,
                finished_at=current_time,
                updated_at=current_time,
            )
        )

    @classmethod
    def finish_error(cls, run_id, *, owner_token: str, exc: Exception) -> bool:
        current_time = now()
        return bool(
            IPAMReconcileRun.objects.filter(
                run_id=run_id,
                status=IPAMReconcileRunStatus.RUNNING,
                owner_token=owner_token,
            ).update(
                status=IPAMReconcileRunStatus.ERROR,
                active_scope=None,
                last_error=cls._safe_error(exc),
                owner_token="",
                lease_expires_at=None,
                finished_at=current_time,
                updated_at=current_time,
            )
        )

    @classmethod
    def execute(cls, run_id, *, owner_token: str | None = None) -> dict:
        token = owner_token or uuid.uuid4().hex
        if not cls.claim(run_id, owner_token=token):
            run = IPAMReconcileRun.objects.filter(run_id=run_id).first()
            return run.stats if run and run.status == IPAMReconcileRunStatus.SUCCESS else {
                "status": run.status if run else "missing"
            }

        from apps.cmdb.services.ipam_reconcile import run_reconciliation

        try:
            stats = run_reconciliation()
        except Exception as exc:
            cls.finish_error(run_id, owner_token=token, exc=exc)
            raise
        cls.finish_success(run_id, owner_token=token, stats=stats)
        return stats
