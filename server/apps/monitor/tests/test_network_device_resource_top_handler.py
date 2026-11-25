import logging
import time
import traceback
from types import SimpleNamespace

from apps.monitor.nats import monitor as nm

SENTINEL_ID = "SECRET-DEVICE-9"
SENTINEL_URL = "http://vm.secret.example/api/v1/query"
SENTINEL_PROMQL = 'max(device_cpu_usage{instance_id=~"SECRET-DEVICE-9"'
DIAGNOSTIC_FIELDS = (
    "metric_type=",
    "failed_stage=",
    "chunk_count=",
    "query_bytes=",
    "budget_bytes=16128",
    "error_type=",
)


def _switch(instance_id, interval=300):
    return SimpleNamespace(
        id=instance_id,
        name="Switch A",
        ip="10.0.0.1",
        interval=interval,
        monitor_object=SimpleNamespace(name="Switch", type_id="Network Device", instance_id_keys=["instance_id"]),
    )


def _authorize(monkeypatch, instances, vm):
    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", lambda user_info, scope_ids: (instances, None))
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: vm)


def _raise_sensitive(message):
    raise RuntimeError(message)


def _business_errors(records):
    return [record for record in records if record.levelno >= logging.ERROR and record.name in {"nats", "monitor"}]


def _exception_chain(error):
    chain = []
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ if current.__cause__ is not None else (None if current.__suppress_context__ else current.__context__)
    return chain


def _assert_one_business_error(caplog, *, sentinels, diagnostics, origin_name):
    errors = _business_errors(caplog.records)
    assert len(errors) == 1
    record = errors[0]
    assert record.name == "nats"
    assert record.exc_info is not None
    formatted = logging.Formatter().format(record)
    frames = []
    tb = record.exc_info[2]
    while tb is not None:
        frames.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    assert origin_name in frames
    assert origin_name in formatted
    chain = _exception_chain(record.exc_info[1])
    chain_text = []
    for item in chain:
        chain_text.append("".join(traceback.format_exception(item)))
        chain_text.extend(str(arg) for arg in item.args)
        chain_text.extend(getattr(item, "__notes__", []))
    inspected = "\n".join([str(record.msg), str(record.args), record.getMessage(), formatted, "\n".join(chain_text)])
    for token in sentinels:
        assert token not in inspected
    for field in diagnostics:
        assert field in formatted
    assert record.exc_info[1].__cause__ is None
    assert record.exc_info[1].__context__ is None


