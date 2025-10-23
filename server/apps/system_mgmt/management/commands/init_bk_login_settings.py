from django.core.management import BaseCommand

from apps.system_mgmt.models import Role
from apps.system_mgmt.models.login_module import LoginModule


class Command(BaseCommand):
    help = "初始登陆化设置"

    def handle(self, *args, **options):
        role = Role.objects.get(app="opspilot", name="normal")
        LoginModule.objects.get_or_create(
            name="蓝鲸平台",
            source_type="bk_login",
            is_build_in=True,
            defaults={
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
