"""MonitorPlugin 写操作权限门禁单测（BL-NEW-005）。

验证 plugin.py 视图所依赖的 HasPermission 装饰器：无监控配置权限的登录用户被拒，
拥有权限 / 超管放行。这是修复「功能级授权缺失」所依赖的机制。

注：完整的 HTTP 端点级测试（实际 PATCH/import 路由返回 403）建议在具备 DB 的 CI
环境补充；此处以装饰器门禁为核心做无 DB 回归。
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.decorators.api_permission import HasPermission

pytestmark = pytest.mark.unit

_SENTINEL = "EXECUTED"
_DENIED = "DENIED_403"


@HasPermission("integration_configure-Add")
def _guarded(request):
    return _SENTINEL


def _call(user):
    with patch("apps.core.decorators.api_permission.WebUtils.response_403", return_value=_DENIED):
        return _guarded(SimpleNamespace(user=user))


def test_无监控配置权限用户被拒():
    user = SimpleNamespace(is_superuser=False, permission=set(), locale="en")
    assert _call(user) == _DENIED


def test_拥有配置权限放行():
    user = SimpleNamespace(is_superuser=False, permission={"integration_configure-Add"}, locale="en")
    assert _call(user) == _SENTINEL


def test_超管放行():
    user = SimpleNamespace(is_superuser=True, permission=set(), locale="en")
    assert _call(user) == _SENTINEL


def test_其他无关权限不放行():
    user = SimpleNamespace(is_superuser=False, permission={"some_other-View"}, locale="en")
    assert _call(user) == _DENIED
