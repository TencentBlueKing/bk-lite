"""指标列表 REST 契约回归测试。"""

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.monitor.models import MonitorObject, MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.views.monitor_metrics import MetricViewSet


@pytest.mark.django_db
def test_metric_list_returns_monitor_plugin_name():
    """展示列按 plugin+metric 解析元数据时，REST 指标列表必须返回插件内部名。"""
    monitor_object = MonitorObject.objects.create(
        name="MetricRestContractHost",
        display_name="MetricRestContractHost",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(
        name="MetricRestContractPlugin",
        display_name="MetricRestContractPlugin",
        template_id="metric-rest-contract",
        template_type="api",
        collector="test",
        collect_type="api",
        is_pre=False,
    )
    plugin.monitor_object.add(monitor_object)
    group = MetricGroup.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="MetricRestContractGroup",
    )
    metric = Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        metric_group=group,
        name="metric_rest_contract_value",
        display_name="Metric REST Contract Value",
        instance_id_keys=["instance_id"],
    )
    user = User.objects.create_user(username="metric_rest_contract_user", password="testpass123")
    request = APIRequestFactory().get("/monitor/api/metrics/", {"monitor_object_id": monitor_object.id})
    force_authenticate(request, user=user)

    response = MetricViewSet.as_view({"get": "list"})(request)
    payload = json.loads(response.content)
    result = next(item for item in payload["data"] if item["id"] == metric.id)

    assert result["monitor_plugin_name"] == plugin.name
