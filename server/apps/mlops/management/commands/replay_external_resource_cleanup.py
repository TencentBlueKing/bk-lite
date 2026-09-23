from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.mlops.models.external_resource_cleanup import ExternalResourceCleanupIntent
from apps.mlops.tasks.external_resource_cleanup import dispatch_pending_external_resource_cleanup


class Command(BaseCommand):
    help = "把 FAILED 外部资源清理意图置回 PENDING 并投递周期扫描"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 100:
            raise CommandError("--limit 必须在 1 到 100 之间")

        with transaction.atomic():
            intent_ids = list(
                ExternalResourceCleanupIntent.objects.select_for_update()
                .filter(status=ExternalResourceCleanupIntent.Status.FAILED)
                .order_by("pk")
                .values_list("pk", flat=True)[:limit]
            )
            reset = ExternalResourceCleanupIntent.objects.filter(pk__in=intent_ids).update(
                status=ExternalResourceCleanupIntent.Status.PENDING,
                attempts=0,
                claim_token="",
                claim_expires_at=None,
                next_retry_at=None,
            )

        result = dispatch_pending_external_resource_cleanup()
        self.stdout.write(f"replayed={reset} claimed={result['claimed']} scheduled={result['scheduled']}")
