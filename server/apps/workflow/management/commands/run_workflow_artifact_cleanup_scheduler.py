import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.workflow.services.artifacts import cleanup_expired_artifacts


class Command(BaseCommand):
    help = "在运行期定期清理编排中心已到期的报告对象"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=3600)
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        interval = max(60, min(int(options["interval"]), 86400))
        while True:
            # 常驻命令没有请求结束信号，在执行 ORM 的线程内管理连接。
            close_old_connections()
            try:
                result = cleanup_expired_artifacts(batch_size=options["batch_size"])
            finally:
                close_old_connections()
            if any(result.values()):
                self.stdout.write(f"artifact cleanup: selected={result['selected']} deleted={result['deleted']} failed={result['failed']}")
            if options["once"]:
                return
            time.sleep(interval)
