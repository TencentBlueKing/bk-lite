from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.monitor.views.monitor_metrics import MetricGroupViewSet, MetricViewSet
from apps.monitor.views.monitor_object import MonitorObjectTypeViewSet, MonitorObjectViewSet
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = pytest.mark.unit


WRITE_ACTION_CASES = [
    pytest.param(MonitorObjectTypeViewSet, "post", "create", {}, "object-Add", id="object-type-create"),
    pytest.param(MonitorObjectTypeViewSet, "put", "update", {"pk": "missing"}, "object-Edit", id="object-type-update"),
    pytest.param(MonitorObjectTypeViewSet, "patch", "partial_update", {"pk": "missing"}, "object-Edit", id="object-type-partial"),
    pytest.param(MonitorObjectTypeViewSet, "delete", "destroy", {"pk": "missing"}, "object-Delete", id="object-type-delete"),
    pytest.param(MonitorObjectViewSet, "post", "create", {}, "object-Add", id="object-create"),
    pytest.param(MonitorObjectViewSet, "put", "update", {"pk": "missing"}, "object-Edit", id="object-update"),
    pytest.param(MonitorObjectViewSet, "patch", "partial_update", {"pk": "missing"}, "object-Edit", id="object-partial"),
    pytest.param(MonitorObjectViewSet, "delete", "destroy", {"pk": "missing"}, "object-Delete", id="object-delete"),
    pytest.param(MonitorObjectViewSet, "post", "order", {}, "object-Edit", id="object-order"),
    pytest.param(MonitorObjectViewSet, "post", "visibility", {"pk": "missing"}, "object-Edit", id="object-visibility"),
    pytest.param(MonitorObjectViewSet, "post", "display_fields", {"pk": "missing"}, "object-Edit", id="object-display-fields"),
    pytest.param(MetricGroupViewSet, "post", "create", {}, "integration_metric-Add Group", id="metric-group-create"),
    pytest.param(MetricGroupViewSet, "put", "update", {"pk": "missing"}, "integration_metric-Edit Group", id="metric-group-update"),
    pytest.param(MetricGroupViewSet, "patch", "partial_update", {"pk": "missing"}, "integration_metric-Edit Group", id="metric-group-partial"),
    pytest.param(MetricGroupViewSet, "delete", "destroy", {"pk": "missing"}, "integration_metric-Delete Group", id="metric-group-delete"),
    pytest.param(MetricGroupViewSet, "post", "set_order", {}, "integration_metric-Edit Group", id="metric-group-order"),
    pytest.param(MetricViewSet, "post", "create", {}, "integration_metric-Add Metric", id="metric-create"),
    pytest.param(MetricViewSet, "put", "update", {"pk": "missing"}, "integration_metric-Edit Metric", id="metric-update"),
    pytest.param(MetricViewSet, "patch", "partial_update", {"pk": "missing"}, "integration_metric-Edit Metric", id="metric-partial"),
    pytest.param(MetricViewSet, "delete", "destroy", {"pk": "missing"}, "integration_metric-Delete Metric", id="metric-delete"),
    pytest.param(MetricViewSet, "post", "set_order", {}, "integration_metric-Edit Metric", id="metric-order"),
    pytest.param(MetricViewSet, "post", "test_query", {}, "integration_metric-Edit Metric", id="metric-test-query"),
    pytest.param(MonitorPolicyViewSet, "post", "create", {}, "strategy_list-Add", id="strategy-create"),
    pytest.param(MonitorPolicyViewSet, "put", "update", {"pk": "missing"}, "strategy_list-Edit", id="strategy-update"),
    pytest.param(MonitorPolicyViewSet, "patch", "partial_update", {"pk": "missing"}, "strategy_list-Edit", id="strategy-partial"),
    pytest.param(MonitorPolicyViewSet, "delete", "destroy", {"pk": "missing"}, "strategy_list-Delete", id="strategy-delete"),
    pytest.param(MonitorPolicyViewSet, "post", "save_template", {}, "strategy_list-Edit", id="strategy-template-save"),
    pytest.param(MonitorPolicyViewSet, "post", "import_templates", {}, "strategy_list-Edit", id="strategy-template-import"),
    pytest.param(MonitorPolicyViewSet, "post", "bulk_delete_templates", {}, "strategy_list-Delete", id="strategy-template-delete"),
    pytest.param(MonitorPolicyViewSet, "post", "bulk_create_from_templates", {}, "strategy_list-Add", id="strategy-template-bulk-create"),
]


def _invoke(view_class, method, action, path_kwargs, permissions):
    request_factory = APIRequestFactory()
    request = getattr(request_factory, method)("/", {}, format="json")
    user = SimpleNamespace(
        username="permission-user",
        domain="domain.com",
        locale="en",
        is_superuser=False,
        is_authenticated=True,
        permission={"monitor": set(permissions)},
    )
    force_authenticate(request, user=user)
    view = view_class.as_view({method: action})
    try:
        response = view(request, **path_kwargs)
    except Exception:
        return None
    return response.status_code


@pytest.mark.parametrize("view_class,method,action,path_kwargs,required_permission", WRITE_ACTION_CASES)
def test_global_write_action_requires_matching_menu_permission(
    view_class,
    method,
    action,
    path_kwargs,
    required_permission,
):
    assert _invoke(view_class, method, action, path_kwargs, set()) == 403
    assert _invoke(view_class, method, action, path_kwargs, {required_permission}) != 403
