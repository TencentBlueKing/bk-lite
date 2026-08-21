from django.core.management import BaseCommand

from apps.core.utils.permission_cache import clear_all_permission_cache
from apps.patch_mgmt.services.patch_settings_split_migration import migrate_patch_settings_split, reverse_patch_settings_split_custom_menus


class Command(BaseCommand):
    help = "迁移或回滚补丁设置菜单拆分的存量授权与自定义菜单"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reverse",
            action="store_true",
            help="回滚自定义菜单为旧设置叶子节点（部署旧版本前执行）",
        )

    def handle(self, *args, **options):
        if options["reverse"]:
            result = reverse_patch_settings_split_custom_menus()
            action = "回滚"
        else:
            result = migrate_patch_settings_split()
            action = "迁移"
            if result.roles_updated:
                clear_all_permission_cache()

        self.stdout.write(self.style.SUCCESS(f"补丁设置菜单{action}完成：角色 {result.roles_updated} 个，" f"自定义菜单 {result.custom_menu_groups_updated} 个"))
