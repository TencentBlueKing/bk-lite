import pytest

from apps.monitor.services.interface_metrics_query import (
    InterfaceMetricsQueryError,
    build_instance_id_selector,
    map_vm_instance_id,
    merge_interface_metric_rows,
    normalize_instance_ids,
    parse_instant_vector,
    query_interface_metric_items,
    vm_instance_id_labels,
)


def test_normalize_instance_ids_dedupes_and_accepts_list():
    assert normalize_instance_ids(["a", "a", "b"]) == ["a", "b"]
    assert normalize_instance_ids("a, b") == ["a", "b"]
    assert normalize_instance_ids(None) == []


def test_normalize_instance_ids_rejects_over_limit():
    with pytest.raises(InterfaceMetricsQueryError, match="不能超过"):
        normalize_instance_ids([str(i) for i in range(201)])


def test_build_instance_id_selector_escapes_regex_and_quotes():
    selector = build_instance_id_selector(["MTox", "sw.1"])
    assert 'instance_id=~"^(?:' in selector
    assert selector.endswith(')$"')
    assert r"\." in selector


def test_vm_instance_id_labels_unwraps_tuple_storage_keys():
    assert vm_instance_id_labels(["('MToxMC4xMC42OS4yNDc',)", "mon-1", "mon-1"]) == [
        "MToxMC4xMC42OS4yNDc",
        "mon-1",
    ]


def test_map_vm_instance_id_returns_requested_storage_key():
    storage_id = "('MToxMC4xMC42OS4yNDc',)"
    assert map_vm_instance_id("MToxMC4xMC42OS4yNDc", [storage_id, "mon-1"]) == storage_id
    assert map_vm_instance_id("mon-1", [storage_id, "mon-1"]) == "mon-1"
    assert map_vm_instance_id("ghost", [storage_id]) is None


def test_parse_instant_vector_keeps_ifdescr_and_skips_incomplete_series():
    payload = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "mon-1", "ifDescr": "Gi0/1"},
                    "value": [1, "2"],
                },
                {
                    "metric": {"instance_id": "mon-1"},
                    "value": [1, "1"],
                },
            ]
        },
    }
    rows = parse_instant_vector(payload, "interface_ifOperStatus")
    assert rows == [
        {
            "instance_id": "mon-1",
            "ifDescr": "Gi0/1",
            "metric": "interface_ifOperStatus",
            "value": 2.0,
        }
    ]


def test_merge_interface_metric_rows_groups_by_instance_and_ifdescr():
    items = merge_interface_metric_rows(
        [
            {
                "instance_id": "mon-1",
                "ifDescr": "Gi0/1",
                "metric": "interface_ifOperStatus",
                "value": 1,
            },
            {
                "instance_id": "mon-1",
                "ifDescr": "Gi0/1",
                "metric": "interface_ifHCInOctets",
                "value": 12.5,
            },
            {
                "instance_id": "mon-1",
                "ifDescr": "Gi0/2",
                "metric": "interface_ifOperStatus",
                "value": 2,
            },
        ]
    )
    by_descr = {item["ifDescr"]: item["metrics"] for item in items}
    assert by_descr["Gi0/1"]["interface_ifOperStatus"] == 1
    assert by_descr["Gi0/1"]["interface_ifHCInOctets"] == 12.5
    assert by_descr["Gi0/2"]["interface_ifOperStatus"] == 2


class _FakeVm:
    def __init__(self, payloads):
        self.payloads = payloads
        self.queries = []

    def query(self, query, step="5m"):
        self.queries.append(query)
        return self.payloads.get(query, {"status": "success", "data": {"result": []}})


def test_query_interface_metric_items_uses_rate_for_counters_and_merges():
    selector = build_instance_id_selector(["mon-1"])
    vm = _FakeVm(
        {
            f"interface_ifOperStatus{{{selector}}}": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "mon-1", "ifDescr": "Gi0/1"},
                            "value": [1, "1"],
                        }
                    ]
                },
            },
            f"rate(interface_ifHCInOctets{{{selector}}}[5m])": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "mon-1", "ifDescr": "Gi0/1"},
                            "value": [1, "1024"],
                        }
                    ]
                },
            },
        }
    )
    items = query_interface_metric_items(vm, ["mon-1"])
    assert items == [
        {
            "instance_id": "mon-1",
            "ifDescr": "Gi0/1",
            "metrics": {
                "interface_ifOperStatus": 1.0,
                "interface_ifHCInOctets": 1024.0,
            },
        }
    ]
    assert any("rate(interface_ifHCInOctets" in query for query in vm.queries)
    assert all("instance_type=" not in query for query in vm.queries)


def test_query_interface_metric_items_empty_ids_skips_vm():
    vm = _FakeVm({})
    assert query_interface_metric_items(vm, []) == []
    assert vm.queries == []


def test_query_unwraps_tuple_ids_and_remaps_response_to_requested_key():
    storage_id = "('MToxMC4xMC42OS4yNDc',)"
    vm_id = "MToxMC4xMC42OS4yNDc"
    selector = build_instance_id_selector([vm_id])
    vm = _FakeVm(
        {
            f"interface_ifOperStatus{{{selector}}}": {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": vm_id, "ifDescr": "GigabitEthernet0/0/5"},
                            "value": [1, "1"],
                        },
                        {
                            "metric": {"instance_id": "other", "ifDescr": "GigabitEthernet0/0/1"},
                            "value": [1, "2"],
                        },
                    ]
                },
            },
        }
    )
    items = query_interface_metric_items(vm, [storage_id])
    assert items == [
        {
            "instance_id": storage_id,
            "ifDescr": "GigabitEthernet0/0/5",
            "metrics": {"interface_ifOperStatus": 1.0},
        }
    ]
    assert vm.queries
    assert all(vm_id in query for query in vm.queries)
    assert all(storage_id not in query for query in vm.queries)
