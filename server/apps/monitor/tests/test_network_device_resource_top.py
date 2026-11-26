import logging
import time
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.management.services.plugin_migrate import _build_common_ifmib_metrics
from apps.monitor.services.metric_query_contract import build_instance_matcher_groups, join_label_queries
from apps.monitor.services.network_device_resource_top import (
    CPU_MEMORY_OBJECT_NAMES,
    NetworkDeviceResourceTopService,
    build_ranked_rows,
    collection_interval_seconds,
    gauge_search_window_seconds,
    load_network_device_detail_metrics,
    traffic_search_window_seconds,
)

NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
NO_CARD_OBJECTS = (
    "Wireless",
    "Access",
    "Transmission",
    "NetworkService",
    "ConsoleServer",
    "VoiceGateway",
)
LOCAL_QUERY_BYTE_BUDGET = 16128


class FakeVM:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker
        self.calls = []

    def query(self, query, **kwargs):
        self.calls.append((query, kwargs))
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return {"status": "success", "data": {"result": rows}}
        return {"status": "success", "data": {"result": []}}


def _point(instance_id, value, sampled_at=NOW):
    return {"metric": {"instance_id": instance_id}, "value": [sampled_at.timestamp(), str(value)]}


def _device(instance_id, object_name, *, interval=300, keys=("instance_id",), type_id="Network Device", name=""):
    return SimpleNamespace(
        id=instance_id,
        name=name or instance_id,
        ip="10.0.0.1",
        interval=interval,
        monitor_object=SimpleNamespace(name=object_name, type_id=type_id, instance_id_keys=list(keys)),
    )


def _run(metric_type, devices, rows_by_marker):
    vm = FakeVM(rows_by_marker)
    rows = NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run(metric_type, devices)
    return rows, vm


def _binding(object_name, metric_name):
    return load_network_device_detail_metrics()[(object_name, metric_name)]


def _catalog(metric_name):
    return next(item["query"] for item in _build_common_ifmib_metrics("switch", "") if item["name"] == metric_name)


def _query_bytes(query):
    return len(query.encode("utf-8"))


def _matcher_body(query):
    marker = 'instance_id=~"'
    start = query.find(marker)
    assert start >= 0
    start += len(marker)
    end = query.find('"', start)
    return query[start:end]


def _id_count(query):
    return _matcher_body(query).count("|") + 1


def test_cpu_and_memory_bindings_cover_only_the_five_detail_objects():
    bindings = load_network_device_detail_metrics()
    assert {object_name for object_name, _metric_name in bindings} == set(CPU_MEMORY_OBJECT_NAMES)
    assert {metric_name for _object_name, metric_name in bindings} == {"device_cpu_usage", "device_memory_usage"}


@pytest.mark.parametrize(
    ("object_name", "metric_name", "snippet"),
    [
        ("Switch", "device_cpu_usage", "max("),
        ("Router", "device_cpu_usage", "avg("),
        ("Firewall", "device_cpu_usage", "avg("),
        ("Loadbalance", "device_cpu_usage", "avg("),
        ("Wanopt", "device_cpu_usage", "snmp_device_cpu_usage"),
        ("Switch", "device_memory_usage", "device_memory_usage"),
    ],
)
def test_ranked_gauge_sends_the_detail_capability_unchanged(object_name, metric_name, snippet):
    metric_type = "cpu" if metric_name == "device_cpu_usage" else "memory"
    rows, vm = _run(metric_type, [_device("sw-1", object_name, interval=300)], {"device_": [_point("sw-1", 12.5)]})
    template = _binding(object_name, metric_name).template
    expected = join_label_queries(template, build_instance_matcher_groups(("sw-1",), ["instance_id"]))
    assert snippet in template
    assert vm.calls[0][0] == expected
    assert "timestamp(" not in vm.calls[0][0]
    assert vm.calls[0][1]["step"] == "601s"
    assert vm.calls[0][1]["lookback_delta"] == "601s"
    assert rows[0]["value"] == 12.5
    assert rows[0]["unit"] == "percent"
    assert rows[0]["sampled_at"] == NOW.isoformat()


def test_wanopt_cpu_keeps_snmp_before_the_unprefixed_series():
    template = _binding("Wanopt", "device_cpu_usage").template
    assert template.index("snmp_device_cpu_usage") < template.index("device_cpu_usage{")


def test_switch_memory_keeps_the_detail_or_order():
    template = _binding("Switch", "device_memory_usage").template
    positions = [template.index(name) for name in ("device_memory_usage", "device_memory_used", "device_memory_total")]
    assert positions == sorted(positions)


def test_objects_without_a_cpu_or_memory_card_are_absent_and_not_averaged():
    devices = [_device(f"dev-{name}", name) for name in NO_CARD_OBJECTS]
    devices.append(_device("probe-1", "Probe"))
    for metric_type in ("cpu", "memory"):
        rows, vm = _run(metric_type, devices, {"__name__": [_point("dev-Wireless", 88)]})
        assert rows == []
        assert vm.calls == []


