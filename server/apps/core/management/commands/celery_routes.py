import json

from celery import current_app
from django.core.management.base import BaseCommand, CommandError

from apps.core.celery_runtime import inspect_registry
from apps.core.celery_runtime.periodic_routes import migrate_routes, restore_routes


class Command(BaseCommand):
    help = "检查/调整明确名单的 Beat 路由；默认 dry-run，不修改业务调度"

    def add_arguments(self, parser):
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--ids", nargs="+", type=int)
        action.add_argument("--restore", metavar="SNAPSHOT")
        parser.add_argument("--snapshot", help="应用时必须提供不存在的新快照文件")
        parser.add_argument("--apply", action="store_true", help="显式执行，否则只读预览")

    def handle(self, *args, **options):
        try:
            if options["restore"]:
                changes = restore_routes(options["restore"], apply=options["apply"])
            else:
                registered = inspect_registry(current_app)
                changes = migrate_routes(options["ids"], set(registered), options["snapshot"], options["apply"])
            self.stdout.write(json.dumps({"applied": options["apply"], "changes": changes}, ensure_ascii=False, indent=2))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise CommandError(f"路由操作失败：{type(exc).__name__}；请核对名单、快照及当前路由") from exc
