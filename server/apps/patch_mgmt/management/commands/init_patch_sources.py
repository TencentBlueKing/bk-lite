from django.core.management.base import BaseCommand

from apps.patch_mgmt.services.builtin_source_service import initialize_builtin_patch_sources


class Command(BaseCommand):
    help = "幂等初始化系统内置 Linux 补丁源（不访问外部网络）"

    def handle(self, *args, **options):
        created, existing = initialize_builtin_patch_sources()
        self.stdout.write(
            self.style.SUCCESS(
                f"内置补丁源初始化完成（新建: {created}，已存在: {existing}）"
            )
        )
