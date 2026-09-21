import pytest

from apps.monitor.services.metric_query_contract import build_instance_matcher_groups, join_label_queries

pytestmark = pytest.mark.unit


def test_multi_key_matchers_keep_instance_tuples():
    groups = build_instance_matcher_groups(
        ("('host-a', 'nginx')", "('host-b', 'postgres')"),
        ["instance_id", "process_name"],
    )
    query = join_label_queries("process_cpu{__$labels__}", groups)

    assert 'instance_id="host-a", process_name="nginx"' in query
    assert 'instance_id="host-b", process_name="postgres"' in query
    assert " or " in query
    assert 'instance_id=~' not in query
    assert 'process_name=~' not in query


def test_single_key_matchers_keep_regex_union():
    groups = build_instance_matcher_groups(
        ("('host-a',)", "('host-b',)"),
        ["instance_id"],
    )

    assert groups == [['instance_id=~"host\\\\-a|host\\\\-b"']]
