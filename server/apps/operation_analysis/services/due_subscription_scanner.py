"""DueSubscriptionScanner：发现到期订阅并创建 scheduled Execution。

只负责扫描与调用 create_scheduled；不调用 Render / Delivery / Orchestrator。
不负责补偿循环：每个 due subscription 最多一次 create_scheduled，
catch_up 计划点由 create_scheduled 锁内计算。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)

logger = logging.getLogger(__name__)

DEFAULT_SCAN_BATCH_SIZE = 50


@dataclass(frozen=True)
class ScanStats:
    scanned: int = 0
    created: int = 0
    skipped_in_flight: int = 0
    already_exists: int = 0
    skipped_other: int = 0


class DueSubscriptionScanner:
    @classmethod
    def scan(
        cls,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_SCAN_BATCH_SIZE,
    ) -> ScanStats:
        moment = now or timezone.now()
        due_ids = list(
            DashboardReportSubscription.objects.filter(
                status=DashboardReportSubscription.Status.ACTIVE,
                deleted_at__isnull=True,
                schedule_type__isnull=False,
                next_run_at__isnull=False,
                next_run_at__lte=moment,
            )
            .order_by("next_run_at", "id")
            .values_list("id", flat=True)[:limit]
        )

        created = 0
        skipped_in_flight = 0
        already_exists = 0
        skipped_other = 0

        for subscription_id in due_ids:
            result = DashboardReportExecutionService.create_scheduled(
                subscription_id,
                now=moment,
            )
            if result.created:
                created += 1
            elif result.skipped_in_flight:
                skipped_in_flight += 1
            elif result.already_exists:
                already_exists += 1
            else:
                skipped_other += 1

        stats = ScanStats(
            scanned=len(due_ids),
            created=created,
            skipped_in_flight=skipped_in_flight,
            already_exists=already_exists,
            skipped_other=skipped_other,
        )
        if stats.scanned:
            logger.info(
                "DueSubscriptionScanner finished: scanned=%s created=%s "
                "skipped_in_flight=%s already_exists=%s skipped_other=%s",
                stats.scanned,
                stats.created,
                stats.skipped_in_flight,
                stats.already_exists,
                stats.skipped_other,
            )
        return stats
