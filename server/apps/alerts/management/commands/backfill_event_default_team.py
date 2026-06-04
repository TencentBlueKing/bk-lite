from django.core.management.base import BaseCommand
from django.db import transaction

from apps.alerts.models.models import Event
from apps.core.logger import alert_logger as logger


class Command(BaseCommand):
    help = "回填 team 为空的历史事件到默认组织 [1]"

    DEFAULT_TEAM = [1]

    @staticmethod
    def _batched(iterable, batch_size):
        batch = []
        for item in iterable:
            batch.append(item)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="每批处理的事件数量",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅展示结果，不实际写入",
        )

    def handle(self, *args, **options):
        batch_size = max(int(options.get("batch_size") or 500), 1)
        dry_run = bool(options.get("dry_run"))

        queryset = Event.objects.filter(team=[]).order_by("pk")
        updated_count = 0

        event_id_queryset = queryset.values_list("id", "event_id")
        scanned_count = queryset.count()

        for batch in self._batched(event_id_queryset.iterator(chunk_size=batch_size), batch_size):
            event_ids = [event_id for event_id, _ in batch]

            if dry_run:
                for _, event_id in batch:
                    self.stdout.write(f"[DRY-RUN] event={event_id} team={self.DEFAULT_TEAM}")
                updated_count += len(batch)
                continue

            with transaction.atomic():
                updated_count += Event.objects.filter(id__in=event_ids, team=[]).update(team=self.DEFAULT_TEAM.copy())

        summary = (
            f"事件 team 默认组织回填完成: scanned={scanned_count}, "
            f"updated={updated_count}, dry_run={dry_run}, default_team={self.DEFAULT_TEAM}"
        )
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))
