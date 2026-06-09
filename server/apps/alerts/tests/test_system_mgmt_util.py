"""alerts.utils.system_mgmt_util.SystemMgmtUtils 测试。

规格：封装 system_mgmt RPC，统一从 result["data"] 取业务数据，并转发参数。
替换 RPC 客户端为记录器，验证取值与转发契约（不依赖真实 NATS）。
"""

from unittest import mock

import pytest

from apps.alerts.utils.system_mgmt_util import SystemMgmtUtils

pytestmark = pytest.mark.unit


class _FakeSystemMgmt:
    last = {}

    def get_all_users(self):
        return {"result": True, "data": [{"id": 1, "username": "alice"}]}

    def search_channel_list(self, channel_type):
        _FakeSystemMgmt.last["search_channel_list"] = channel_type
        return {"result": True, "data": [{"id": 9, "channel_type": channel_type}]}

    def send_msg_with_channel(self, channel_id, title, content, receivers):
        _FakeSystemMgmt.last["send"] = (channel_id, title, content, receivers)
        return {"result": True}


@pytest.fixture(autouse=True)
def patch_rpc():
    with mock.patch("apps.alerts.utils.system_mgmt_util.SystemMgmt", _FakeSystemMgmt):
        yield


def test_get_user_all_取data():
    assert SystemMgmtUtils.get_user_all() == [{"id": 1, "username": "alice"}]


def test_search_channel_list_转发并取data():
    out = SystemMgmtUtils.search_channel_list("email")
    assert _FakeSystemMgmt.last["search_channel_list"] == "email"
    assert out == [{"id": 9, "channel_type": "email"}]


def test_send_msg_with_channel_转发参数():
    SystemMgmtUtils.send_msg_with_channel(5, "标题", "内容", ["a@x.com"])
    assert _FakeSystemMgmt.last["send"] == (5, "标题", "内容", ["a@x.com"])
