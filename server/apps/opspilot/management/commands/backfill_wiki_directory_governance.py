"""存量知识库目录/generation 基线回填命令。

示例::

    python manage.py backfill_wiki_directory_governance --dry-run
    python manage.py backfill_wiki_directory_governance --knowledge-base-ids 12 34
    python manage.py backfill_wiki_directory_governance --knowledge-base-ids 12 --batch-size 20
"""

from django.core.management.base import BaseCommand, CommandError

from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase
from apps.opspilot.services.wiki.directory_backfill_service import (
    BackfillPreflightError,
    baseline_already_complete,
    begin_backfill,
    complete_backfill,
    preflight_legacy_knowledge_base,
    repair_missing_current_versions,
)

# 测试与外部脚本兼容：从命令模块导入 _begin_backfill。
_begin_backfill = begin_backfill


class Command(BaseCommand):
    help = "为存量 Wiki 知识库补齐 active structure revision 与 active generation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--knowledge-base-ids",
            nargs="*",
            type=int,
            default=None,
            dest="knowledge_base_ids",
            help="仅处理指定知识库；缺省处理全部",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            dest="batch_size",
            help="每批写入的页面数量",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="只检查不写库",
        )
        parser.add_argument(
            "--operator",
            type=str,
            default="system",
            help="回填操作人标识",
        )

    def handle(self, *args, **options):
        knowledge_base_ids = options.get("knowledge_base_ids")
        queryset = WikiKnowledgeBase.objects.all().order_by("id")
        if knowledge_base_ids is not None:
            queryset = queryset.filter(pk__in=knowledge_base_ids)
        knowledge_bases = list(queryset)
        if knowledge_base_ids is not None:
            found = {item.pk for item in knowledge_bases}
            missing = [kb_id for kb_id in knowledge_base_ids if kb_id not in found]
            if missing:
                raise CommandError("failed_kb_ids=" + ",".join(str(item) for item in missing))

        dry_run = bool(options.get("dry_run"))
        batch_size = max(int(options.get("batch_size") or 50), 1)
        operator = options.get("operator") or "system"
        failed = []

        for knowledge_base in knowledge_bases:
            label = f"kb={knowledge_base.pk} name={knowledge_base.name}"
            try:
                orphan_qs = KnowledgePage.objects.filter(
                    knowledge_base=knowledge_base,
                    current_version_id__isnull=True,
                )
                orphan_count = orphan_qs.count()

                if baseline_already_complete(knowledge_base):
                    if dry_run:
                        self.stdout.write(f"[DRY-RUN] {label} baseline 已完成 " f"would_repair_current_version_pages={orphan_count}")
                        continue
                    repaired = repair_missing_current_versions(knowledge_base.pk)
                    still_missing = list(orphan_qs.order_by("id").values_list("id", flat=True)[:20])
                    if still_missing:
                        raise BackfillPreflightError("page_current_version_missing page_ids=" + ",".join(str(item) for item in still_missing))
                    self.stdout.write(f"{label} baseline 已完成 repaired_current_version_pages={repaired}")
                    continue

                if dry_run:
                    preflight_legacy_knowledge_base(knowledge_base.pk)
                    page_count = knowledge_base.pages.count()
                    self.stdout.write(
                        f"[DRY-RUN] {label} would_backfill pages={page_count} "
                        f"state={knowledge_base.directory_migration_state} "
                        f"would_repair_current_version_pages={orphan_count}"
                    )
                    continue

                if knowledge_base.directory_migration_state == "legacy":
                    preflight_legacy_knowledge_base(knowledge_base.pk)

                repaired = repair_missing_current_versions(knowledge_base.pk)
                context = begin_backfill(knowledge_base.pk, operator=operator)
                complete_backfill(context, batch_size=batch_size, operator=operator)
                knowledge_base.refresh_from_db()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{label} backfill ok generation={knowledge_base.active_generation_id} "
                        f"state={knowledge_base.directory_migration_state} "
                        f"repaired_current_version_pages={repaired}"
                    )
                )
            except BackfillPreflightError as error:
                failed.append(str(knowledge_base.pk))
                self.stderr.write(f"{label} {error.message}")
            except Exception as error:  # noqa: BLE001 - 命令汇总失败集
                failed.append(str(knowledge_base.pk))
                self.stderr.write(f"{label} unexpected_error={error}")

        if failed:
            raise CommandError("failed_kb_ids=" + ",".join(failed))
