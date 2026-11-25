"""Query-semantics checks against a disposable VictoriaMetrics.

Skipped unless BKLITE_VM_RANK_URL points at an isolated server. The samples are
explicit test series. This does not prove the product deployment.
"""

import json
import os
import time
import urllib.parse
import urllib.request

import pytest

from apps.monitor.services.network_device_resource_top import (
    build_device_total_rate_query,
    gauge_search_window_seconds,
    traffic_search_window_seconds,
)

pytestmark = pytest.mark.skipif(not os.environ.get("BKLITE_VM_RANK_URL"), reason="BKLITE_VM_RANK_URL is not set")

VM_URL = os.environ.get("BKLITE_VM_RANK_URL", "").rstrip("/")
PROBE = "ranking-semantics-pytest"


def _ms(timestamp):
    return int(timestamp * 1000)


def _import(lines):
    body = "\n".join(lines).encode()
    request = urllib.request.Request(f"{VM_URL}/api/v1/import/prometheus", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 204
    # Import returns before the index used by /api/v1/query can see the rows.
    flush = urllib.request.Request(f"{VM_URL}/internal/force_flush", method="GET")
    with urllib.request.urlopen(flush, timeout=10) as response:
        assert response.status == 200


def _sample(name, instance_id, value, timestamp, **labels):
    merged = {"instance_id": instance_id, "probe": PROBE, **labels}
    rendered = ",".join(f'{key}="{merged[key]}"' for key in sorted(merged))
    return f"{name}{{{rendered}}} {value} {_ms(timestamp)}"


def _query(query, step):
    params = urllib.parse.urlencode({"query": query, "time": str(EVAL), "step": step, "nocache": "1"})
    with urllib.request.urlopen(f"{VM_URL}/api/v1/query?{params}", timeout=10) as response:
        payload = json.loads(response.read().decode())
    assert payload["status"] == "success"
    return payload["data"]["result"]


def _value(result):
    assert len(result) == 1
    return float(result[0]["value"][1])


EVAL = int(time.time()) - 30


def _id(name):
    return f"{name}-{EVAL}"


@pytest.fixture(scope="module")
def vm_samples():
    interval_cases = {
        60: (EVAL - 120, EVAL - 121),
        300: (EVAL - 600, EVAL - 601),
        600: (EVAL - 1200, EVAL - 1201),
    }
    lines = []
    for interval, (edge, over) in interval_cases.items():
        lines.append(_sample("vmtest_cpu", _id(f"vmtest-i{interval}-edge"), 5, edge, descr="eq"))
        lines.append(_sample("vmtest_cpu", _id(f"vmtest-i{interval}-over"), 6, over, descr="plus1"))
    lines.append(_sample("vmtest_cpu", _id("vmtest-mix"), 10, EVAL - 60, descr="fresh"))
    lines.append(_sample("vmtest_cpu", _id("vmtest-mix"), 99, EVAL - 700, descr="stale"))
    lines.append(_sample("vmtest_cpu", _id("vmtest-avg"), 80, EVAL - 60, descr="fresh"))
    lines.append(_sample("vmtest_cpu", _id("vmtest-avg"), 10, EVAL - 720, descr="stale"))
    lines.append(_sample("vmtest_cpu_plain", _id("vmtest-or"), 99, EVAL - 700))
    lines.append(_sample("vmtest_cpu_snmp", _id("vmtest-or"), 40, EVAL - 30))
    lines.append(_sample("vmtest_cpu_plain", _id("vmtest-or2"), 70, EVAL - 20))
    lines.append(_sample("vmtest_cpu_snmp", _id("vmtest-or2"), 40, EVAL - 30))
    lines += [
        _sample("interface_ifHCInOctets", _id("vmtest-traffic"), 1000, EVAL - 240, ifDescr="eth0"),
        _sample("interface_ifHCInOctets", _id("vmtest-traffic"), 2200, EVAL - 30, ifDescr="eth0"),
        _sample("interface_ifInOctets", _id("vmtest-traffic"), 500, EVAL - 240, ifDescr="eth1"),
        _sample("interface_ifInOctets", _id("vmtest-traffic"), 1100, EVAL - 30, ifDescr="eth1"),
        _sample("interface_ifHCInOctets", _id("vmtest-traffic"), 0, EVAL - 240, ifDescr="eth2"),
        _sample("interface_ifHCInOctets", _id("vmtest-traffic"), 4200, EVAL - 30, ifDescr="eth2"),
        _sample("interface_ifInOctets", _id("vmtest-traffic"), 0, EVAL - 240, ifDescr="eth2"),
        _sample("interface_ifInOctets", _id("vmtest-traffic"), 21000, EVAL - 30, ifDescr="eth2"),
        _sample("interface_ifHCInOctets", _id("vmtest-stopped"), 0, EVAL - 280, ifDescr="eth0"),
        _sample("interface_ifHCInOctets", _id("vmtest-stopped"), 5000, EVAL - 180, ifDescr="eth0"),
        _sample("interface_ifHCInOctets", _id("vmtest-partial"), 0, EVAL - 200, ifDescr="up"),
        _sample("interface_ifHCInOctets", _id("vmtest-partial"), 1000, EVAL - 20, ifDescr="up"),
        _sample("interface_ifHCInOctets", _id("vmtest-partial"), 0, EVAL - 400, ifDescr="old"),
        _sample("interface_ifHCInOctets", _id("vmtest-partial"), 9000, EVAL - 250, ifDescr="old"),
        _sample("interface_ifHCInOctets", _id("vmtest-edge"), 0, EVAL - 180, ifDescr="eth0"),
        _sample("interface_ifHCInOctets", _id("vmtest-edge"), 600, EVAL - 120, ifDescr="eth0"),
    ]
    _import(lines)
    return True


def test_gauge_lookback_keeps_the_two_interval_boundary(vm_samples):
    for interval in (60, 300, 600):
        window = f"{gauge_search_window_seconds(interval)}s"
        short = f"{2 * interval}s"
        edge = _query(f'timestamp(vmtest_cpu{{instance_id="{_id(f"vmtest-i{interval}-edge")}"}})', window)
        dropped = _query(f'timestamp(vmtest_cpu{{instance_id="{_id(f"vmtest-i{interval}-edge")}"}})', short)
        over = _query(f'timestamp(vmtest_cpu{{instance_id="{_id(f"vmtest-i{interval}-over")}"}})', window)
        assert _value(edge) == EVAL - 2 * interval
        assert edge[0]["value"][0] == EVAL
        assert dropped == []
        assert over == []


def test_stale_series_cannot_change_max_or_avg(vm_samples):
    window = f"{gauge_search_window_seconds(300)}s"
    fresh_max = _query(f'max(vmtest_cpu{{instance_id="{_id("vmtest-mix")}"}}) by (instance_id)', window)
    wide_max = _query(f'max(vmtest_cpu{{instance_id="{_id("vmtest-mix")}"}}) by (instance_id)', "15m")
    fresh_avg = _query(f'avg(vmtest_cpu{{instance_id="{_id("vmtest-avg")}"}}) by (instance_id)', window)
    wide_avg = _query(f'avg(vmtest_cpu{{instance_id="{_id("vmtest-avg")}"}}) by (instance_id)', "15m")
    assert _value(fresh_max) == 10
    assert _value(wide_max) == 99
    assert _value(fresh_avg) == 80
    assert _value(wide_avg) == 45


def test_or_keeps_fresh_snmp_and_prefers_the_left_side(vm_samples):
    window = f"{gauge_search_window_seconds(300)}s"
    stale_left = (
        f'max(vmtest_cpu_plain{{instance_id="{_id("vmtest-or")}"}}) by (instance_id) '
        f'or max(vmtest_cpu_snmp{{instance_id="{_id("vmtest-or")}"}}) by (instance_id)'
    )
    both_fresh = (
        f'max(vmtest_cpu_plain{{instance_id="{_id("vmtest-or2")}"}}) by (instance_id) '
        f'or max(vmtest_cpu_snmp{{instance_id="{_id("vmtest-or2")}"}}) by (instance_id)'
    )
    assert _value(_query(stale_left, window)) == 40
    assert _value(_query(stale_left, "15m")) == 99
    assert _value(_query(both_fresh, window)) == 70


def test_catalog_rate_shape_differs_from_sum_then_or_and_honors_raw_age(vm_samples):
    matcher = f'instance_id="{_id("vmtest-traffic")}"'
    cutoff = str(EVAL - 120)
    catalog = build_device_total_rate_query("device_total_incoming_traffic", matcher, cutoff)
    dashboard = (
        f"(sum(rate(interface_ifHCInOctets{{{matcher}}}[5m])) by (instance_id)) "
        f"or (sum(rate(interface_ifInOctets{{{matcher}}}[5m])) by (instance_id))"
    )
    window = f"{traffic_search_window_seconds(60)}s"
    assert _value(_query(catalog, window)) == pytest.approx(1200 / 210 + 600 / 210 + 4200 / 210)
    assert _value(_query(dashboard, "5m")) == pytest.approx(1200 / 210 + 4200 / 210)

    stopped = build_device_total_rate_query("device_total_incoming_traffic", f'instance_id="{_id("vmtest-stopped")}"', cutoff)
    ungated = f'sum(rate(interface_ifHCInOctets{{instance_id="{_id("vmtest-stopped")}"}}[5m])) by (instance_id)'
    assert _query(stopped, window) == []
    assert _value(_query(ungated, window)) == pytest.approx(50)

    partial = build_device_total_rate_query("device_total_incoming_traffic", f'instance_id="{_id("vmtest-partial")}"', cutoff)
    assert _value(_query(partial, window)) == pytest.approx(1000 / 180)
    exact = build_device_total_rate_query("device_total_incoming_traffic", f'instance_id="{_id("vmtest-edge")}"', str(EVAL - 120))
    newer = build_device_total_rate_query("device_total_incoming_traffic", f'instance_id="{_id("vmtest-edge")}"', str(EVAL - 119))
    assert _value(_query(exact, "5m")) == pytest.approx(10)
    assert _query(newer, "5m") == []