def test_incomplete_identity_is_not_queried_by_its_first_segment():
    device = _device(("collector", "ap-1"), "Switch", keys=("instance_id", "resource_id"))
    rows, vm = _run("cpu", [device], {"device_cpu_usage": [_point("collector", 70)]})
    assert rows == []
    assert vm.calls == []
    assert "collector" not in "".join(query for query, _kwargs in vm.calls)


def test_gauge_lookback_is_two_intervals_plus_one_second_for_each_device():
    devices = [
        _device("fast", "Switch", interval=60),
        _device("normal", "Router", interval=300),
        _device("slow", "Firewall", interval=600),
        _device("unset", "Loadbalance", interval=None),
        _device("illegal", "Wanopt", interval="soon"),
    ]
    _rows, vm = _run("cpu", devices, {})
    windows = {call[1]["step"] for call in vm.calls}
    assert windows == {"121s", "601s", "1201s"}
    assert all(call[1]["lookback_delta"] == call[1]["step"] for call in vm.calls)
    assert gauge_search_window_seconds(60) == 121
    assert gauge_search_window_seconds(300) == 601
    assert collection_interval_seconds("soon") == 300
    assert collection_interval_seconds(0) == 300


def test_traffic_uses_the_public_ifmib_or_then_sum_and_raw_timestamp_gate():
    incoming = _catalog("device_total_incoming_traffic")
    outgoing = _catalog("device_total_outgoing_traffic")
    assert incoming.startswith("sum(rate(interface_ifHCInOctets")
    assert "or rate(interface_ifInOctets" in incoming
    assert "[5m]" in incoming and "[15m]" not in incoming
    assert outgoing.startswith("sum(rate(interface_ifHCOutOctets")
    rows, vm = _run(
        "traffic",
        [_device("sw-1", "Switch", interval=60)],
        {
            "ifHCInOctets": [_point("sw-1", 10)],
            "ifHCOutOctets": [_point("sw-1", 5)],
        },
    )
    queries = [query for query, _kwargs in vm.calls]
    assert queries[0].startswith("sum((rate(interface_ifHCInOctets") or queries[0].startswith("sum(rate(interface_ifHCInOctets")
    assert "interface_ifInOctets" in queries[0]
    assert "or" in queries[0]
    assert "timestamp(" in queries[0] and "ignoring(__name__)" in queries[0] and "[5m]" in queries[0]
    assert "interface_ifHCOutOctets" in queries[1] and "interface_ifOutOctets" in queries[1]
    assert "timestamp(" in queries[1] and "[5m]" in queries[1]
    assert all(call[1]["step"] == "300s" and call[1]["lookback_delta"] == "300s" for call in vm.calls)
    assert all(call[1]["time"] == NOW.timestamp() for call in vm.calls)
    assert '__name__="' not in "".join(queries)
    assert "instance_type=" not in "".join(queries)
    assert "[15m]" not in "".join(queries)
    assert rows[0]["value"] == 15.0
    assert rows[0]["unit"] == "byteps"


def test_traffic_lookback_is_the_wider_of_five_minutes_and_two_intervals():
    devices = [
        _device("fast", "Wireless", interval=60),
        _device("normal", "Access", interval=300),
        _device("slow", "Transmission", interval=600),
    ]
    _rows, vm = _run("traffic", devices, {})
    by_window = {}
    for query, kwargs in vm.calls:
        by_window.setdefault(kwargs["step"], set()).add(query)
    assert set(by_window) == {"300s", "601s", "1201s"}
    assert traffic_search_window_seconds(60) == 300
    assert traffic_search_window_seconds(600) == 1201
    fast_query = next(iter(by_window["300s"]))
    assert str(int(NOW.timestamp()) - 120) in fast_query
    slow_query = next(iter(by_window["1201s"]))
    assert str(int(NOW.timestamp()) - 1200) in slow_query


def test_traffic_without_samples_and_multi_key_devices_are_absent():
    devices = [
        _device("silent", "Wireless"),
        _device(("collector", "ap-1"), "Switch", keys=("instance_id", "resource_id")),
        _device("host-1", "Host", type_id="OS"),
    ]
    rows, vm = _run("traffic", devices, {"ifHCInOctets": [_point("collector", 9)]})
    assert rows == []
    sent = "".join(query for query, _kwargs in vm.calls)
    assert "silent" in sent
    assert "collector" not in sent
    assert "host-1" not in sent


