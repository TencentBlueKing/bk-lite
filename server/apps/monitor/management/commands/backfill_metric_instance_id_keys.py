from django.core.management import BaseCommand
from django.db import transaction

from apps.monitor.models import Metric, MonitorObject
from apps.monitor.utils.instance_id_keys import (
    normalize_instance_id_keys,
    resolve_metric_instance_id_keys,
    resolve_monitor_object_instance_id_keys,
)


class Command(BaseCommand):
    help = "回填 monitor_object / metric 缺失的 instance_id_keys"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        monitor_objects = list(MonitorObject.objects.all().order_by("id"))
        object_key_map = {}
        object_updates = []
        for monitor_object in monitor_objects:
            resolved_keys = resolve_monitor_object_instance_id_keys(
                monitor_object.instance_id_keys,
                level=monitor_object.level,
                object_name=monitor_object.name,
            )
            object_key_map[monitor_object.id] = resolved_keys
            if resolved_keys != normalize_instance_id_keys(monitor_object.instance_id_keys):
                monitor_object.instance_id_keys = resolved_keys
                object_updates.append(monitor_object)

        metrics = list(Metric.objects.select_related("monitor_object").all().order_by("id"))
        metric_updates = []
        unresolved_metric_ids = []
        for metric in metrics:
            monitor_object_keys = object_key_map.get(metric.monitor_object_id)
            if monitor_object_keys is None and metric.monitor_object:
                monitor_object_keys = resolve_monitor_object_instance_id_keys(
                    metric.monitor_object.instance_id_keys,
                    level=metric.monitor_object.level,
                    object_name=metric.monitor_object.name,
                )
            resolved_keys = resolve_metric_instance_id_keys(metric.instance_id_keys, monitor_object_keys)
            if not resolved_keys:
                unresolved_metric_ids.append(metric.id)
                continue
            if resolved_keys != normalize_instance_id_keys(metric.instance_id_keys):
                metric.instance_id_keys = resolved_keys
                metric_updates.append(metric)

        if not dry_run:
            with transaction.atomic():
                if object_updates:
                    MonitorObject.objects.bulk_update(object_updates, ["instance_id_keys"])
                if metric_updates:
                    Metric.objects.bulk_update(metric_updates, ["instance_id_keys"])

        self.stdout.write(
            self.style.SUCCESS(
                "monitor_object updated=%s, metric updated=%s, unresolved_metrics=%s, dry_run=%s"
                % (len(object_updates), len(metric_updates), len(unresolved_metric_ids), dry_run)
            )
        )
        if unresolved_metric_ids:
            self.stdout.write(self.style.WARNING("unresolved metric ids: %s" % ", ".join(str(metric_id) for metric_id in unresolved_metric_ids)))
