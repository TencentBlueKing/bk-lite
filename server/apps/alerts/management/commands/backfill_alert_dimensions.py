from django.core.management.base import BaseCommand
from django.db import transaction

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.models.models import Alert
from apps.core.logger import alert_logger as logger


class Command(BaseCommand):
    help = "回填历史告警 dimensions 字段"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="每批处理的告警数量",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅展示结果，不实际写入",
        )

    def handle(self, *args, **options):
        batch_size = max(int(options.get("batch_size") or 200), 1)
        dry_run = bool(options.get("dry_run"))

        queryset = Alert.objects.exclude(group_by_field__isnull=True).exclude(group_by_field="").prefetch_related("events").order_by("pk")

        scanned_count = 0
        updated_count = 0
        skipped_count = 0

        for alert in queryset.iterator(chunk_size=batch_size):
            scanned_count += 1

            if alert.dimensions:
                skipped_count += 1
                continue

            dimensions = AlertBuilder._resolve_dimensions(alert.events.all().order_by("pk"), alert.group_by_field or "")
            if not dimensions:
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(f"[DRY-RUN] alert={alert.alert_id} dimensions={dimensions}")
                updated_count += 1
                continue

            with transaction.atomic():
                alert.dimensions = dimensions
                alert.save(update_fields=["dimensions"])

            updated_count += 1

        summary = (
            f"告警 dimensions 回填完成: scanned={scanned_count}, "
            f"updated={updated_count}, skipped={skipped_count}, dry_run={dry_run}"
        )
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))
