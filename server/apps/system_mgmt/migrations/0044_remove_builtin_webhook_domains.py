"""移除公有云官方 IM webhook 内置域名种子。

公网域名在统一 SSRF 语义下默认放行，不再需要 is_build_in 域名行。
"""

from django.db import migrations

BUILTIN_WEBHOOK_DOMAINS = [
    "qyapi.weixin.qq.com",
    "open.feishu.cn",
    "open.larksuite.com",
    "oapi.dingtalk.com",
]


def remove_builtin_webhook_domains(apps, schema_editor):
    NetworkWhiteList = apps.get_model("system_mgmt", "NetworkWhiteList")
    NetworkWhiteList.objects.filter(
        domain_name__in=BUILTIN_WEBHOOK_DOMAINS,
        is_build_in=True,
        network="",
    ).delete()


def restore_builtin_webhook_domains(apps, schema_editor):
    NetworkWhiteList = apps.get_model("system_mgmt", "NetworkWhiteList")
    for domain_name in BUILTIN_WEBHOOK_DOMAINS:
        NetworkWhiteList.objects.get_or_create(
            domain_name=domain_name,
            defaults={
                "network": "",
                "is_build_in": True,
                "enabled": True,
                "remark": "官方 IM webhook 域名（内置）",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0043_networkwhitelist_forbid_universal_cidr"),
    ]

    operations = [
        migrations.RunPython(remove_builtin_webhook_domains, restore_builtin_webhook_domains),
    ]
