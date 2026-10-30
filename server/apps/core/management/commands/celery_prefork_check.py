import json

from celery import current_app
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.celery_runtime import inspect_registry
from apps.core.celery_runtime.diagnostics import inactive_limit_declarations, prefork_issues


class Command(BaseCommand):
    help = "验证执行池兼容策略，保留任务声明但不隐式启用原 threads 不支持的超时/回收"

    def handle(self, *args, **options):
        if not getattr(settings, "IS_USE_CELERY", False):
            return
        inspect_registry(current_app)
        issues = prefork_issues(current_app)
        self.stdout.write(
            json.dumps(
                {"prefork_semantics_issues": issues, "inactive_limit_declarations": inactive_limit_declarations(current_app)},
                ensure_ascii=False,
                indent=2,
            )
        )
        if issues:
            raise CommandError("执行池未使用 threads 行为兼容层，请使用统一启动配置，不要修改业务任务声明")
