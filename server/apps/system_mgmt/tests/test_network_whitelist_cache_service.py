"""network_whitelist_cache 读取逻辑（测试环境用 DummyCache，故每次读 DB）。"""

import pytest


@pytest.mark.django_db
def test_get_network_whitelist_cidrs_returns_enabled_only():
    from apps.system_mgmt.models import NetworkWhiteList
    from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

    NetworkWhiteList.objects.create(network="10.11.73.0/24", enabled=True)
    NetworkWhiteList.objects.create(network="192.168.5.0/24", enabled=False)

    result = get_network_whitelist_cidrs()

    assert "10.11.73.0/24" in result
    assert "192.168.5.0/24" not in result


@pytest.mark.django_db
def test_get_network_whitelist_cidrs_empty_when_no_rows():
    from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs

    assert get_network_whitelist_cidrs() == []
