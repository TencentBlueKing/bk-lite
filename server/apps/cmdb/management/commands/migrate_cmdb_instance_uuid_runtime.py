"""手工执行 CMDB/OA 实例 UUID 清洗。

    python manage.py migrate_cmdb_instance_uuid_runtime
    python manage.py migrate_cmdb_instance_uuid_runtime --dry-run
    python manage.py migrate_cmdb_instance_uuid_runtime --apply
    python manage.py migrate_cmdb_instance_uuid_runtime --verify
"""

from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.tasks.uuid_migration import run_uuid_runtime_migration


class Command(BaseCommand):
    help = (
        "手工执行 CMDB/OA 实例 UUID 清洗。默认 apply 后再 verify。"
        "不再由 Celery Beat 周期调度；升级后 batch_init 会删除历史周期任务。"
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="只生成清洗统计，不写入")
        mode.add_argument("--apply", action="store_true", help="只执行幂等清洗，不 verify")
        mode.add_argument("--verify", action="store_true", help="只读验证；存在待清洗项时非零退出")

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        apply_only = bool(options.get("apply"))
        verify_only = bool(options.get("verify"))
        if dry_run:
            result = run_uuid_runtime_migration(dry_run=True, apply=False, verify=False)
        elif apply_only:
            result = run_uuid_runtime_migration(apply=True, verify=False)
        elif verify_only:
            result = run_uuid_runtime_migration(apply=False, verify=True)
        else:
            result = run_uuid_runtime_migration()

        status = result.get("status")
        if status == "locked":
            raise CommandError("UUID 清洗正在执行，跳过本轮")
        if status == "retry":
            raise CommandError(f"UUID 清洗未完成: {result.get('reason')}")
        self.stdout.write(self.style.SUCCESS(str(result)))