def test_unauthorized_instance_is_not_part_of_the_matcher_and_rows_stay_sorted():
    devices = [
        _device("sw-1", "Switch", name="B"),
        _device("host-1", "Host", type_id="OS", name="secret-1"),
    ]
    rows, vm = _run("cpu", devices, {"device_cpu_usage": [_point("sw-1", 3)]})
    assert "secret-1" not in vm.calls[0][0]
    assert "sw\\\\-1" in vm.calls[0][0]
    assert [row["instance_id"] for row in rows] == ["sw-1"]


def test_ranking_sorts_before_rounding_and_keeps_the_existing_fields():
    devices = [
        _device("a", "Switch", name="A"),
        _device("b", "Switch", name="B"),
        _device("c", "Switch", name="A"),
    ]
    rows, _vm = _run(
        "cpu",
        devices,
        {"device_cpu_usage": [_point("a", 10.126), _point("b", 10.126), _point("c", 2)]},
    )
    assert [row["instance_id"] for row in rows] == ["a", "b", "c"]
    assert rows[0]["value"] == 10.13
    assert list(rows[0]) == [
        "rank",
        "display_name",
        "ip",
        "instance_id",
        "device_type",
        "value",
        "unit",
        "sampled_at",
    ]


def _huawei_ids(count):
    return [f"dc01_switch_snmp_huawei_{index:08d}" for index in range(count)]


def test_switch_memory_long_ids_are_split_on_utf8_bytes():
    for count in (33, 34):
        devices = [_device(instance_id, "Switch") for instance_id in _huawei_ids(count)]
        _rows, vm = _run("memory", devices, {})
        assert vm.calls
        assert all(_query_bytes(query) <= LOCAL_QUERY_BYTE_BUDGET for query, _kwargs in vm.calls)
        assert len(vm.calls) > 1
        assert sum(_id_count(query) for query, _kwargs in vm.calls) == count
        assert all(call[1]["step"] == "601s" and call[1]["lookback_delta"] == "601s" and call[1]["time"] == NOW.timestamp() for call in vm.calls)


def test_two_hundred_short_ids_stay_together_and_the_next_id_starts_a_new_batch():
    short = [f"a{index:03d}" for index in range(200)]
    _rows, vm = _run("cpu", [_device(instance_id, "Switch") for instance_id in short], {})
    assert len(vm.calls) == 1
    assert _id_count(vm.calls[0][0]) == 200
    assert _query_bytes(vm.calls[0][0]) <= LOCAL_QUERY_BYTE_BUDGET

    wider = short + ["a200"]
    _rows, vm = _run("cpu", [_device(instance_id, "Switch") for instance_id in wider], {})
    assert sorted(_id_count(query) for query, _kwargs in vm.calls) == [1, 200]
    assert all(_query_bytes(query) <= LOCAL_QUERY_BYTE_BUDGET for query, _kwargs in vm.calls)


def test_unicode_ids_are_budgeted_as_utf8_bytes():
    devices = [_device(f"测{index:03d}" + ("测" * 80), "Switch") for index in range(8)]
    _rows, vm = _run("memory", devices, {})
    assert len(vm.calls) > 1
    assert len(devices) <= 200
    assert all(_query_bytes(query) <= LOCAL_QUERY_BYTE_BUDGET for query, _kwargs in vm.calls)
    assert any(len(query) < _query_bytes(query) for query, _kwargs in vm.calls)


def test_regex_metacharacters_are_escaped_before_the_byte_budget():
    devices = [_device(f"a.b|c({index:03d})" + ("x" * 40), "Switch") for index in range(40)]
    _rows, vm = _run("memory", devices, {})
    sent = "".join(query for query, _kwargs in vm.calls)
    assert "a\\\\.b\\\\|c\\\\(" in sent
    assert "a.b|c(" not in sent
    assert len(vm.calls) > 1
    assert all(_query_bytes(query) <= LOCAL_QUERY_BYTE_BUDGET for query, _kwargs in vm.calls)


def test_traffic_batches_follow_the_larger_direction_and_keep_the_raw_timestamp_gate():
    devices = [_device(instance_id, "Wireless") for instance_id in _huawei_ids(140)]
    _rows, vm = _run("traffic", devices, {})
    assert len(vm.calls) > 2
    assert len(vm.calls) % 2 == 0
    times = set()
    for index in range(0, len(vm.calls), 2):
        incoming, in_kwargs = vm.calls[index]
        outgoing, out_kwargs = vm.calls[index + 1]
        assert _matcher_body(incoming) == _matcher_body(outgoing)
        assert _query_bytes(incoming) <= LOCAL_QUERY_BYTE_BUDGET
        assert _query_bytes(outgoing) <= LOCAL_QUERY_BYTE_BUDGET
        assert "timestamp(" in incoming and "timestamp(" in outgoing
        assert "[5m]" in incoming and "[5m]" in outgoing
        assert "ignoring(__name__)" in incoming and "ignoring(__name__)" in outgoing
        assert in_kwargs["step"] == out_kwargs["step"] == "601s"
        assert in_kwargs["lookback_delta"] == out_kwargs["lookback_delta"] == "601s"
        times.add(in_kwargs["time"])
        times.add(out_kwargs["time"])
    assert times == {NOW.timestamp()}


