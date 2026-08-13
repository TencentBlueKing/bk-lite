from django.core.management import BaseCommand

from apps.system_mgmt.models import Role
from apps.system_mgmt.models.login_module import LoginModule


class Command(BaseCommand):
    """初始化遗留 bk_login 配置。

    认证源管理入口已关闭。该默认记录仅兼容已部署实例，后续由集成中心
    Provider 的 ``login_auth`` capability 替代；禁止基于此命令扩展新功能。
    """

    help = "初始登陆化设置"

    def handle(self, *args, **options):
        role = Role.objects.get(app="opspilot", name="normal")
        LoginModule.objects.get_or_create(
            name="蓝鲸平台",
            source_type="bk_login",
            defaults={
                "is_build_in": True,
                "other_config": {
                    "sync": False,
                    "app_id": "weops_saas",
                    "bk_url": "",
                    "app_token": "",
                    "sync_time": "00:00",
                    "root_group": "蓝鲸",
                    "default_roles": [role.id],
                },
                "enabled": False,
            },
        )
