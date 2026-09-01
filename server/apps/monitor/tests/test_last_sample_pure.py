"""列表上报时间必须取最后一条原始样本，而不是即时查询求值时刻。"""

import pytest

from apps.monitor.utils.last_sample import last_sample_timestamp_query, last_sample_unix_seconds

pytestmark = pytest.mark.unit


def test_rewrites_any_by_selector_to_tlast_over_time():
    assert last_sample_timestamp_query("any({instance_type='os'}) by (instance_id)") == (
        "max(tlast_over_time(({instance_type='os'})[20m])) by (instance_id)"
    )


def test_rewrites_count_by_selector_and_keeps_multi_key_group():
    query = 'count(kube_node_info{instance_type="k3s"}) by (instance_id, node)'
    assert last_sample_timestamp_query(query) == (
        'max(tlast_over_time((kube_node_info{instance_type="k3s"})[20m])) by (instance_id, node)'
    )


def test_rewrites_metric_selector_inside_any_by():
    query = (
        "any(http_response_result_type{instance_type='web', collect_type='web', result='success'}) "
        "by (instance_id)"
    )
    assert last_sample_timestamp_query(query) == (
        "max(tlast_over_time((http_response_result_type{instance_type='web', collect_type='web', "
        "result='success'})[20m])) by (instance_id)"
    )


def test_wraps_raw_selector_without_changing_lookback_twice():
    rewritten = last_sample_timestamp_query("up")
    assert rewritten == "tlast_over_time((up)[20m])"
    assert last_sample_timestamp_query(rewritten) == rewritten


def test_reads_sample_timestamp_from_value_not_evaluation_time():
    sample = {"value": [1_782_888_110, "1782887860"]}
    assert last_sample_unix_seconds(sample) == 1_782_887_860


@pytest.mark.parametrize(
    "sample",
    [
        None,
        {},
        {"value": [1_782_888_110]},
        {"value": [1_782_888_110, "1"]},
        {"value": [1_782_888_110, "not-a-time"]},
    ],
)
def test_rejects_evaluation_time_and_metric_values(sample):
    assert last_sample_unix_seconds(sample) is None