def test_rank_deadline_does_not_return_a_partial_board():
    class SlowVM:
        def __init__(self):
            self.calls = []

        def query(self, query, **kwargs):
            self.calls.append(query)
            time.sleep(0.3)
            return {"status": "success", "data": {"result": [_point("a000", 50)]}}

    vm = SlowVM()
    devices = [_device(f"a{index:03d}", "Switch", name=f"n{index:03d}") for index in range(201)]
    with pytest.raises(RuntimeError, match="网络设备资源指标查询失败"):
        NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run("cpu", devices, deadline=time.monotonic() + 0.2)
    assert len(vm.calls) == 1

    idle = FakeVM({})
    with pytest.raises(RuntimeError, match="网络设备资源指标查询失败"):
        NetworkDeviceResourceTopService(vm_api=idle, now=NOW).run(
            "cpu",
            [_device("sw-1", "Switch")],
            deadline=time.monotonic() - 1,
        )
    assert idle.calls == []


def test_a_high_value_in_a_later_batch_still_wins_the_global_top():
    ids = [f"a{index:03d}" for index in range(201)]
    points = [_point(instance_id, 1) for instance_id in ids]
    points[-1] = _point("a200", 99)
    rows, vm = _run("cpu", [_device(instance_id, "Switch", name=instance_id) for instance_id in ids], {"device_cpu_usage": points})
    assert len(vm.calls) >= 2
    assert rows[0]["instance_id"] == "a200"
    assert rows[0]["value"] == 99.0
    assert len(rows) == 10


def test_a_later_batch_failure_does_not_return_a_partial_board():
    class BoomVM:
        def __init__(self):
            self.calls = []

        def query(self, query, **kwargs):
            self.calls.append(query)
            if len(self.calls) > 1:
                raise RuntimeError("vm failed SECRET-DEVICE-9 max(device_memory_usage{instance_id")
            return {"status": "success", "data": {"result": [_point("a000", 4)]}}

    vm = BoomVM()
    devices = [_device(f"a{index:03d}", "Switch") for index in range(201)]
    with pytest.raises(RuntimeError) as caught:
        NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run("cpu", devices)
    assert "SECRET-DEVICE-9" not in str(caught.value)
    assert "device_memory_usage" not in str(caught.value)
    assert len(vm.calls) >= 1


def test_one_oversized_id_sends_nothing_even_when_only_a_later_group_overflows(caplog):
    huge = "SECRET-HUGE-" + ("x" * 4000)
    devices = [
        _device("sw-1", "Switch", interval=300),
        _device(huge, "Switch", interval=60),
    ]
    vm = FakeVM({})
    with caplog.at_level(logging.ERROR, logger="monitor"):
        with pytest.raises(RuntimeError) as caught:
            NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run("memory", devices)
    assert vm.calls == []
    assert type(caught.value) is RuntimeError
    assert str(caught.value) == "网络设备资源指标查询失败"
    assert "SECRET-HUGE" not in str(caught.value)
    assert caplog.records == []
    rendered = "".join(traceback.format_exception(caught.value))
    assert "_pack_rendered" in rendered
    assert "failed_stage=single_query_over_budget" in rendered
    assert "metric_type=memory" in rendered
    assert "budget_bytes=16128" in rendered
    assert "query_bytes=" in rendered
    assert "SECRET-HUGE" not in rendered
    assert "max(" not in rendered


def test_signature_fallback_cannot_drop_step_and_lookback():
    class KwargsOnly:
        def __init__(self):
            self.calls = []

        def query(self, query, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise TypeError("step")
            return {"status": "success", "data": {"result": [_point("sw-1", 9)]}}

    vm = KwargsOnly()
    with pytest.raises(TypeError):
        NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run("cpu", [_device("sw-1", "Switch")])
    assert len(vm.calls) == 1
    assert vm.calls[0]["step"] == "601s"


def test_negative_gauge_values_stay_in_the_ranking():
    rows, _vm = _run("cpu", [_device("sw-1", "Switch")], {"device_cpu_usage": [_point("sw-1", -3.5)]})
    assert rows[0]["value"] == -3.5


def test_result_timestamp_is_stored_as_sampled_at_without_a_python_age_filter():
    stale_point = datetime(2026, 7, 22, 11, tzinfo=timezone.utc)
    rows, _vm = _run("cpu", [_device("sw-1", "Switch", interval=60)], {"device_cpu_usage": [_point("sw-1", 4, stale_point)]})
    assert rows[0]["sampled_at"] == stale_point.isoformat()
    ranked = build_ranked_rows([], {}, limit=10)
    assert ranked == []
