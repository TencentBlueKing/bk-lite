"""通知中心按用户隔离 BDD（中文 Gherkin）。

对照 notification.feature：已读/删除按用户隔离、重复标记幂等。
经真实 DRF 接口验证（含全局响应封装），不 mock 业务逻辑。
"""

from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory
from apps.console_mgmt.tests.factories import NotificationFactory

pytestmark = pytest.mark.bdd

FEATURE = str(Path(__file__).parent / "notification.feature")
scenarios(FEATURE)

BASE = "/api/v1/console_mgmt/notifications/"


def _data(resp):
    return resp.json()["data"]


@pytest.fixture
def ctx(db):
    return {"clients": {}}


def _client_for(ctx, username):
    if username not in ctx["clients"]:
        user = UserFactory(username=username, domain="domain.com")
        client = APIClient()
        client.force_authenticate(user=user)
        ctx["clients"][username] = client
    return ctx["clients"][username]


@given("系统中存在一条系统通知")
def given_one_notification(ctx):
    ctx["notification"] = NotificationFactory()


@when(parsers.parse('用户 "{username}" 将该通知标记为已读'))
def when_mark_read(ctx, username):
    client = _client_for(ctx, username)
    client.post(f"{BASE}{ctx['notification'].id}/mark_as_read/")


@when(parsers.parse('用户 "{username}" 再次将该通知标记为已读'))
def when_mark_read_again(ctx, username):
    client = _client_for(ctx, username)
    client.post(f"{BASE}{ctx['notification'].id}/mark_as_read/")


@when(parsers.parse('用户 "{username}" 删除该通知'))
def when_delete(ctx, username):
    client = _client_for(ctx, username)
    client.delete(f"{BASE}{ctx['notification'].id}/")


@then(parsers.parse('用户 "{username}" 看到该通知为已读'))
def then_read(ctx, username):
    client = _client_for(ctx, username)
    assert _data(client.get(BASE))[0]["is_read"] is True


@then(parsers.parse('用户 "{username}" 看到该通知为未读'))
def then_unread(ctx, username):
    client = _client_for(ctx, username)
    assert _data(client.get(BASE))[0]["is_read"] is False


@then(parsers.parse('用户 "{username}" 的通知列表为空'))
def then_empty(ctx, username):
    client = _client_for(ctx, username)
    assert _data(client.get(BASE)) == []


@then(parsers.parse('用户 "{username}" 仍能看到该通知'))
def then_still_visible(ctx, username):
    client = _client_for(ctx, username)
    assert len(_data(client.get(BASE))) == 1


@then(parsers.parse('用户 "{username}" 的未读数量为 {count:d}'))
def then_unread_count(ctx, username, count):
    client = _client_for(ctx, username)
    resp = client.get(f"{BASE}unread_count/")
    assert resp.json()["data"]["count"] == count
