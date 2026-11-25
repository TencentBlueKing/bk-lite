"""脚本序列隔离：原生查询排除脚本点，脚本指标收窄到本模板。

排除必须写在选择器里。包成 `(a unless b)` 再拼区间会变成子查询，
changes / deriv 这类逐序列汇聚的结果会变。
"""

from types import SimpleNamespace

import pytest

from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.tasks.utils.policy_methods import compile_policy_query
from apps.monitor.utils.script_series_isolation import (
    exclude_script_series,
    isolate_metric_query,
    isolate_status_timestamp_query,
    scope_to_script_plugin,
)

NATIVE = SimpleNamespace(monitor_plugin=SimpleNamespace(collect_type="host", template_type="builtin", template_id="host"))
SCRIPT = SimpleNamespace(monitor_plugin=SimpleNamespace(collect_type="script", template_type="script", template_id="tpl-1"))


def test_native_selector_gets_a_not_script_matcher():
    assert exclude_script_series('cpu{instance_type="os"}') == 'cpu{instance_type="os", collect_type!="script"}'
    assert exclude_script_series("cpu{}") == 'cpu{collect_type!="script"}'
    assert "unless" not in exclude_script_series('rate(a{x="1"}[5m]) / b{x="1"}')


def test_selector_that_already_filters_collect_type_is_left_alone():
    query = "snmp_uptime{instance_type='switch', collect_type='snmp'}"
    assert exclude_script_series(query) == query


def test_braces_inside_strings_are_not_selectors():
    query = 'http_requests{path=~"/v[0-9]{1,2}/.*"}'
    assert exclude_script_series(query) == 'http_requests{path=~"/v[0-9]{1,2}/.*", collect_type!="script"}'
    replaced = 'label_replace(up{job="a"}, "dst", "{$1}", "src", "(.*)")'
    assert exclude_script_series(replaced) == 'label_replace(up{job="a", collect_type!="script"}, "dst", "{$1}", "src", "(.*)")'


def test_script_metric_is_scoped_to_its_template():
    assert scope_to_script_plugin("conn{}", "tpl-1") == 'conn{collect_type="script", plugin_id="tpl-1"}'
    assert isolate_metric_query('conn{instance_id="h1"}', SCRIPT) == 'conn{instance_id="h1", collect_type="script", plugin_id="tpl-1"}'
    assert isolate_metric_query('conn{instance_id="h1"}', NATIVE) == 'conn{instance_id="h1", collect_type!="script"}'


def test_status_query_excludes_script_before_taking_sample_time():
    assert (
        isolate_status_timestamp_query("any({instance_type='os'}) by (instance_id)")
        == "max(tlast_over_time(({instance_type='os', collect_type!=\"script\"})[20m])) by (instance_id)"
    )


@pytest.mark.parametrize("algorithm", ["changes", "deriv", "rate"])
def test_per_series_alert_keeps_a_raw_range_selector(algorithm):
    base = compile_filter_to_query(
        'net_bytes_recv{instance_type="os", __$labels__}',
        [{"name": "instance_id", "method": "=", "value": "h1"}],
        metric=NATIVE,
    )
    policy = {"algorithm": algorithm, "group_algorithm": "avg", "query_condition": {"type": "metric"}, "compare_mode": "absolute"}
    query = compile_policy_query(policy, base, "5m", "instance_id")
    assert query == (f'avg({algorithm}(net_bytes_recv{{instance_type="os", instance_id="h1", collect_type!="script"}}[5m])) by (instance_id)')
