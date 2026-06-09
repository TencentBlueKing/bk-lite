import pytest
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory


@pytest.fixture
def make_client(db):
    """返回一个工厂：按 username 创建用户并返回其已认证的 APIClient。"""

    def _make(username, domain="domain.com", **kw):
        user = UserFactory(username=username, domain=domain, **kw)
        client = APIClient()
        client.force_authenticate(user=user)
        return user, client

    return _make


@pytest.fixture
def user_client(make_client):
    """默认用户 alice + 已认证 client。"""
    return make_client("alice")
