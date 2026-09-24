import time

from django.core.management.base import BaseCommand

from apps.workflow_orchestration.services.artifacts import cleanup_expired_artifacts


class Command(BaseCommand):
    help = "在运行期定期清理编排中心已到期的报告对象"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=3600)
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        interval = max(60, min(int(options["interval"]), 86400))
        while True:
            result = cleanup_expired_artifacts(batch_size=options["batch_size"])
            if any(result.values()):
                self.stdout.write(f"artifact cleanup: selected={result['selected']} deleted={result['deleted']} failed={result['failed']}")
            if options["once"]:
                return
            time.sleep(interval)
