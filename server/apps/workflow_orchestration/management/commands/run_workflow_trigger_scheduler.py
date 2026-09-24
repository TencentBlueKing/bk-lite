import time

from django.core.management.base import BaseCommand

from apps.workflow_orchestration.services.executions import sync_active_executions
from apps.workflow_orchestration.services.interactions import expire_due_interactions, retry_pending_interaction_deliveries
from apps.workflow_orchestration.services.triggers import run_due_cron_triggers


class Command(BaseCommand):
    help = "在运行期调度编排中心 Cron 触发器"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=15)

    def handle(self, *args, **options):
        interval = max(5, min(int(options["interval"]), 60))
        while True:
            summary = run_due_cron_triggers()
            timeout_summary = expire_due_interactions()
            delivery_summary = retry_pending_interaction_deliveries()
            sync_summary = sync_active_executions()
            if any(summary.values()):
                self.stdout.write(f"cron triggers: succeeded={summary['succeeded']} skipped={summary['skipped']} failed={summary['failed']}")
            if any(timeout_summary.values()):
                self.stdout.write(f"interaction timeouts: timed_out={timeout_summary['timed_out']} failed={timeout_summary['failed']}")
            if any(delivery_summary.values()):
                self.stdout.write(f"interaction delivery: delivered={delivery_summary['delivered']} failed={delivery_summary['failed']}")
            if any(sync_summary.values()):
                self.stdout.write(f"execution sync: synchronized={sync_summary['synchronized']} failed={sync_summary['failed']}")
            if options["once"]:
                return
            time.sleep(interval)
