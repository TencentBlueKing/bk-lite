"""console_mgmt init_user_set 视图的字段校验防护回归测试。

覆盖 Issue #3472：
- init_user_set：kwargs["group_name"] 裸字典访问，请求体缺少该字段时 KeyError → 500

规则：将修复代码 revert（将 kwargs.get("group_name") 改回 kwargs["group_name"]）后，
以下 test 必须失败——缺 group_name 时 KeyError 无捕获 → Django 500。
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.console_mgmt.views import init_user_set

pytestmark = [pytest.mark.unit]

INIT_URL = "/api/v1/console_mgmt/init_user_set/"


def _make_request(body: dict, group_list=None):
    """构造一个最小 request 对象，模拟已登录用户属于 OpsPilotGuest 组。"""
    factory = RequestFactory()
    req = factory.post(
        INIT_URL,
        data=json.dumps(body),
        content_type="application/json",
    )

    # 构造 group_list：默认为 OpsPilotGuest（首次登录状态）
    if group_list is None:
        group_list = [{"id": 1, "name": "OpsPilotGuest"}]

    user = MagicMock()
    user.username = "testuser"
    user.domain = "domain.com"
    user.locale = "zh"
    user.group_list = group_list
    req.user = user
    return req


class TestInitUserSetGroupNameRequired:
    """group_name 必填字段校验。"""

    def test_缺少group_name返回400而非500(self):
        """body 中没有 group_name 时应返回 400，不得抛 KeyError 触发 500。

        revert 修复（还原为 kwargs["group_name"]）后本测试必须失败：
        KeyError 无捕获 → Django 500 handler。
        """
        req = _make_request({})

        # patch User.objects.get 让用户查找成功，排除 User.DoesNotExist 干扰
        mock_user = MagicMock()
        mock_user.id = 99
        with patch("apps.console_mgmt.views.User") as MockUser:
            MockUser.objects.get.return_value = mock_user
            resp = init_user_set(req)

        assert resp.status_code == 400, (
            f"期望 400，实际 {resp.status_code}。"
            "说明 kwargs['group_name'] 裸字典访问未改为 .get() 校验。"
        )
        body = json.loads(resp.content)
        assert body["result"] is False
        assert "group_name" in body.get("message", "").lower() or body["result"] is False

    def test_group_name为空字符串返回400(self):
        """group_name 存在但为空字符串，也属于无效值，应返回 400。"""
        req = _make_request({"group_name": ""})

        mock_user = MagicMock()
        mock_user.id = 99
        with patch("apps.console_mgmt.views.User") as MockUser:
            MockUser.objects.get.return_value = mock_user
            resp = init_user_set(req)

        assert resp.status_code == 400
        body = json.loads(resp.content)
        assert body["result"] is False

    def test_携带合法group_name时正常调用下游(self):
        """group_name 存在且非空时，不应在字段校验阶段被拒，应走到下游 RPC 调用。

        本测试断言：响应不是因为「group_name 缺失」返回的 400；
        如果把修复 revert，缺 group_name 的路径会 500，与本测试无关——
        但若此测试失败，说明修复引入了误报（把合法请求也拦截了）。
        """
        req = _make_request({"group_name": "DevTeam"})

        mock_user = MagicMock()
        mock_user.id = 99
        rpc_resp = {"result": True, "data": {}}

        with patch("apps.console_mgmt.views.User") as MockUser, patch(
            "apps.console_mgmt.views.SystemMgmt"
        ) as MockRPC, patch("apps.console_mgmt.views.log_operation"):
            MockUser.objects.get.return_value = mock_user
            mock_rpc_instance = MagicMock()
            mock_rpc_instance.init_user_default_attributes.return_value = rpc_resp
            MockRPC.return_value = mock_rpc_instance

            resp = init_user_set(req)

        # 断言 RPC 被调用（说明通过了字段校验）
        mock_rpc_instance.init_user_default_attributes.assert_called_once_with(99, "DevTeam", 1)
        body = json.loads(resp.content)
        assert body["result"] is True
