from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.monitor.views.plugin import MonitorPluginViewSet

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


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
            permission={"monitor": {"integration_collect-View"}},
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
            permission={"monitor": {"integration_configure-Add"}},
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
