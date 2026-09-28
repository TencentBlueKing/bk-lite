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

    def search_workflow_orchestration_nats_channels(self, teams=None, workflow_id=None, include_children=False, active_only=True):
        _FakeSystemMgmt.last["search_workflow"] = (teams, workflow_id, include_children, active_only)
        return {"result": True, "data": [{"id": 10, "channel_type": "nats"}]}

    def send_msg_with_channel(self, channel_id, title, content, receivers, append_receivers=True, channel_type=None):
        _FakeSystemMgmt.last["send"] = (channel_id, title, content, receivers, append_receivers, channel_type)
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


def test_search_workflow_orchestration_nats_channels_只查询已启用通道():
    out = SystemMgmtUtils.search_workflow_orchestration_nats_channels(teams=[7], workflow_id=12, include_children=True)
    assert _FakeSystemMgmt.last["search_workflow"] == ([7], 12, True, True)
    assert out == [{"id": 10, "channel_type": "nats"}]


@pytest.mark.parametrize("append_receivers", [True, False])
def test_send_msg_with_channel_转发参数(append_receivers):
    SystemMgmtUtils.send_msg_with_channel(5, "标题", "内容", ["a@x.com"], append_receivers=append_receivers)
    assert _FakeSystemMgmt.last["send"] == (5, "标题", "内容", ["a@x.com"], append_receivers, None)


def test_send_msg_with_channel_转发channel_type():
    SystemMgmtUtils.send_msg_with_channel(5, "标题", "内容", ["a@x.com"], channel_type="im_notification")
    assert _FakeSystemMgmt.last["send"] == (5, "标题", "内容", ["a@x.com"], True, "im_notification")
