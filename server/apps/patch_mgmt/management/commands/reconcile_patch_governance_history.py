import json

from django.core.management.base import BaseCommand, CommandError

from apps.patch_mgmt.services.governance_convergence import reconcile_stale_history


class Command(BaseCommand):
    help = "有界、幂等地收敛历史陈旧补丁治理记录；不会自动重跑"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只列出候选，不写数据库")
        parser.add_argument("--limit", type=int, default=100, help="本批最多处理 1-1000 条")
        parser.add_argument("--after-id", type=int, default=0, help="只处理 ID 大于该值的记录")
        parser.add_argument("--before-id", type=int, default=None, help="只处理 ID 小于该值的记录")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit 必须在 1 到 1000 之间")
        if options["after_id"] < 0:
            raise CommandError("--after-id 不能小于 0")
        if options["before_id"] is not None and options["before_id"] <= 0:
            raise CommandError("--before-id 必须大于 0")
        result = reconcile_stale_history(
            dry_run=options["dry_run"],
            limit=options["limit"],
            after_id=options["after_id"],
            before_id=options["before_id"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
