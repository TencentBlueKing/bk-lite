from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from django.db import transaction
from django.utils import timezone

from apps.monitor.models.snmp_ifmib_reconcile import SnmpIfmibReconcileState


@dataclass(frozen=True)
class ReconcileClaim:
    status: str
    cursor: tuple[datetime, str] | None = None


@dataclass(frozen=True)
class OwnedWriteResult:
    executed: bool
    value: object = None


class SnmpIfmibReconcileStateService:
    """用单行条件更新约束 IF-MIB 对账的 owner、租约、游标与完成态。"""

    @staticmethod
    def claim(*, version: int, owner_token: str, lease_seconds: int) -> ReconcileClaim:
        current_time = timezone.now()
        lease_until = current_time + timedelta(seconds=lease_seconds)
        with transaction.atomic():
            SnmpIfmibReconcileState.objects.get_or_create(version=version)
            state = SnmpIfmibReconcileState.objects.select_for_update().get(version=version)
            if state.completed_at is not None:
                return ReconcileClaim(status="completed")
            if state.owner_token and state.lease_expires_at and state.lease_expires_at > current_time:
                return ReconcileClaim(status="running")
            cursor = (state.cursor_created_at, state.cursor_config_id) if state.cursor_created_at is not None and state.cursor_config_id else None
            state.owner_token = owner_token
            state.lease_expires_at = lease_until
            state.save(update_fields=["owner_token", "lease_expires_at", "updated_at"])
            return ReconcileClaim(status="claimed", cursor=cursor)

    @staticmethod
    def renew_progress(
        *,
        version: int,
        owner_token: str,
        lease_seconds: int,
        cursor: tuple[datetime, str] | None,
    ) -> bool:
        current_time = timezone.now()
        updates = {
            "lease_expires_at": current_time + timedelta(seconds=lease_seconds),
            "updated_at": current_time,
        }
        if cursor is not None:
            updates.update(
                cursor_created_at=cursor[0],
                cursor_config_id=str(cursor[1]),
            )
        return bool(
            SnmpIfmibReconcileState.objects.filter(
                version=version,
                owner_token=owner_token,
                completed_at__isnull=True,
                lease_expires_at__gt=current_time,
            ).update(**updates)
        )

    @staticmethod
    def run_owned_write(
        *,
        version: int,
        owner_token: str,
        lease_seconds: int,
        write: Callable[[], object],
    ) -> OwnedWriteResult:
        """锁住租约行执行一次写入；过期 owner 不得进入外部 CAS。"""
        current_time = timezone.now()
        with transaction.atomic():
            state = (
                SnmpIfmibReconcileState.objects.select_for_update()
                .filter(
                    version=version,
                    owner_token=owner_token,
                    completed_at__isnull=True,
                    lease_expires_at__gt=current_time,
                )
                .first()
            )
            if state is None:
                return OwnedWriteResult(executed=False)
            state.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
            state.save(update_fields=["lease_expires_at", "updated_at"])
            return OwnedWriteResult(executed=True, value=write())

    @staticmethod
    def finish(*, version: int, owner_token: str) -> bool:
        current_time = timezone.now()
        return bool(
            SnmpIfmibReconcileState.objects.filter(
                version=version,
                owner_token=owner_token,
                completed_at__isnull=True,
                lease_expires_at__gt=current_time,
            ).update(
                owner_token="",
                lease_expires_at=None,
                cursor_created_at=None,
                cursor_config_id="",
                completed_at=current_time,
                updated_at=current_time,
            )
        )

    @staticmethod
    def reset_cursor(*, version: int, owner_token: str) -> bool:
        """仅当前未过期 owner 可清空游标，供毒数据隔离扫描后重新检查全量。"""
        current_time = timezone.now()
        return bool(
            SnmpIfmibReconcileState.objects.filter(
                version=version,
                owner_token=owner_token,
                completed_at__isnull=True,
                lease_expires_at__gt=current_time,
            ).update(
                cursor_created_at=None,
                cursor_config_id="",
                updated_at=current_time,
            )
        )
