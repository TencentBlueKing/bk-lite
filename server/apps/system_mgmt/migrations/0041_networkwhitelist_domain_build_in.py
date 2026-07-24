"""NetworkWhiteList: domain + is_build_in 字段 + 内置 webhook 域名初始化。

依赖:0034_networkwhitelist(初始表)
"""

import django.db.models.deletion
from django.db import migrations, models

# 官方 IM webhook 域名 — 内置白名单,viewset 禁止修改/删除
BUILTIN_WEBHOOK_DOMAINS = [
    "qyapi.weixin.qq.com",
    "open.feishu.cn",
    "open.larksuite.com",
    "oapi.dingtalk.com",
]


def seed_builtin_webhook_domains(apps, schema_editor):
    """同步内置域名到 NetworkWhiteList;已存在则跳过(idempotent)。"""
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


def unseed_builtin_webhook_domains(apps, schema_editor):
    """回滚:仅删除 is_build_in=True 且 domain_name 命中的行,避免误删用户条目"""
    NetworkWhiteList = apps.get_model("system_mgmt", "NetworkWhiteList")
    NetworkWhiteList.objects.filter(
        domain_name__in=BUILTIN_WEBHOOK_DOMAINS,
        is_build_in=True,
        network="",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0040_usersyncsource_platform_config"),
    ]

    operations = [
        # 1. 新增字段;network 改成可空(原本 unique=True,现改 blank=True)
        migrations.AlterField(
            model_name="networkwhitelist",
            name="network",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="networkwhitelist",
            name="domain_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                db_index=True,
                help_text="私有化部署域名(如 corp-wecom.example.com)。与 network 二选一。",
            ),
        ),
        migrations.AddField(
            model_name="networkwhitelist",
            name="is_build_in",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name="networkwhitelist",
            name="remark",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        # 2. 同步内置 webhook 域名
        migrations.RunPython(seed_builtin_webhook_domains, unseed_builtin_webhook_domains),
    ]
