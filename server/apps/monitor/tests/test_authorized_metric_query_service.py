from types import SimpleNamespace

import pytest

from apps.monitor.models import Metric, MetricGroup, MonitorInstance, MonitorObject, MonitorPlugin
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService

pytestmark = pytest.mark.django_db


def _build_metric_contract():
    monitor_object = MonitorObject.objects.create(
        name="AuthorizedQueryObject",
        level="base",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(name="AuthorizedQueryPlugin")
    group = MetricGroup.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="AuthorizedQueryGroup",
    )
    metric = Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        dimensions=[{"name": "mode"}],
        unit="percent",
    )
    allowed = MonitorInstance.objects.create(
        id="('allowed-host',)",
        name="allowed-host",
        monitor_object=monitor_object,
    )
    denied = MonitorInstance.objects.create(
        id="('denied-host',)",
        name="denied-host",
        monitor_object=monitor_object,
    )
    return monitor_object, metric, allowed, denied


def _service(mocker, allowed_instance):
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.get_permission_rules",
        return_value={"data": "permission"},
    )
    mocker.patch(
        "apps.monitor.services.authorized_metric_query.permission_filter",
        side_effect=lambda model, permission, **kwargs: model.objects.filter(id=allowed_instance.id),
    )
    return AuthorizedMetricQueryService(
        user=SimpleNamespace(username="viewer", domain="domain.com", is_superuser=False),
        current_team="1",
        include_children=False,
    )


def test_range_query_uses_server_metric_template_and_authorized_instances(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )

    result = service.query_range(
        {
            "monitor_object_id": monitor_object.id,
            "metric_id": metric.id,
            "instance_ids": [allowed.id],
            "filters": [{"label": "mode", "operator": "=", "value": "idle"}],
            "aggregation": "SUM",
            "start": 1000,
            "end": 61000,
            "step": "60s",
        }
    )

    assert result == {"status": "success", "data": {"result": []}}
    vm_query.assert_called_once_with(
        'sum(cpu_usage{instance_id=~"allowed\\\\-host", mode="idle"}) by (instance_id)',
        1000,
        61000,
        "60s",
        detect_gaps=False,
        collection_interval_seconds=None,
        card_budget=False,
    )


def test_mixed_authorized_and_denied_instances_fail_before_vm_query(mocker):
    monitor_object, metric, allowed, denied = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        service.query_range(
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [allowed.id, denied.id],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            }
        )

    assert exc_info.value.code == "monitor_instance_forbidden"
    assert str(exc_info.value) == "无权访问所选监控实例"
    vm_query.assert_not_called()


def test_query_requires_explicit_instance_ids(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        service.query_range(
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            }
        )

    assert exc_info.value.code == "instance_ids_required"
    vm_query.assert_not_called()


def test_raw_query_field_is_rejected_before_vm_query(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        service.query_range(
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [allowed.id],
                "start": 1000,
                "end": 61000,
                "step": "60s",
                "query": 'secret_metric{instance_id="denied-host"}',
            }
        )

    assert exc_info.value.code == "raw_query_not_allowed"
    vm_query.assert_not_called()


def test_missing_identity_fails_before_permission_or_vm_query(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    permission = mocker.patch("apps.monitor.services.authorized_metric_query.get_permission_rules")
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")
    service = AuthorizedMetricQueryService(
        user=None,
        current_team=None,
        include_children=False,
    )

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        service.query_range(
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [allowed.id],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            }
        )

    assert exc_info.value.code == "query_identity_required"
    permission.assert_not_called()
    vm_query.assert_not_called()


def test_all_metric_template_selectors_receive_authorized_scope(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    metric.query = "left_metric{__$labels__} / right_metric{__$labels__}"
    metric.save(update_fields=["query"])
    service = _service(mocker, allowed)
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )

    service.query_range(
        {
            "monitor_object_id": monitor_object.id,
            "metric_id": metric.id,
            "instance_ids": [allowed.id],
            "start": 1000,
            "end": 61000,
            "step": "60s",
            "detect_gaps": True,
            "collection_interval": 60,
            "card_budget": True,
        }
    )

    query = vm_query.call_args.args[0]
    assert query.count('instance_id=~"allowed\\\\-host"') == 2
    assert vm_query.call_args.kwargs == {
        "detect_gaps": True,
        "collection_interval_seconds": 60,
        "card_budget": True,
    }


def test_undeclared_filter_is_rejected_before_vm_query(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        service.query_range(
            {
                "monitor_object_id": monitor_object.id,
                "metric_id": metric.id,
                "instance_ids": [allowed.id],
                "filters": [{"label": "organization", "operator": "=", "value": "2"}],
                "start": 1000,
                "end": 61000,
                "step": "60s",
            }
        )

    assert exc_info.value.code == "filter_label_invalid"
    vm_query.assert_not_called()


def test_instant_query_uses_server_template_and_range_end_as_eval_time(mocker):
    monitor_object, metric, allowed, _ = _build_metric_contract()
    service = _service(mocker, allowed)
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics",
        return_value={"status": "success", "data": {"result": []}},
    )

    result = service.query_instant(
        {
            "monitor_object_id": monitor_object.id,
            "metric_id": metric.id,
            "instance_ids": [allowed.id],
            "start": 1000,
            "end": 61000,
            "step": "60s",
        }
    )

    assert result["status"] == "success"
    vm_query.assert_called_once_with(
        'cpu_usage{instance_id=~"allowed\\\\-host"}',
        time=61.0,
    )
