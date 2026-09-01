"""内置指标与指标分组只读契约测试。"""

from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.views.monitor_metrics import MetricGroupViewSet, MetricViewSet


@pytest.mark.parametrize(
    ("viewset", "instance"),
    [
        (MetricGroupViewSet, MetricGroup(name="builtin-group", is_pre=True)),
        (MetricViewSet, Metric(name="builtin-metric", is_pre=True)),
    ],
)
def test_builtin_metric_resources_are_read_only(viewset, instance):
    with pytest.raises(BaseAppException, match="只读"):
        viewset._ensure_modifiable(instance)


@pytest.mark.parametrize(
    ("viewset", "instance"),
    [
        (MetricGroupViewSet, MetricGroup(name="custom-group", is_pre=False)),
        (MetricViewSet, Metric(name="custom-metric", is_pre=False)),
    ],
)
def test_custom_metric_resources_remain_modifiable(viewset, instance):
    assert viewset._ensure_modifiable(instance) is None


@pytest.mark.parametrize(
    ("viewset", "model"),
    [
        (MetricGroupViewSet, MetricGroup),
        (MetricViewSet, Metric),
    ],
)
def test_builtin_metric_resources_cannot_be_reordered(mocker, viewset, model):
    queryset = mocker.patch.object(model.objects, "filter").return_value
    queryset.exists.return_value = True
    request = SimpleNamespace(
        data=[{"id": 1, "sort_order": 0}],
        user=SimpleNamespace(is_superuser=True),
    )

    with pytest.raises(BaseAppException, match="只读"):
        viewset().set_order(request)

    model.objects.filter.assert_called_once_with(id__in=[1], is_pre=True)
