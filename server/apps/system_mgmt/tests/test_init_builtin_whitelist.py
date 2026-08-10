"""内置 webhook 域名种子：0041 写入、0044 移除。"""

from importlib import import_module

import pytest
from django.apps import apps as django_apps

from apps.system_mgmt.models import NetworkWhiteList

BUILTIN_WEBHOOK_DOMAINS = {
    "qyapi.weixin.qq.com",
    "open.feishu.cn",
    "open.larksuite.com",
    "oapi.dingtalk.com",
}
SEED_MIGRATION = import_module("apps.system_mgmt.migrations.0041_networkwhitelist_domain_build_in")
REMOVE_MIGRATION = import_module("apps.system_mgmt.migrations.0044_remove_builtin_webhook_domains")


@pytest.mark.django_db
def test_init_builtin_whitelist_seeds_four_rows():
    NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS).delete()

    SEED_MIGRATION.seed_builtin_webhook_domains(django_apps, None)

    rows = NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True)
    assert rows.count() == 4
    assert set(rows.values_list("domain_name", flat=True)) == BUILTIN_WEBHOOK_DOMAINS


@pytest.mark.django_db
def test_remove_builtin_webhook_domains_clears_seed_rows():
    NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS).delete()
    SEED_MIGRATION.seed_builtin_webhook_domains(django_apps, None)
    # 用户自建同名域名（非 build_in）应保留
    NetworkWhiteList.objects.create(
        domain_name="custom.example.com",
        network="",
        is_build_in=False,
        enabled=True,
        created_by="t",
        updated_by="t",
    )

    REMOVE_MIGRATION.remove_builtin_webhook_domains(django_apps, None)

    assert NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True).count() == 0
    assert NetworkWhiteList.objects.filter(domain_name="custom.example.com").exists()
