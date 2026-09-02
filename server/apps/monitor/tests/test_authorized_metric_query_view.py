import json

import pytest
from django.urls import Resolver404, resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.exceptions.base_app_exception import UnauthorizedException
from apps.monitor.models import Metric, MetricGroup, MonitorInstance, MonitorObject, MonitorPlugin
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet

pytestmark = pytest.mark.django_db


def _setup_query_contract(*, object_name="AuthorizedViewObject"):
    monitor_object = MonitorObject.objects.create(
        name=object_name,
        level="base",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(name="AuthorizedViewPlugin")
    group = MetricGroup.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="AuthorizedViewGroup",
    )
    metric = Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        unit="percent",
    )
    allowed = MonitorInstance.objects.create(
        id="('allowed-view-host',)",
        name="allowed-view-host",
        monitor_object=monitor_object,
    )
    denied = MonitorInstance.objects.create(
        id="('denied-view-host',)",
        name="denied-view-host",
        monitor_object=monitor_object,
    )
    return monitor_object, metric, allowed, denied


def _request(user, payload):
    request = APIRequestFactory().post(
        "/monitor/api/metrics_instance/query_by_metric_range/",
        payload,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def test_authorized_range_view_uses_authenticated_request_scope(authenticated_user, mocker):
    monitor_object, metric, allowed, _ = _setup_query_contract()
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.get_permission_rules",
        return_value={"data": "permission"},
    )
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.permission_filter",
        side_effect=lambda model, permission, **kwargs: model.objects.filter(id=allowed.id),
    )
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )
    view = MetricsInstanceViewSet.as_view({"post": "query_by_metric_range"})

    response = view(
        _request(
            authenticated_user,
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [allowed.id],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            },
        )
    )

    assert response.status_code == 200
    assert json.loads(response.content)["result"] is True
    vm_query.assert_called_once()


def test_authorized_range_view_rejects_mixed_scope_without_vm_call(authenticated_user, mocker):
    monitor_object, metric, allowed, denied = _setup_query_contract()
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.get_permission_rules",
        return_value={"data": "permission"},
    )
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.permission_filter",
        side_effect=lambda model, permission, **kwargs: model.objects.filter(id=allowed.id),
    )
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")
    view = MetricsInstanceViewSet.as_view({"post": "query_by_metric_range"})

    with pytest.raises(UnauthorizedException, match="无权访问所选监控实例"):
        view(
            _request(
                authenticated_user,
                {
                    "monitor_object_id": monitor_object.id,
                    "metric_id": metric.id,
                    "instance_ids": [allowed.id, denied.id],
                    "start": 1000,
                    "end": 61000,
                    "step": "60s",
                },
            )
        )

    vm_query.assert_not_called()


def test_authorized_range_view_executes_registered_dashboard_capability(authenticated_user, mocker):
    monitor_object, _, allowed, _ = _setup_query_contract(object_name="Website")
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.get_permission_rules",
        return_value={"data": "permission"},
    )
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.permission_filter",
        side_effect=lambda model, permission, **kwargs: model.objects.filter(id=allowed.id),
    )
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )
    view = MetricsInstanceViewSet.as_view({"post": "query_by_metric_range"})

    response = view(
        _request(
            authenticated_user,
            {
                "monitor_object_id": monitor_object.id,
                "capability_id": "dashboard:v1:0a6a83ef",
                "instance_ids": [allowed.id],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            },
        )
    )

    assert response.status_code == 200
    assert json.loads(response.content)["result"] is True
    query = vm_query.call_args.args[0]
    assert "http_response_result_code" in query
    assert 'instance_id=~"allowed\\\\-view\\\\-host"' in query


@pytest.mark.parametrize("action", ["query", "query_range"])
def test_raw_promql_rest_actions_are_not_registered(action):
    with pytest.raises(Resolver404):
        resolve(f"/api/v1/monitor/api/metrics_instance/{action}/")
