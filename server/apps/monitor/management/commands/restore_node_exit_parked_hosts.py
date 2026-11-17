from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.monitor.models import CollectConfig, MonitorInstance


class Command(BaseCommand):
    help = "把节点删除遗留的软删主机实例恢复为停采待处理（默认 dry-run，--apply 落库）"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="落库（默认只输出报告）")

    def handle(self, *args, **options):
        apply = options["apply"]
        candidates = list(
            MonitorInstance.objects.filter(is_deleted=True, is_active=False)
            .annotate(config_count=Count("collectconfig"))
            .filter(config_count__gt=0)
            .order_by("id")
        )
        live_index = _live_instance_index()
        plans = [(_conflict_id(instance, live_index), instance) for instance in candidates]
        restorable_ids = [instance.id for conflict_id, instance in plans if conflict_id is None]
        if apply and restorable_ids:
            with transaction.atomic():
                MonitorInstance.objects.filter(id__in=restorable_ids).update(is_deleted=False, is_active=True)
                CollectConfig.objects.filter(monitor_instance_id__in=restorable_ids).update(executor_node_removed=True)
        for conflict_id, instance in plans:
            if conflict_id is not None:
                verdict = f"conflict:{conflict_id}"
            elif apply:
                verdict = "restored"
            else:
                verdict = "restorable"
            self.stdout.write(f"{instance.id}\t{instance.name}\t{instance.config_count}\t{verdict}")
        count_label = "restored" if apply else "restorable"
        dry_run = "false" if apply else "true"
        self.stdout.write(
            f"summary\tcandidates={len(plans)}\t{count_label}={len(restorable_ids)}\t"
            f"conflicts={len(plans) - len(restorable_ids)}\tdry-run={dry_run}"
        )


def _live_instance_index():
    """(monitor_object_id, ip, cloud_region_id) -> 最小实例 ID。ip 为空的活实例不参与冲突。"""
    index = {}
    rows = MonitorInstance.objects.filter(is_deleted=False).order_by("id").values_list("id", "monitor_object_id", "ip", "cloud_region_id")
    for instance_id, object_id, ip, region_id in rows:
        if not ip:
            continue
        index.setdefault((object_id, ip, region_id), instance_id)
    return index


def _conflict_id(instance, live_index):
    if not instance.ip:
        return None
    return live_index.get((instance.monitor_object_id, instance.ip, instance.cloud_region_id))
