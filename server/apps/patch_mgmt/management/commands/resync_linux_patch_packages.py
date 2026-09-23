import argparse
import json

from django.core.management.base import BaseCommand, CommandError

from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService


class Command(BaseCommand):
    help = (
        "升级后对空 packages 存量 Linux 公告做有界运行期重同步。"
        "只补齐空快照，不拉全量建档、不把已入库候选当成跳过理由。"
        "默认 dry-run 不写库；确认后使用 --no-dry-run。"
        "可用 --source-id 限定内置或普通 Linux 源，--limit / --after-id 分页。"
        "不要从 batch_init、apps.ready 或 migration 调用本命令。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="默认只报告不写库；加 --no-dry-run 才写库",
        )
        parser.add_argument("--limit", type=int, default=100, help="本批最多处理 1-1000 条")
        parser.add_argument("--source-id", type=int, default=None, help="只处理指定 Linux 源（内置或普通）")
        parser.add_argument("--after-id", type=int, default=0, help="只处理 patch_id 大于该值的记录")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit 必须在 1 到 1000 之间")
        if options["after_id"] < 0:
            raise CommandError("--after-id 不能小于 0")
        try:
            result = SourceSyncService.resync_empty_linux_packages(
                source_id=options["source_id"],
                limit=options["limit"],
                dry_run=options["dry_run"],
                after_id=options["after_id"],
            )
        except SourceSyncError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
