"""NetworkWhiteListSerializer.validate_network 纯函数校验（无 DB）。"""
import pytest
from rest_framework import serializers

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
