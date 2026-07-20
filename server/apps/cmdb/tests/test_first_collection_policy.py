import types

import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy

pytestmark = pytest.mark.unit


def task(**overrides):
    values = {
        "id": 7,
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "instances": [{"inst_name": "host-1", "ip_addr": "10.0.0.1"}],
        "ip_range": "",
        "access_point": [{"id": "node-1"}],
        "plugin_id": "host_info",
        "params": {"port": 22},
        "timeout": 60,
        "decrypt_credentials": {"username": "root", "password": "secret"},
        "name": "任务",
        "team": [1],
        "expire_days": 7,
        "data_cleanup_strategy": "no_cleanup",
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_interval": False},
        {"cycle_value_type": "timing"},
        {"cycle_value": "14"},
        {"cycle_value": "bad"},
        {"task_type": CollectPluginTypes.K8S},
        {"task_type": CollectPluginTypes.CONFIG_FILE},
    ],
)
def test_ineligible_tasks_are_rejected(overrides):
    assert FirstCollectionPolicy.is_eligible(task(**overrides)) is False


def test_threshold_task_is_eligible():
    assert FirstCollectionPolicy.is_eligible(task(cycle_value="15")) is True


def test_equivalent_dict_order_has_same_fingerprint():
    first = task(params={"port": 22, "options": {"b": 2, "a": 1}})
    second = task(params={"options": {"a": 1, "b": 2}, "port": 22})
    assert FirstCollectionPolicy.fingerprint(first) == FirstCollectionPolicy.fingerprint(second)


def test_fingerprint_is_irreversible():
    result = FirstCollectionPolicy.fingerprint(task())
    assert len(result) == 64
    assert "secret" not in result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instances", [{"inst_name": "host-2"}]),
        ("access_point", [{"id": "node-2"}]),
        ("plugin_id", "host_info_v2"),
        ("params", {"port": 2222}),
        ("timeout", 90),
        ("cycle_value", "60"),
        ("decrypt_credentials", {"username": "root", "password": "new-secret"}),
    ],
)
def test_source_change_triggers(field, value):
    old = task()
    new = task(**{field: value})
    assert field in FirstCollectionPolicy.changed_fields(old, new)
    assert FirstCollectionPolicy.should_trigger_update(old, new) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "新名称"),
        ("team", [2]),
        ("expire_days", 30),
        ("data_cleanup_strategy", "delete"),
    ],
)
def test_governance_change_does_not_trigger(field, value):
    assert FirstCollectionPolicy.should_trigger_update(task(), task(**{field: value})) is False


def test_update_to_short_cycle_does_not_trigger():
    assert FirstCollectionPolicy.should_trigger_update(task(), task(cycle_value="5")) is False
