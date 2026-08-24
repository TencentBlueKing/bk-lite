from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.apm.adapters import VictoriaTracesTelemetryStore
from apps.apm.services.deployments import BACKFILL_LOOKBACK, backfill_inferred_deployment_events
from apps.core.logger import apm_logger as logger


class Command(BaseCommand):
    help = "从 VictoriaTraces 回填近窗推断部署事件。运行期命令，不参与 batch_init。"

    def add_arguments(self, parser):
        parser.add_argument("--lookback-days", type=int, default=BACKFILL_LOOKBACK.days)

    def handle(self, *args, **options):
        lookback_days = options["lookback_days"]
        if lookback_days <= 0 or lookback_days > BACKFILL_LOOKBACK.days:
            raise CommandError(f"lookback-days 必须在 1 到 {BACKFILL_LOOKBACK.days} 之间")
        result = backfill_inferred_deployment_events(
            VictoriaTracesTelemetryStore(),
            observed_at=timezone.now(),
            lookback=timedelta(days=lookback_days),
        )
        logger.info(
            "APM inferred deployment events backfilled",
            extra={"created": result.created, "updated": result.updated, "lookback_days": lookback_days},
        )
        self.stdout.write(f"created={result.created} updated={result.updated}")
