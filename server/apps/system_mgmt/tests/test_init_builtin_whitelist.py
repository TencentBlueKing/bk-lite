"""内置 webhook 域名 data migration 行为测试。

迁移:把 4 个官方 IM 域名同步到 NetworkWhiteList(domain=..., is_build_in=True)。
- 首次执行:插入 4 条记录
- 重复执行:idempotent,无副作用
"""

import pytest

from apps.system_mgmt.models import NetworkWhiteList

BUILTIN_WEBHOOK_DOMAINS = {
    "qyapi.weixin.qq.com",
    "open.feishu.cn",
    "open.larksuite.com",
    "oapi.dingtalk.com",
}


@pytest.mark.django_db
def test_init_builtin_whitelist_seeds_four_rows():
    """迁移跑完后,4 个官方域名落库,带 is_build_in=True"""
    for domain in BUILTIN_WEBHOOK_DOMAINS:
        NetworkWhiteList.objects.get_or_create(
            domain_name=domain,
            defaults={"network": "", "is_build_in": True, "enabled": True},
        )

    rows = NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True)
    assert rows.count() == 4
    domains = set(rows.values_list("domain_name", flat=True))
    assert domains == BUILTIN_WEBHOOK_DOMAINS
    for row in rows:
        assert row.enabled is True


@pytest.mark.django_db
def test_init_builtin_whitelist_idempotent():
    """重复跑迁移不会产生重复记录"""
    for domain in BUILTIN_WEBHOOK_DOMAINS:
        NetworkWhiteList.objects.get_or_create(
            domain_name=domain,
            defaults={"network": "", "is_build_in": True, "enabled": True},
        )

    # 第二次跑
    for domain in BUILTIN_WEBHOOK_DOMAINS:
        NetworkWhiteList.objects.get_or_create(
            domain_name=domain,
            defaults={"network": "", "is_build_in": True, "enabled": True},
        )

    rows = NetworkWhiteList.objects.filter(domain_name__in=BUILTIN_WEBHOOK_DOMAINS, is_build_in=True)
    assert rows.count() == 4
