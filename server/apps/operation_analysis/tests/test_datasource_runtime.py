from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.operation_analysis.common.runtime_params import build_runtime_params
from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet


def test_build_runtime_params_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        build_runtime_params(
            [{"name": "query", "type": "string", "filterType": "params", "value": ""}],
            {"query": "cpu", "unexpected": "boom"},
        )


def test_build_runtime_params_uses_fixed_defaults_and_runtime_extras():
    params = build_runtime_params(
        [
            {"name": "query", "type": "string", "filterType": "params", "value": ""},
            {"name": "time_range", "type": "timeRange", "filterType": "fixed", "value": 15},
            {"name": "step", "type": "string", "filterType": "fixed", "value": "5m"},
        ],
        {
            "query": "avg(cpu_usage)",
            "page": 2,
            "page_size": 20,
            "query_list": [{"field": "host", "type": "str*", "value": "db"}],
        },
    )

    assert params["query"] == "avg(cpu_usage)"
    assert params["step"] == "5m"
    assert params["page"] == 2
    assert params["page_size"] == 20
    assert params["query_list"] == [{"field": "host", "type": "str*", "value": "db"}]
    assert len(params["time_range"]) == 2


def test_get_source_data_rejects_unauthorized_instance_access():
    view = DataSourceAPIModelViewSet()
    request = SimpleNamespace(
        user=SimpleNamespace(is_superuser=False),
        COOKIES={"current_team": "2", "include_children": "0"},
    )
    view.request = request
    view.get_object = lambda: SimpleNamespace(id=3)
    view.get_has_permission = lambda user, instance, current_team, is_check=False, include_children=False: False

    with pytest.raises(PermissionDenied):
        view._ensure_source_access(request, view.get_object())
