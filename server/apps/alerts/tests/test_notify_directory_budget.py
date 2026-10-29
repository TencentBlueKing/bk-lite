"""通知接收人目录只应按请求用户名读取，不能每次把全站用户物化出来。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.alerts.common.notify.notify import Notify, SystemMgmtUtils
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db

_DIRECTORY_METHODS = ("get_user_all", "get_users_by_usernames")


def _observe_notify_directory(monkeypatch):
    """记录 Notify 实际调用的目录函数返回行数。

    观察函数只包住已有目录方法并转调原实现，不会自己再读全表。
    """
    sizes = []
    for name in _DIRECTORY_METHODS:
        original = getattr(SystemMgmtUtils, name, None)
        if original is None:
            continue

        def recorded(*args, _original=original, **kwargs):
            rows = _original(*args, **kwargs)
            if isinstance(rows, list):
                sizes.append(len(rows))
            return rows

        monkeypatch.setattr(SystemMgmtUtils, name, recorded)
    return sizes


def _create_unrelated_users(count):
    User.objects.bulk_create(
        [
            User(
                username=f"notify-unrelated-{index:04d}",
                display_name=f"无关用户{index}",
                email=f"notify-unrelated-{index:04d}@example.com",
                password="x",
            )
            for index in range(count)
        ]
    )


def _create_recipient():
    return User.objects.create(
        username="notify-recipient",
        display_name="接收人",
        email="notify-recipient@example.com",
        password="x",
    )


def _send_two_channels(monkeypatch, username):
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"result": True}

    monkeypatch.setattr(SystemMgmtUtils, "send_msg_with_channel", fake_send)
    channels = (
        (11, "email", True),
        (22, "enterprise_wechat", False),
    )
    for channel_id, channel_type, append_receivers in channels:
        Notify(
            username_list=[username],
            channel_id=channel_id,
            title="标题",
            content="正文",
            append_receivers=append_receivers,
            channel_type=channel_type,
        ).notify()
    return sent


@pytest.mark.parametrize("unrelated_count", [100, 500])
def test_两个渠道只读取请求中的接收人(unrelated_count, monkeypatch):
    _create_unrelated_users(unrelated_count)
    recipient = _create_recipient()
    directory_sizes = _observe_notify_directory(monkeypatch)

    sent = _send_two_channels(monkeypatch, recipient.username)

    total_users = User.objects.count()
    assert directory_sizes == [1, 1], f"unrelated={unrelated_count} total_users={total_users} directory_sizes={directory_sizes}"
    assert sent == [
        {
            "channel_id": 11,
            "title": "标题",
            "content": "正文",
            "receivers": [recipient.id],
            "append_receivers": True,
            "channel_type": "email",
        },
        {
            "channel_id": 22,
            "title": "标题",
            "content": "正文",
            "receivers": [recipient.id],
            "append_receivers": False,
            "channel_type": "enterprise_wechat",
        },
    ]


def test_缺失用户跳过且重复用户名按输入次数出现(monkeypatch):
    _create_unrelated_users(10)
    recipient = _create_recipient()
    directory_sizes = _observe_notify_directory(monkeypatch)

    users = Notify.get_user_list(["missing-user", recipient.username, recipient.username])

    assert directory_sizes == [1]
    assert [user["id"] for user in users] == [recipient.id, recipient.id]
    assert [user["username"] for user in users] == [recipient.username, recipient.username]
    assert [user["display_name"] for user in users] == ["接收人", "接收人"]


def test_空名单不读取用户表(monkeypatch):
    _create_unrelated_users(20)
    directory_sizes = _observe_notify_directory(monkeypatch)
    table_name = User._meta.db_table

    with CaptureQueriesContext(connection) as captured:
        assert Notify.get_user_list([]) == []

    assert directory_sizes == []
    assert not any(table_name in query["sql"] for query in captured.captured_queries)
