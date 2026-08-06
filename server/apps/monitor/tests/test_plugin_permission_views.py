from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import routers

from apps.monitor.views.plugin import MonitorPluginViewSet

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

router = routers.DefaultRouter()
router.register(r"api/monitor_plugin", MonitorPluginViewSet, basename="MonitorPluginViewSet")
urlpatterns = router.urls


@override_settings(ROOT_URLCONF=__name__)
def test_只读权限_http_put_在读取插件前返回_403(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_collect-View"}}
    url = reverse("MonitorPluginViewSet-collect-template", kwargs={"pk": "plugin-1"})

    with (
        patch.object(MonitorPluginViewSet, "get_object") as get_object,
        patch(
            "apps.monitor.views.plugin.CustomSnmpPluginService.update_collect_template",
            return_value={"content": "new"},
        ) as update_template,
    ):
        response = api_client.put(
            url,
        {"content": "[[inputs.snmp.field]]"},
            format="json",
        )

    assert response.status_code == 403
    get_object.assert_not_called()
    update_template.assert_not_called()


@override_settings(ROOT_URLCONF=__name__)
def test_写权限_http_head_沿用读取路径且不更新模板(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_configure-Add"}}
    url = reverse("MonitorPluginViewSet-collect-template", kwargs={"pk": "plugin-1"})

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
        response = api_client.head(url)

    assert response.status_code == 200
    get_object.assert_called_once_with()
    get_template.assert_called_once()
    update_template.assert_not_called()
