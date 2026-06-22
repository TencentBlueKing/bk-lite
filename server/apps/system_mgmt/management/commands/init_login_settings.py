from django.core.management import BaseCommand
from django.db import transaction

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    SystemSettings,
)
from apps.system_mgmt.models.login_module import LoginModule


BUILTIN_PLATFORM_PROVIDER_KEY = "bk_lite_builtin"
BUILTIN_PLATFORM_INSTANCE_NAME = "平台账号内建体系"
BUILTIN_PLATFORM_INSTANCE_DESCRIPTION = "系统内建平台账号体系"
BUILTIN_PLATFORM_BINDING_NAME = "平台账号密码登录"
BUILTIN_PLATFORM_BINDING_DESCRIPTION = "系统内建平台账号密码登录方式"
BUILTIN_PLATFORM_BINDING_EXTERNAL_FIELD = "username"
BUILTIN_PLATFORM_BINDING_ORDER = 1


def normalize_login_auth_binding_orders():
    ordered_bindings = list(LoginAuthBinding.objects.order_by("order", "id"))
    for index, binding in enumerate(ordered_bindings, start=1):
        if binding.order != index:
            LoginAuthBinding.objects.filter(id=binding.id).update(order=index)


def init_builtin_platform_login_auth():
    with transaction.atomic():
        instance, _ = IntegrationInstance.objects.get_or_create(
            provider_key=BUILTIN_PLATFORM_PROVIDER_KEY,
            defaults={
                "name": BUILTIN_PLATFORM_INSTANCE_NAME,
                "config": {},
                "status": IntegrationInstanceStatusChoices.READY,
                "capability_status": {"login_auth": IntegrationInstanceStatusChoices.READY},
                "enabled": True,
                "description": BUILTIN_PLATFORM_INSTANCE_DESCRIPTION,
            },
        )

        LoginAuthBinding.objects.get_or_create(
            integration_instance=instance,
            defaults={
                "name": BUILTIN_PLATFORM_BINDING_NAME,
                "description": BUILTIN_PLATFORM_BINDING_DESCRIPTION,
                "order": BUILTIN_PLATFORM_BINDING_ORDER,
                "enabled": True,
                "external_field": BUILTIN_PLATFORM_BINDING_EXTERNAL_FIELD,
                "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
                "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.DENY,
                "default_group_name": "",
            },
        )
        normalize_login_auth_binding_orders()


class Command(BaseCommand):
    help = "初始登陆化设置"

    def handle(self, *args, **options):
        LoginModule.objects.get_or_create(
            is_build_in=True,
            source_type="wechat",
            defaults={
                "name": "微信开放平台",
                "app_id": "",
                "app_secret": "",
                "other_config": {
                    "redirect_uri": "",
                    "callback_url": "",
                },
                "enabled": True,
            },
        )

        SystemSettings.objects.get_or_create(key="login_expired_time", defaults={"value": "24"})
        SystemSettings.objects.get_or_create(key="enable_otp", defaults={"value": "0"})
        SystemSettings.objects.get_or_create(key="portal_name", defaults={"value": "BlueKing Lite"})
        SystemSettings.objects.get_or_create(key="portal_logo_url", defaults={"value": ""})
        SystemSettings.objects.get_or_create(key="portal_favicon_url", defaults={"value": ""})
        SystemSettings.objects.get_or_create(key="watermark_enabled", defaults={"value": "0"})
        SystemSettings.objects.get_or_create(key="watermark_text", defaults={"value": "BlueKing Lite · ${username} · ${date}"})
        init_builtin_platform_login_auth()
