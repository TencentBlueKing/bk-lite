import logging

from django.core.management import BaseCommand
from django.db import transaction

from apps.system_mgmt.models import App, CustomMenuGroup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "初始化自定义菜单组"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("开始初始化自定义菜单组..."))

        try:
            with transaction.atomic():
                # 获取所有内置应用
                builtin_apps = App.objects.filter(is_build_in=True)
                self.stdout.write(f"找到 {builtin_apps.count()} 个内置应用")

                for app in builtin_apps:
                    self.stdout.write(f"\n处理应用: {app.name} ({app.display_name})")

                    # 创建或更新菜单组
                    menu_group, created = CustomMenuGroup.objects.get_or_create(
                        app=app.name,
                        display_name="默认菜单",
                        defaults={
                            "is_enabled": True,
                            "is_build_in": True,
                            "description": f"{app.display_name}的默认菜单配置",
                            "created_by": "system",
                            "updated_by": "system",
                            "menus": [],
                        },
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ 创建菜单组: {menu_group.display_name} (已启用，内置)"))
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ 更新菜单组: {menu_group.display_name} (is_enabled={menu_group.is_enabled}, is_build_in={menu_group.is_build_in})"
                            )
                        )

                self.stdout.write(self.style.SUCCESS("\n✓ 自定义菜单组初始化完成！"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ 初始化失败: {str(e)}"))
            logger.exception("初始化自定义菜单组时发生错误")
            raise
