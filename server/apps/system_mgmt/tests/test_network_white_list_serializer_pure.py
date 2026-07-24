"""NetworkWhiteListSerializer.validate_network / validate_domain 纯函数校验（无 DB）。"""

from unittest.mock import patch

import pytest
from rest_framework import serializers

from apps.system_mgmt.models import NetworkWhiteList
from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer


def test_validate_network_normalizes_bare_ip():
    s = NetworkWhiteListSerializer()
    assert s.validate_network("10.11.73.15") == "10.11.73.15/32"


def test_validate_network_normalizes_cidr():
    s = NetworkWhiteListSerializer()
    assert s.validate_network(" 10.11.73.0/24 ") == "10.11.73.0/24"


def test_validate_network_rejects_invalid():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("not-a-cidr")


def test_validate_network_rejects_supernet_v4():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("0.0.0.0/0")


def test_validate_network_rejects_supernet_v6():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_network("::/0")


# ---- validate_domain_name ----


def test_validate_domain_name_lowercases():
    """domain_name 自动转小写"""
    s = NetworkWhiteListSerializer()
    assert s.validate_domain_name("Corp-Wecom.Example.COM") == "corp-wecom.example.com"


def test_validate_domain_name_trims_whitespace():
    s = NetworkWhiteListSerializer()
    assert s.validate_domain_name("  corp-wecom.example.com  ") == "corp-wecom.example.com"


def test_validate_domain_name_rejects_empty():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name("")


def test_validate_domain_name_rejects_whitespace():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name("   ")


def test_validate_domain_name_rejects_at_sign():
    """防止 userinfo 绕过"""
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name("user@evil.com")


def test_validate_domain_name_rejects_slash():
    """防止 CIDR 格式混入 domain_name"""
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name("evil.com/webhook")


def test_validate_domain_name_rejects_leading_dot():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name(".evil.com")


def test_validate_domain_name_rejects_wildcard():
    s = NetworkWhiteListSerializer()
    with pytest.raises(serializers.ValidationError):
        s.validate_domain_name("*.example.com")


def test_is_build_in_is_read_only():
    """is_build_in 字段在 serializer 中不可写"""
    s = NetworkWhiteListSerializer()
    assert "is_build_in" in s.Meta.read_only_fields
    assert "domain" in s.Meta.read_only_fields


def test_validate_rejects_changing_network_entry_to_domain():
    """编辑网段条目时不能通过 PATCH 改成域名条目。"""
    instance = type("NetworkEntry", (), {"pk": 1, "network": "10.0.0.0/24", "domain_name": None})()
    serializer = NetworkWhiteListSerializer(instance=instance, partial=True)

    with patch.object(NetworkWhiteList.objects, "all") as all_entries:
        all_entries.return_value.filter.return_value.exclude.return_value.exists.return_value = False
        with pytest.raises(serializers.ValidationError, match="条目类型不可变更"):
            serializer.validate({"domain_name": "corp-wecom.example.com"})


def test_validate_rejects_changing_domain_entry_to_network():
    """编辑域名条目时不能通过 PATCH 改成网段条目。"""
    instance = type("DomainEntry", (), {"pk": 2, "network": "", "domain_name": "corp-wecom.example.com"})()
    serializer = NetworkWhiteListSerializer(instance=instance, partial=True)

    with patch.object(NetworkWhiteList.objects, "all") as all_entries:
        all_entries.return_value.filter.return_value.exclude.return_value.exists.return_value = False
        with pytest.raises(serializers.ValidationError, match="条目类型不可变更"):
            serializer.validate({"network": "10.0.0.0/24"})


def test_validate_rejects_empty_network_and_domain():
    serializer = NetworkWhiteListSerializer()
    with patch.object(NetworkWhiteList.objects, "all") as all_entries:
        all_entries.return_value.exists.return_value = False
        with pytest.raises(serializers.ValidationError):
            serializer.validate({"network": "", "domain_name": ""})


def test_remark_is_optional_and_allows_blank():
    field = NetworkWhiteListSerializer().fields["remark"]
    assert field.required is False
    assert field.allow_blank is True
