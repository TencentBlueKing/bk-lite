"""
测试 APISecretMiddleware 的 team 上下文注入行为，以及 get_current_team 工具函数。

Issue #3486：中间件不应直接写 request.COOKIES（只读 dict），应通过
request._api_current_team 属性注入，下游统一使用 get_current_team(request) 读取。

测试策略：使用 revert-fail 准则——将 _handle_successful_auth 中的
request._api_current_team = ... 改回 request.COOKIES[...] = ... 后，这些测试会失败。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.utils.team_utils import get_current_team


# ---------------------------------------------------------------------------
# 辅助：构造轻量 request mock
# ---------------------------------------------------------------------------

def _make_request(cookies=None, api_current_team=None):
    """构造只包含 COOKIES 和可选 _api_current_team 的轻量 request。"""
    req = SimpleNamespace(
        COOKIES=dict(cookies or {}),
        META={},
        session=SimpleNamespace(session_key="fake-key"),
    )
    if api_current_team is not None:
        req._api_current_team = api_current_team
    return req


# ---------------------------------------------------------------------------
# get_current_team 工具函数测试
# ---------------------------------------------------------------------------

class TestGetCurrentTeam:
    """验证 get_current_team 读取优先级：_api_current_team > COOKIES > default"""

    def test_api_attr_takes_priority_over_cookie(self):
        """当 _api_current_team 和 COOKIES 都存在时，返回 _api_current_team 的值。"""
        req = _make_request(
            cookies={"current_team": "99"},
            api_current_team="7",
        )
        assert get_current_team(req) == "7"

    def test_cookie_used_when_no_api_attr(self):
        """没有 _api_current_team 时，从 COOKIES 读取。"""
        req = _make_request(cookies={"current_team": "42"})
        assert get_current_team(req) == "42"

    def test_default_when_neither_present(self):
        """既没有 _api_current_team 也没有 cookie 时，返回 default。"""
        req = _make_request()
        assert get_current_team(req) is None
        assert get_current_team(req, "0") == "0"

    def test_api_attr_zero_string_is_returned_not_default(self):
        """_api_current_team 为 "0" 时应返回 "0"，而不是 default。"""
        req = _make_request(api_current_team="0")
        assert get_current_team(req, "fallback") == "0"

    def test_cookie_zero_string_is_returned_not_default(self):
        """COOKIES["current_team"] 为 "0" 时应返回 "0"，而不是 default。"""
        req = _make_request(cookies={"current_team": "0"})
        assert get_current_team(req, "fallback") == "0"


# ---------------------------------------------------------------------------
# APISecretMiddleware 注入行为测试
# ---------------------------------------------------------------------------

class TestAPISecretMiddlewareTeamInjection:
    """验证中间件使用 request._api_current_team 而非写 request.COOKIES。"""

    def _make_middleware(self):
        from apps.core.middlewares.api_middleware import APISecretMiddleware
        mw = APISecretMiddleware(get_response=lambda r: None)
        return mw

    def _make_auth_request(self, has_cookie=False):
        """构造模拟认证请求，模拟 auth.login 后的状态。"""
        req = SimpleNamespace(
            COOKIES={"current_team": "99"} if has_cookie else {},
            META={},
            session=SimpleNamespace(session_key="fake-session"),
            user=SimpleNamespace(
                group_list=[7, 8],
                locale="zh-cn",
            ),
        )
        setattr(req, "api_pass", False)
        return req

    def test_middleware_sets_api_attr_not_cookies(self):
        """
        当请求不携带 current_team cookie 时，中间件应设置
        request._api_current_team，而不是直接写 request.COOKIES。

        revert-fail：若改回 request.COOKIES[...] = ...，
        断言 "_api_current_team" in req.__dict__ 将失败。
        """
        mw = self._make_middleware()
        req = self._make_auth_request(has_cookie=False)
        user = req.user

        with patch("apps.core.middlewares.api_middleware.auth") as mock_auth:
            mock_auth.login.return_value = None
            mw._handle_successful_auth(req, user)

        # 关键断言：_api_current_team 必须被设置
        assert hasattr(req, "_api_current_team"), (
            "中间件应设置 request._api_current_team，而非写 request.COOKIES"
        )
        assert req._api_current_team == "7"

    def test_middleware_does_not_mutate_cookies_dict(self):
        """
        中间件不应向 request.COOKIES 写入 current_team。

        revert-fail：若改回 request.COOKIES[...] = ...，
        断言 cookies_before == cookies_after 将失败。
        """
        mw = self._make_middleware()
        req = self._make_auth_request(has_cookie=False)
        user = req.user
        cookies_before = dict(req.COOKIES)

        with patch("apps.core.middlewares.api_middleware.auth") as mock_auth:
            mock_auth.login.return_value = None
            mw._handle_successful_auth(req, user)

        assert req.COOKIES == cookies_before, (
            "中间件不应修改 request.COOKIES（只读 dict），应使用 request._api_current_team"
        )

    def test_middleware_skips_injection_when_cookie_present(self):
        """当浏览器已携带 current_team cookie 时，不注入 _api_current_team。"""
        mw = self._make_middleware()
        req = self._make_auth_request(has_cookie=True)
        user = req.user

        with patch("apps.core.middlewares.api_middleware.auth") as mock_auth:
            mock_auth.login.return_value = None
            mw._handle_successful_auth(req, user)

        assert not hasattr(req, "_api_current_team"), (
            "浏览器已有 cookie 时不应注入 _api_current_team"
        )

    def test_get_current_team_reads_injected_attr(self):
        """
        端到端：中间件注入 + get_current_team 读取，结果符合预期。

        revert-fail：若中间件改回写 COOKIES，get_current_team 仍能通过 COOKIES 读到值，
        但 test_middleware_does_not_mutate_cookies_dict 会失败，保证整体检测有效。
        """
        mw = self._make_middleware()
        req = self._make_auth_request(has_cookie=False)
        user = req.user

        with patch("apps.core.middlewares.api_middleware.auth") as mock_auth:
            mock_auth.login.return_value = None
            mw._handle_successful_auth(req, user)

        assert get_current_team(req) == "7"

    def test_empty_group_list_does_not_inject(self):
        """group_list 为空时，不设置 _api_current_team。"""
        mw = self._make_middleware()
        req = self._make_auth_request(has_cookie=False)
        req.user.group_list = []

        with patch("apps.core.middlewares.api_middleware.auth") as mock_auth:
            mock_auth.login.return_value = None
            mw._handle_successful_auth(req, req.user)

        assert not hasattr(req, "_api_current_team")
        assert get_current_team(req) is None
