"""NetworkWhiteListSerializer.validate_network / validate_domain 纯函数校验（无 DB）。"""

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
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


@pytest.mark.django_db
@pytest.mark.parametrize("network", ["0.0.0.0/0", "::/0"])
def test_model_rejects_forbidden_supernets(network):
    entry = NetworkWhiteList(network=network, domain_name="", created_by="review", updated_by="review")

    with pytest.raises(DjangoValidationError):
        entry.full_clean()
    with pytest.raises(DjangoValidationError):
        entry.save()


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


def test_validate_domain_name_accepts_prefix_wildcard():
    s = NetworkWhiteListSerializer()
    assert s.validate_domain_name("*.Example.COM") == "*.example.com"


def test_validate_domain_name_rejects_invalid_wildcard_forms():
    s = NetworkWhiteListSerializer()
    for bad in ("*", "*.com", "*example.com", "foo.*.com", "**.example.com", "*.*"):
        with pytest.raises(serializers.ValidationError):
            s.validate_domain_name(bad)


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
        with pytest.raises(serializers.ValidationError, match="不可变更|cannot be changed"):
            serializer.validate({"domain_name": "corp-wecom.example.com"})


def test_validate_rejects_changing_domain_entry_to_network():
    """编辑域名条目时不能通过 PATCH 改成网段条目。"""
    instance = type("DomainEntry", (), {"pk": 2, "network": "", "domain_name": "corp-wecom.example.com"})()
    serializer = NetworkWhiteListSerializer(instance=instance, partial=True)

    with patch.object(NetworkWhiteList.objects, "all") as all_entries:
        all_entries.return_value.filter.return_value.exclude.return_value.exists.return_value = False
        with pytest.raises(serializers.ValidationError, match="不可变更|cannot be changed"):
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


@pytest.mark.django_db
def test_universal_cidr_cannot_be_written_through_bulk_orm():
    with pytest.raises(DjangoValidationError):
        NetworkWhiteList.objects.bulk_create([NetworkWhiteList(network="0.0.0.0/0")])
    with pytest.raises(ValueError, match="逐条 save"):
        NetworkWhiteList.objects.update(network="::/0")
