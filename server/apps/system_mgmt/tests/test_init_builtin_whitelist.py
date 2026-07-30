"""内置 webhook 域名数据迁移行为测试。"""

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
MIGRATION = import_module("apps.system_mgmt.migrations.0041_networkwhitelist_domain_build_in")


def _run_seed_migration():
    MIGRATION.seed_builtin_webhook_domains(django_apps, None)


@pytest.mark.django_db
def test_init_builtin_whitelist_seeds_four_rows():
    NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS).delete()

    _run_seed_migration()

    rows = NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True)
    assert rows.count() == 4
    assert set(rows.values_list("domain_name", flat=True)) == BUILTIN_WEBHOOK_DOMAINS
    assert all(row.enabled for row in rows)


@pytest.mark.django_db
def test_init_builtin_whitelist_idempotent():
    NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS).delete()

    _run_seed_migration()
    _run_seed_migration()

    rows = NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True)
    assert rows.count() == 4
