"""console_mgmt send_email_code 接口速率限制测试。

规格要点（Issue #3469）：
- send_email_code 接受任意 email 发送验证码（合法用途：修改绑定邮箱）
- 修复前：无速率限制，任意已登录用户可向任意外部邮箱无限发送
- 修复后：每用户每目标邮箱 60 秒内最多 1 次，超出返回 result=False

revert 测试：若将 `cache.set(rate_key, ...)` 和速率检查代码移除，第二个请求
会再次调用 send_email_to_receiver → mock 调用次数 > 1 → test_速率限制_第二次请求被拦截 失败。
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.console_mgmt.views import EMAIL_CODE_RATE_LIMIT_SECONDS, send_email_code
from apps.base.tests.factories import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.unit]

TARGET_EMAIL = "newaddr@example.com"


def _build_request(user, email=TARGET_EMAIL):
    """构造携带认证用户的 POST 请求。"""
    factory = RequestFactory()
    req = factory.post(
        "/api/v1/console_mgmt/send_email_code/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    req.user = user
    return req


@pytest.fixture
def alice(db):
    return UserFactory(username="alice", domain="domain.com")


class TestSendEmailCodeRateLimit:
    """速率限制守卫：确保同一用户对同一目标邮箱 60s 内只能发 1 次。"""

    def test_首次请求_正常发送(self, alice):
        mock_result = {"result": True}
        with patch("apps.console_mgmt.views.SystemMgmt") as MockClient, \
             patch("apps.console_mgmt.views.cache") as mock_cache:
            mock_cache.get.return_value = None  # 未命中速率限制
            instance = MockClient.return_value
            instance.send_email_to_receiver.return_value = mock_result

            req = _build_request(alice)
            resp = send_email_code(req)
            data = json.loads(resp.content)

            assert data["result"] is True
            # 发送后必须设置速率限制缓存
            mock_cache.set.assert_called_once()
            call_args = mock_cache.set.call_args
            assert call_args.kwargs.get("timeout") == EMAIL_CODE_RATE_LIMIT_SECONDS or (
                len(call_args.args) >= 3 and call_args.args[2] == EMAIL_CODE_RATE_LIMIT_SECONDS
            )
            # 确实调用了邮件发送
            instance.send_email_to_receiver.assert_called_once()

    def test_速率限制_第二次请求被拦截(self, alice):
        """速率限制命中时，不调用 send_email_to_receiver，返回 result=False。"""
        with patch("apps.console_mgmt.views.SystemMgmt") as MockClient, \
             patch("apps.console_mgmt.views.cache") as mock_cache:
            mock_cache.get.return_value = 1  # 模拟速率限制已命中
            instance = MockClient.return_value

            req = _build_request(alice)
            resp = send_email_code(req)
            data = json.loads(resp.content)

            assert data["result"] is False
            # 被速率限制拦截，不应发送邮件
            instance.send_email_to_receiver.assert_not_called()
            # 速率限制已命中，不应再次 set（避免重置窗口）
            mock_cache.set.assert_not_called()

    def test_速率限制_缓存key包含用户名和目标邮箱(self, alice):
        """缓存 key 必须同时包含用户名和目标邮箱，避免不同用户/邮箱互相干扰。"""
        with patch("apps.console_mgmt.views.SystemMgmt") as MockClient, \
             patch("apps.console_mgmt.views.cache") as mock_cache:
            mock_cache.get.return_value = None
            instance = MockClient.return_value
            instance.send_email_to_receiver.return_value = {"result": True}

            req = _build_request(alice, email="other@example.com")
            send_email_code(req)

            set_call = mock_cache.set.call_args
            rate_key = set_call.args[0] if set_call.args else set_call.kwargs.get("key", "")
            assert alice.username in rate_key
            assert "other@example.com" in rate_key

    def test_速率限制_不同用户之间不互相干扰(self, db):
        """alice 命中速率限制，bob 同一邮箱首次请求应成功。"""
        alice = UserFactory(username="alice", domain="domain.com")
        bob = UserFactory(username="bob", domain="domain.com")

        def fake_cache_get(key):
            # 只有 alice 的 key 命中速率限制
            return 1 if "alice" in key else None

        with patch("apps.console_mgmt.views.SystemMgmt") as MockClient, \
             patch("apps.console_mgmt.views.cache") as mock_cache:
            mock_cache.get.side_effect = fake_cache_get
            instance = MockClient.return_value
            instance.send_email_to_receiver.return_value = {"result": True}

            # alice 被拦截
            resp_alice = send_email_code(_build_request(alice))
            assert json.loads(resp_alice.content)["result"] is False

            # bob 不受影响
            resp_bob = send_email_code(_build_request(bob))
            assert json.loads(resp_bob.content)["result"] is True
