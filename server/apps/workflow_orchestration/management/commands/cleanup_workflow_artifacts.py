from django.core.management.base import BaseCommand

from apps.workflow_orchestration.services.artifacts import cleanup_expired_artifacts


class Command(BaseCommand):
    help = "清理编排中心已到期的报告对象，保留数据库摘要与审计字段"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        result = cleanup_expired_artifacts(batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"selected={result['selected']} deleted={result['deleted']} failed={result['failed']}"))
