"""issue #3140 回归测试：监控通知人列表必须按调用方授权范围收口，不返回全平台用户。

revert 准则：
- 若 view 的 get_user_all 改回不传 actor_context，test_view_passes_actor_context 必失败；
- 若 util 改回总是调 get_group_users（无作用域），test_util_routes_to_scoped 必失败。
"""

import types

from apps.monitor.utils import system_mgmt_api
from apps.monitor.views import system_mgmt as sm_view


def test_view_get_user_all_passes_actor_context(monkeypatch):
    captured = {}
    monkeypatch.setattr(sm_view, "_build_actor_context", lambda request: {"current_team": 7, "username": "u"})
    monkeypatch.setattr(
        sm_view.SystemMgmtUtils,
        "get_user_all",
        staticmethod(lambda actor_context=None, **kw: captured.update(actor_context=actor_context) or []),
    )
    monkeypatch.setattr(sm_view.WebUtils, "response_success", staticmethod(lambda data: data))

    request = types.SimpleNamespace(COOKIES={"current_team": "7"})
    sm_view.SystemMgmtView().get_user_all(request)

    # 视图必须把 actor_context 透传给 util（不再无作用域取全量）
    assert captured["actor_context"] == {"current_team": 7, "username": "u"}


def test_util_get_user_all_routes_to_scoped(monkeypatch):
    calls = []

    class _Client:
        def get_group_users(self, group=None, include_children=False):
            calls.append(("unscoped", group))
            return {"data": []}

        def get_group_users_scoped(self, actor_context, group=None, include_children=False):
            calls.append(("scoped", actor_context))
            return {"data": []}

    monkeypatch.setattr(system_mgmt_api, "SystemMgmt", _Client)

    # 带 actor_context → 走 scoped
    system_mgmt_api.SystemMgmtUtils.get_user_all(actor_context={"current_team": 7})
    # 无 actor_context → 走 unscoped（仅系统内部）
    system_mgmt_api.SystemMgmtUtils.get_user_all()

    assert calls[0][0] == "scoped"
    assert calls[0][1] == {"current_team": 7}
    assert calls[1][0] == "unscoped"
