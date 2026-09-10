from django.core.management import BaseCommand

from apps.cmdb.services.port_fingerprint import sync_builtin_port_fingerprints


class Command(BaseCommand):
    help = "同步内置数据库端口指纹（3306/5432/1433）"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="仅统计，不写数据库")

    def handle(self, *args, **options):
        result = sync_builtin_port_fingerprints(dry_run=bool(options["dry_run"]))
        prefix = "DRY-RUN " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}端口指纹同步完成: 新增={result['created']}, " f"未变化={result['unchanged']}, 用户占用={result['skipped_user']}")
        )