def test_network_device_resource_top_handler_returns_ranked_traffic(monkeypatch):
    instance = SimpleNamespace(
        id="sw-1",
        name="Switch A",
        ip="10.0.0.1",
        interval=300,
        monitor_object=SimpleNamespace(name="Switch", type_id="Network Device"),
    )
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: ({"sw-1": instance}, None),
    )

    class FakeVM:
        def __init__(self):
            self.queries = []

        def query(self, query, **kwargs):
            self.queries.append(query)
            if "ifHCInOctets" in query:
                value = "10"
            elif "ifHCOutOctets" in query:
                value = "5"
            else:
                return {"status": "success", "data": {"result": []}}
            assert "sw\\\\-1" in query
            assert "secret-1" not in query
            assert "[5m]" in query
            assert "[15m]" not in query
            assert "and ignoring(__name__)" in query
            assert '__name__="device_total_' not in query
            return {"status": "success", "data": {"result": [{"metric": {"instance_id": "sw-1"}, "value": [time.time(), value]}]}}

    fake_vm = FakeVM()
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: fake_vm)
    out = nm.get_network_device_resource_top("traffic", user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert out["data"][0]["value"] == 15.0
    assert out["data"][0]["device_type"] == "Switch"
    assert out["data"][0]["unit"] == "byteps"


def test_network_device_resource_top_handler_rejects_invalid_type(monkeypatch):
    out = nm.get_network_device_resource_top("disk", user_info={"user": "u", "team": 1})
    assert out["result"] is False


def test_network_device_resource_top_handler_rejects_invalid_limit(monkeypatch):
    out = nm.get_network_device_resource_top("cpu", limit=101, user_info={"user": "u", "team": 1})
    assert out["result"] is False


def test_handler_logs_one_error_when_a_later_group_exceeds_the_budget(monkeypatch, caplog):
    huge = "SECRET-HUGE-" + ("x" * 4000)
    vm = SimpleNamespace(calls=[])

    def query(query_text, **kwargs):
        vm.calls.append(query_text)
        raise AssertionError("budget failure must not reach VM")

    vm.query = query
    _authorize(monkeypatch, {"sw-1": _switch("sw-1", 300), "huge": _switch(huge, 60)}, vm)
    with caplog.at_level(logging.ERROR):
        out = nm.get_network_device_resource_top("memory", user_info={"user": "u", "team": 1})
    assert vm.calls == []
    assert out == {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
    _assert_one_business_error(
        caplog,
        sentinels=("SECRET-HUGE", "max(", huge),
        diagnostics=DIAGNOSTIC_FIELDS
        + ("metric_type=memory", "failed_stage=single_query_over_budget", "chunk_count=0", "error_type=QueryBudgetExceeded"),
        origin_name="_pack_rendered",
    )


def test_handler_logs_one_error_when_a_later_batch_fails(monkeypatch, caplog):
    message = " ".join((SENTINEL_URL, SENTINEL_ID, SENTINEL_PROMQL))
    kept = []
    vm = SimpleNamespace(calls=[])

    def query(query_text, **kwargs):
        vm.calls.append(query_text)
        if len(vm.calls) > 1:
            try:
                _raise_sensitive(message)
            except RuntimeError as exc:
                kept.append(exc)
                raise
        return {"status": "success", "data": {"result": [{"metric": {"instance_id": "a000"}, "value": [time.time(), "4"]}]}}

    vm.query = query
    instances = {f"a{index:03d}": _switch(f"a{index:03d}") for index in range(201)}
    _authorize(monkeypatch, instances, vm)
    with caplog.at_level(logging.ERROR):
        out = nm.get_network_device_resource_top("cpu", user_info={"user": "u", "team": 1})
    assert len(vm.calls) >= 2
    assert out == {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
    assert kept[0].args == (message,)
    _assert_one_business_error(
        caplog,
        sentinels=(SENTINEL_URL, SENTINEL_ID, SENTINEL_PROMQL, "device_cpu_usage"),
        diagnostics=DIAGNOSTIC_FIELDS + ("metric_type=cpu", "failed_stage=query_chunk", "chunk_count=2", "error_type=RuntimeError"),
        origin_name="_raise_sensitive",
    )


def test_handler_logs_one_error_when_the_outgoing_direction_fails(monkeypatch, caplog):
    message = " ".join((SENTINEL_URL, SENTINEL_ID, "interface_ifHCOutOctets"))
    kept = []
    vm = SimpleNamespace(calls=[])

    def query(query_text, **kwargs):
        vm.calls.append(query_text)
        if "ifHCOutOctets" in query_text or "ifOutOctets" in query_text:
            try:
                _raise_sensitive(message)
            except RuntimeError as exc:
                kept.append(exc)
                raise
        return {"status": "success", "data": {"result": [{"metric": {"instance_id": "sw-1"}, "value": [time.time(), "10"]}]}}

    vm.query = query
    _authorize(monkeypatch, {"sw-1": _switch("sw-1")}, vm)
    with caplog.at_level(logging.ERROR):
        out = nm.get_network_device_resource_top("traffic", user_info={"user": "u", "team": 1})
    assert len(vm.calls) >= 1
    assert out == {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
    assert kept[0].args == (message,)
    _assert_one_business_error(
        caplog,
        sentinels=(SENTINEL_URL, SENTINEL_ID, "interface_ifHCOutOctets"),
        diagnostics=DIAGNOSTIC_FIELDS
        + ("metric_type=traffic", "failed_stage=query_chunk", "direction=device_total_outgoing_traffic", "error_type=RuntimeError"),
        origin_name="_raise_sensitive",
    )
