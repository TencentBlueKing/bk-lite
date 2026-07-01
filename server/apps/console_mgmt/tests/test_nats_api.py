"""console_mgmt.nats_api.create_notification 真实测试。

create_notification 校验 app 白名单 + message 长度，校验通过则写 Notification 表。
策略：内置模块走真实 DB 写入；非内置模块经 App 表存在性校验；超长 message 被拒。
只 mock logger（边界外噪声）；DB 写入用真实 ORM。
"""
import pydantic.root_model  # noqa

import pytest

from apps.console_mgmt.models import Notification
from apps.console_mgmt.nats_api import MAX_MESSAGE_LENGTH, create_notification

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_内置模块创建成功并落库():
    out = create_notification("monitor", "磁盘告警")
    assert out == {"result": True}
    n = Notification.objects.get(app_module="monitor")
    assert n.content == "磁盘告警"
    assert n.source == "monitor"


def test_非内置非App表模块被拒():
    out = create_notification("not_a_real_app", "x")
    assert out["result"] is False
    assert "Invalid app module" in out["message"]
    assert not Notification.objects.filter(app_module="not_a_real_app").exists()


def test_非内置但App表存在则放行():
    from apps.system_mgmt.models.app import App
    App.objects.create(name="custom_app", display_name="自定义")
    out = create_notification("custom_app", "hello")
    assert out == {"result": True}
    assert Notification.objects.filter(app_module="custom_app").exists()


def test_message超长被拒():
    long_msg = "x" * (MAX_MESSAGE_LENGTH + 1)
    out = create_notification("monitor", long_msg)
    assert out["result"] is False
    assert "too long" in out["message"].lower()


def test_message恰好等于上限放行():
    msg = "y" * MAX_MESSAGE_LENGTH
    out = create_notification("cmdb", msg)
    assert out == {"result": True}
