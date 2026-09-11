from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.alerts.models import Alert
from apps.alerts.service.monitor_sources import normalize_push_source_ids


class Command(BaseCommand):
    help = "分批回填历史告警监控源；不触发分派/通知，不改变更新时间"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--after-id", type=int, default=0, help="从上次输出的 last_id 之后继续")
        parser.add_argument("--dry-run", action="store_true", help="仅统计将更新的记录")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        last_id = options["after_id"]
        if not 1 <= batch_size <= 1000 or last_id < 0:
            raise CommandError("batch-size 必须在 1–1000 之间，after-id 不能小于 0")
        upper_id = Alert.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        scanned = updated = 0
        while last_id < upper_id:
            ids = list(Alert.objects.filter(pk__gt=last_id, pk__lte=upper_id).order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            with transaction.atomic():
                alerts = Alert.objects.filter(pk__in=ids).select_for_update().order_by("pk")
                for alert in alerts:
                    sources = normalize_push_source_ids(alert.events.order_by().values_list("push_source_id", flat=True).distinct())
                    scanned += 1
                    if sources == alert.push_source_ids:
                        continue
                    updated += 1
                    if not options["dry_run"]:
                        Alert.objects.filter(pk=alert.pk).update(push_source_ids=sources)
            last_id = ids[-1]
            self.stdout.write(f"scanned={scanned} updated={updated} last_id={last_id} dry_run={options['dry_run']}")
        self.stdout.write(self.style.SUCCESS(f"监控源回填完成: scanned={scanned} updated={updated} last_id={last_id}"))
