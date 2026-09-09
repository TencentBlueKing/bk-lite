import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.filters.collect_filters import CollectModelFilter
from apps.cmdb.models.collect_model import CollectModels

pytestmark = pytest.mark.django_db


def _create_task(name, params):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.PROTOCOL,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="physcial_server",
        cycle_value_type="cycle",
        params=params,
    )


def _create_unrelated_task(name, *, params=None):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.PROTOCOL,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="mysql",
        cycle_value_type="cycle",
        params=params or {},
    )


def test_ipmi_filter_includes_legacy_tasks_without_protocol_marker():
    _create_task("legacy-ipmi", {})
    _create_task("explicit-ipmi", {"collection_protocol": "ipmi"})
    _create_task("redfish", {"collection_protocol": "redfish"})
    _create_unrelated_task("mysql-without-protocol")
    _create_unrelated_task("mysql-explicit-ipmi", params={"collection_protocol": "ipmi"})

    queryset = CollectModelFilter(
        {"collection_protocol": "ipmi"},
        queryset=CollectModels.objects.all(),
    ).qs

    assert set(queryset.values_list("name", flat=True)) == {
        "legacy-ipmi",
        "explicit-ipmi",
    }


def test_redfish_filter_only_returns_explicit_redfish_tasks():
    _create_task("legacy-ipmi", {})
    _create_task("explicit-ipmi", {"collection_protocol": "ipmi"})
    _create_task("redfish", {"collection_protocol": "redfish"})
    _create_unrelated_task("mysql-explicit-redfish", params={"collection_protocol": "redfish"})

    queryset = CollectModelFilter(
        {"collection_protocol": "redfish"},
        queryset=CollectModels.objects.all(),
    ).qs

    assert list(queryset.values_list("name", flat=True)) == ["redfish"]
