from django.core.management.base import BaseCommand
from django.db import connections, router

from apps.log.models.policy import AlertSnapshot
from apps.monitor.models.monitor_policy import MonitorAlertMetricSnapshot


class Command(BaseCommand):
    help = "清理 monitor/log 快照字段在 MinIO 中遗留的历史孤儿对象"

    TARGETS = {
        "monitor": {
            "label": "monitor snapshot",
            "model": MonitorAlertMetricSnapshot,
            "field_name": "snapshots",
        },
        "log": {
            "label": "log snapshot",
            "model": AlertSnapshot,
            "field_name": "snapshots",
        },
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--target",
            choices=["monitor", "log", "all"],
            default="all",
            help="选择要清理的快照类型，默认 all",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="执行实际删除；默认仅 dry-run 统计",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="展示前 N 个孤儿对象样本，默认 20",
        )

    def handle(self, *args, **options):
        target = options["target"]
        should_delete = options["delete"]
        sample_limit = max(options["limit"], 0)

        target_keys = list(self.TARGETS.keys()) if target == "all" else [target]
        summaries = []

        for target_key in target_keys:
            config = self.TARGETS[target_key]
            summary = self._scan_target(config, should_delete=should_delete, sample_limit=sample_limit)
            summaries.append(summary)
            self._print_summary(summary, should_delete=should_delete)

        total_orphans = sum(item["orphan_count"] for item in summaries)
        total_bytes = sum(item["orphan_bytes"] for item in summaries)
        deleted_count = sum(item["deleted_count"] for item in summaries)

        footer = (
            f"完成 {'删除' if should_delete else '扫描'}: orphan_count={total_orphans}, orphan_bytes={total_bytes}, deleted_count={deleted_count}"
        )
        self.stdout.write(self.style.SUCCESS(footer))

    def _scan_target(self, config, *, should_delete, sample_limit):
        model = config["model"]
        field_name = config["field_name"]
        field = model._meta.get_field(field_name)
        storage = field.storage
        using = router.db_for_read(model)
        live_paths = self._fetch_live_paths(model, field, using)
        prefix = f"{model.__name__.lower()}_"

        summary = {
            "label": config["label"],
            "bucket": storage.bucket,
            "prefix": prefix,
            "live_count": len(live_paths),
            "scanned_count": 0,
            "orphan_count": 0,
            "orphan_bytes": 0,
            "deleted_count": 0,
            "samples": [],
        }

        for obj in storage.client.list_objects(storage.bucket, recursive=True):
            object_name = obj.object_name
            if not self._matches_prefix(object_name, prefix):
                continue

            summary["scanned_count"] += 1
            if object_name in live_paths:
                continue

            summary["orphan_count"] += 1
            summary["orphan_bytes"] += obj.size

            if len(summary["samples"]) < sample_limit:
                summary["samples"].append({"path": object_name, "size": obj.size})

            if should_delete:
                storage.delete(object_name)
                summary["deleted_count"] += 1

        return summary

    def _fetch_live_paths(self, model, field, using):
        connection = connections[using]
        meta = model._meta
        quote_name = connection.ops.quote_name
        query = f"SELECT {quote_name(field.column)} FROM {quote_name(meta.db_table)}"
        live_paths = set()

        with connection.cursor() as cursor:
            cursor.execute(query)
            for row in cursor.fetchall():
                value = row[0]
                if isinstance(value, str) and value:
                    live_paths.add(value)

        return live_paths

    @staticmethod
    def _matches_prefix(object_name, prefix):
        return object_name.rsplit("/", 1)[-1].startswith(prefix)

    def _print_summary(self, summary, *, should_delete):
        action = "DELETE" if should_delete else "DRY-RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{action}] {summary['label']} bucket={summary['bucket']} prefix={summary['prefix']} "
                f"live={summary['live_count']} scanned={summary['scanned_count']} "
                f"orphans={summary['orphan_count']} orphan_bytes={summary['orphan_bytes']} "
                f"deleted={summary['deleted_count']}"
            )
        )

        for sample in summary["samples"]:
            self.stdout.write(f"  sample orphan: {sample['path']} ({sample['size']} bytes)")
