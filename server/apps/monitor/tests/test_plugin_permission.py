"""MonitorPlugin 写操作权限门禁单测（BL-NEW-005）。

验证 plugin.py 视图所依赖的 HasPermission 装饰器，以及采集模板 action 的方法级
权限分派：无监控配置权限的登录用户被拒，拥有权限 / 超管放行。测试保持无 DB，
并断言拒绝发生在插件读取与模板服务调用之前。
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.decorators.api_permission import HasPermission
from apps.monitor.views.plugin import MonitorPluginViewSet

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


def _call_collect_template(method, permissions, *, is_superuser=False):
    request = SimpleNamespace(
        method=method,
        data={"content": "[[inputs.snmp.field]]"},
        user=SimpleNamespace(is_superuser=is_superuser, permission=set(permissions), locale="en"),
    )
    view = MonitorPluginViewSet()
    view.get_object = Mock(return_value=SimpleNamespace(template_type="snmp"))

    with (
        patch("apps.core.decorators.api_permission.WebUtils.response_403", return_value=_DENIED),
        patch("apps.monitor.views.plugin.WebUtils.response_success", side_effect=lambda data: data),
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.get_collect_template",
            return_value={"content": "old"},
        ) as get_template,
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.update_collect_template",
            return_value={"content": "new"},
        ) as update_template,
    ):
        result = view.collect_template(request, pk="plugin-1")

    return result, view.get_object, get_template, update_template


def test_只读权限_put_在读取插件前被拒绝():
    result, get_object, get_template, update_template = _call_collect_template(
        "PUT",
        {"integration_collect-View"},
    )

    assert result == _DENIED
    get_object.assert_not_called()
    get_template.assert_not_called()
    update_template.assert_not_called()


def test_只读权限_get_可读取采集模板():
    result, get_object, get_template, update_template = _call_collect_template(
        "GET",
        {"integration_collect-View"},
    )

    assert result == {"content": "old"}
    get_object.assert_called_once_with()
    get_template.assert_called_once()
    update_template.assert_not_called()


def test_写权限_put_可更新采集模板():
    result, get_object, get_template, update_template = _call_collect_template(
        "PUT",
        {"integration_configure-Add"},
    )

    assert result == {"content": "new"}
    get_object.assert_called_once_with()
    get_template.assert_not_called()
    update_template.assert_called_once()


def test_既有写权限_get_继续兼容读取采集模板():
    result, get_object, get_template, update_template = _call_collect_template(
        "GET",
        {"integration_configure-Add"},
    )

    assert result == {"content": "old"}
    get_object.assert_called_once_with()
    get_template.assert_called_once()
    update_template.assert_not_called()


def test_超级用户_put_继续兼容更新采集模板():
    result, get_object, get_template, update_template = _call_collect_template(
        "PUT",
        set(),
        is_superuser=True,
    )

    assert result == {"content": "new"}
    get_object.assert_called_once_with()
    get_template.assert_not_called()
    update_template.assert_called_once()


def test_只读权限_http_put_在读取插件前返回_403():
    request = APIRequestFactory().put(
        "/monitor/api/monitor_plugin/plugin-1/collect_template/",
        {"content": "[[inputs.snmp.field]]"},
        format="json",
    )
    force_authenticate(
        request,
        user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            permission={"integration_collect-View"},
            locale="en",
        ),
    )

    with (
        patch.object(MonitorPluginViewSet, "get_object") as get_object,
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.update_collect_template",
            return_value={"content": "new"},
        ) as update_template,
    ):
        response = MonitorPluginViewSet.as_view({"put": "collect_template"})(request, pk="plugin-1")

    assert response.status_code == 403
    get_object.assert_not_called()
    update_template.assert_not_called()


def test_写权限_http_head_沿用读取路径且不更新模板():
    request = APIRequestFactory().head(
        "/monitor/api/monitor_plugin/plugin-1/collect_template/",
    )
    force_authenticate(
        request,
        user=SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            permission={"integration_configure-Add"},
            locale="en",
        ),
    )

    with (
        patch.object(
            MonitorPluginViewSet,
            "get_object",
            return_value=SimpleNamespace(template_type="snmp"),
        ) as get_object,
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.get_collect_template",
            return_value={"content": "old"},
        ) as get_template,
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.update_collect_template",
            return_value={"content": "new"},
        ) as update_template,
    ):
        response = MonitorPluginViewSet.as_view(
            {
                "get": "collect_template",
                "put": "collect_template",
            }
        )(request, pk="plugin-1")

    assert response.status_code == 200
    get_object.assert_called_once_with()
    get_template.assert_called_once()
    update_template.assert_not_called()
