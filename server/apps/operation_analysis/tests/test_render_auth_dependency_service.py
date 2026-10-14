"""Render 身份建立时，数据库故障不能降级为空规则并继续认证。"""

from types import SimpleNamespace

import pytest
from django.db import InterfaceError, OperationalError


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_render_user_rules_database_failure_propagates(monkeypatch, error_type):
    from apps.operation_analysis.services import render_scope_service as module
    from apps.rpc.system_mgmt import SystemMgmt

    error = error_type("database unavailable")
    user = SimpleNamespace(username="creator", group_list=[1])
    monkeypatch.setattr(module.SystemUser.objects, "get", lambda **kwargs: user)
    monkeypatch.setattr(module, "build_user_authorization_context", lambda user: {"username": user.username})

    def fail(*args):
        raise error

    def must_not_continue(*args):
        raise AssertionError("依赖失败后不得继续创建认证身份")

    monkeypatch.setattr(SystemMgmt, "get_user_rules", fail)
    monkeypatch.setattr(module.AuthBackend, "set_user_info", must_not_continue)
    with pytest.raises(error_type) as caught:
        module.DashboardReportRenderScopeService.resolve_request_user(SimpleNamespace(_api_current_team=1), {})
    assert caught.value is error
    assert user.group_list == [1]
