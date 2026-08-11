import json

from django.core.management.base import BaseCommand, CommandError

from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.utils.log_group import LogGroupQueryBuilder


class Command(BaseCommand):
    help = "只读盘点日志分组规则 mode；不输出完整规则值"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500, help="稳定主键分页的批大小")
        parser.add_argument("--format", choices=("text", "jsonl"), default="text", help="输出格式")
        parser.add_argument("--fail-on-invalid", action="store_true", help="发现需处理规则时以非零状态退出")
        parser.add_argument("--fail-on-uncovered", action="store_true", help="发现严格模式未覆盖规则时以非零状态退出")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size <= 0:
            raise CommandError("batch-size 必须是正整数")

        output_format = options["format"]
        summary = {
            LogGroupQueryBuilder.MODE_VALID: 0,
            LogGroupQueryBuilder.MODE_LEGACY_OR: 0,
            LogGroupQueryBuilder.MODE_INVALID: 0,
            "uncovered": 0,
        }
        last_id = None
        legacy_or_group_ids = LogGroupQueryBuilder._configured_legacy_or_group_ids()

        while True:
            queryset = LogGroup.objects.order_by("id")
            if last_id is not None:
                queryset = queryset.filter(id__gt=last_id)
            groups = list(queryset.values("id", "name", "rule", "created_by")[:batch_size])
            if not groups:
                break

            group_ids = [group["id"] for group in groups]
            organizations_by_group = {group_id: [] for group_id in group_ids}
            organization_rows = (
                LogGroupOrganization.objects.filter(log_group_id__in=group_ids)
                .order_by("log_group_id", "organization")
                .values_list("log_group_id", "organization")
            )
            for group_id, organization in organization_rows:
                organizations_by_group[group_id].append(organization)

            for group in groups:
                classification, _ = LogGroupQueryBuilder.classify_rule(group["rule"])
                summary[classification] += 1
                if classification == LogGroupQueryBuilder.MODE_VALID:
                    continue
                covered_by_legacy_or = classification == LogGroupQueryBuilder.MODE_LEGACY_OR and group["id"] in legacy_or_group_ids
                if not covered_by_legacy_or:
                    summary["uncovered"] += 1
                self._write_record(
                    {
                        "type": "finding",
                        "classification": classification,
                        "covered_by_legacy_or": covered_by_legacy_or,
                        "id": group["id"],
                        "name": group["name"],
                        "created_by": group["created_by"],
                        "organizations": organizations_by_group[group["id"]],
                    },
                    output_format,
                )

            last_id = groups[-1]["id"]

        summary_record = {"type": "summary", **summary}
        self._write_record(summary_record, output_format)

        finding_count = summary[LogGroupQueryBuilder.MODE_LEGACY_OR] + summary[LogGroupQueryBuilder.MODE_INVALID]
        if options["fail_on_invalid"] and finding_count:
            raise CommandError(
                "发现需处理的日志分组规则："
                f"legacy_or={summary[LogGroupQueryBuilder.MODE_LEGACY_OR]}, invalid={summary[LogGroupQueryBuilder.MODE_INVALID]}"
            )
        if options["fail_on_uncovered"] and summary["uncovered"]:
            raise CommandError(f"发现严格模式未覆盖的日志分组规则：uncovered={summary['uncovered']}")

    def _write_record(self, record, output_format):
        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if output_format == "jsonl":
            self.stdout.write(serialized)
            return
        if record["type"] == "finding":
            self.stdout.write(f"finding {serialized}")
        else:
            self.stdout.write(f"summary {serialized}")
