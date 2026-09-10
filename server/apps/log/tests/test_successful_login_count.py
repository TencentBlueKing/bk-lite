"""成功登录计数：采集覆盖判定、stats 合并、NATS handler 与日志契约。"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from apps.log.nats import log as nm
from apps.log.services.log_event_contract import normalize_user_logsql_query, to_storage_query
from apps.log.services.successful_login_count import (
    LINUX_SUCCESS_LOGIN_QUERY,
    WINDOWS_SUCCESS_LOGIN_QUERY,
    build_host_match_clause,
    classify_login_coverage,
    merge_login_counts,
)
from apps.log.utils.log_group import LogGroupQueryBuilder

pytestmark = pytest.mark.unit

RFC3339_TIME_RANGE = (
    "2026-08-03T04:17:25.000Z",
    "2026-08-03T05:17:25.000Z",
)

SECRET_SENTINEL = "credential-sentinel-do-not-log"
USER_INFO = {"user": "ops", "domain": "default", "team": 1, "include_children": False}


def _fake_instance_qs(mocker, instances):
    qs = mocker.MagicMock()
    qs.select_related.return_value = list(instances)
    return qs


def _map_log_group_scope(query, _user_info):
    return to_storage_query(normalize_user_logsql_query(query))


def _assert_host_clause(query: str, host_name: str, ip: str):
    quoted_name = json.dumps(host_name)
    quoted_ip = json.dumps(ip)
    assert f"host:{quoted_name}" in query
    assert f"hostname:{quoted_name}" in query
    assert f"host:{quoted_ip}" in query
    assert f"hostname:{quoted_ip}" in query


def _query_limit(call) -> int:
    if len(call.args) > 3:
        return call.args[3]
    return call.kwargs["limit"]


# ----------------------- classify / merge -----------------------


def test_no_collect_instance_is_uncollected():
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    out = classify_login_coverage(hosts, collect_instances=[])
    assert out[0]["login_status"] == "uncollected"
    assert out[0]["login_count"] is None


def test_winlogbeat_same_node_is_counted_zero_until_stats():
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    covered = classify_login_coverage(hosts, collect_instances=[inst])
    assert covered[0]["login_status"] == "counted"
    merged = merge_login_counts(covered, [{"value": "web-1", "count": 4}])
    assert merged[0]["login_count"] == 4


def test_stats_miss_stays_zero_not_uncollected():
    covered = [{"host_name": "web-1", "ip": "10.0.0.1", "login_status": "counted", "login_count": None}]
    merged = merge_login_counts(covered, [])
    assert merged[0]["login_status"] == "counted"
    assert merged[0]["login_count"] == 0


def test_both_empty_node_id_is_uncollected():
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": ""}]
    inst = SimpleNamespace(node_id="", collect_type=SimpleNamespace(name="winlogbeat"))
    out = classify_login_coverage(hosts, collect_instances=[inst])
    assert out[0]["login_status"] == "uncollected"
    assert out[0]["login_count"] is None

    hosts_none = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": None}]
    inst_none = SimpleNamespace(node_id=None, collect_type=SimpleNamespace(name="winlogbeat"))
    out_none = classify_login_coverage(hosts_none, collect_instances=[inst_none])
    assert out_none[0]["login_status"] == "uncollected"
    assert out_none[0]["login_count"] is None


def test_linux_file_same_node_is_counted():
    hosts = [{"host_name": "lnx-1", "ip": "10.0.0.2", "os_type": "1", "node_id": "n2"}]
    inst = SimpleNamespace(node_id="n2", collect_type=SimpleNamespace(name="file"))
    out = classify_login_coverage(hosts, collect_instances=[inst])
    assert out[0]["login_status"] == "counted"
    assert out[0]["login_count"] is None


def test_linux_filebeat_non_windows_os_is_counted():
    hosts = [{"host_name": "lnx-1", "ip": "10.0.0.2", "os_type": "3", "node_id": "n3"}]
    inst = SimpleNamespace(node_id="n3", collect_type=SimpleNamespace(name="filebeat"))
    out = classify_login_coverage(hosts, collect_instances=[inst])
    assert out[0]["login_status"] == "counted"


def test_merge_matches_hostname_case_insensitive_then_ip():
    covered = [
        {"host_name": "Web-1", "ip": "10.0.0.1", "login_status": "counted", "login_count": None},
        {"host_name": "web-2", "ip": "10.0.0.2", "login_status": "counted", "login_count": None},
    ]
    merged = merge_login_counts(
        covered,
        [
            {"host": "web-1", "entry_count": "3"},
            {"hostname": "10.0.0.2", "entry_count": 7},
        ],
    )
    assert merged[0]["login_count"] == 3
    assert merged[1]["login_count"] == 7


def test_merge_prefers_hostname_over_ip():
    covered = [{"host_name": "web-1", "ip": "10.0.0.1", "login_status": "counted", "login_count": None}]
    merged = merge_login_counts(
        covered,
        [
            {"value": "web-1", "count": 2},
            {"value": "10.0.0.1", "count": 99},
        ],
    )
    assert merged[0]["login_count"] == 2


def test_uncollected_stays_none_after_merge():
    covered = [
        {"host_name": "web-1", "ip": "10.0.0.1", "login_status": "uncollected", "login_count": None},
    ]
    merged = merge_login_counts(covered, [{"value": "web-1", "count": 9}])
    assert merged[0]["login_status"] == "uncollected"
    assert merged[0]["login_count"] is None


def test_query_constants_contain_required_tokens():
    assert "collect_type:winlogbeat" in WINDOWS_SUCCESS_LOGIN_QUERY
    assert "event_id:4624" in WINDOWS_SUCCESS_LOGIN_QUERY
    assert "Accepted password" in LINUX_SUCCESS_LOGIN_QUERY
    assert "Accepted publickey" in LINUX_SUCCESS_LOGIN_QUERY
    assert "session opened" in LINUX_SUCCESS_LOGIN_QUERY
    assert "Failed" in LINUX_SUCCESS_LOGIN_QUERY
    assert "Invalid user" in LINUX_SUCCESS_LOGIN_QUERY


def test_build_host_match_clause_includes_name_and_ip():
    clause = build_host_match_clause([{"host_name": "web-1", "ip": "10.0.0.1"}])
    assert clause == '(host:"web-1" OR hostname:"web-1" OR host:"10.0.0.1" OR hostname:"10.0.0.1")'


def test_build_host_match_clause_quotes_special_chars():
    clause = build_host_match_clause([{"host_name": 'web-"1', "ip": ""}])
    quoted = json.dumps('web-"1')
    assert clause == f"(host:{quoted} OR hostname:{quoted})"


def test_build_host_match_clause_empty_when_no_names():
    assert build_host_match_clause([]) == ""
    assert build_host_match_clause([{"host_name": "", "ip": None}]) == ""
    assert build_host_match_clause([{"host_name": "  ", "ip": ""}]) == ""


# ----------------------- NATS handler -----------------------


def test_hosts_not_list_returns_false(mocker):
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    out = nm.count_successful_logins_by_host("nope", RFC3339_TIME_RANGE)
    assert out["result"] is False
    assert out["data"] == []
    vm.assert_not_called()


def test_empty_hosts_skips_victoria_logs(mocker):
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    auth = mocker.patch.object(nm, "_authorized_log_instances")
    out = nm.count_successful_logins_by_host([], RFC3339_TIME_RANGE)
    assert out == {"result": True, "data": [], "message": ""}
    vm.assert_not_called()
    auth.assert_not_called()


def test_invalid_time_range_returns_false_without_vl(mocker):
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    out = nm.count_successful_logins_by_host(hosts, ["2026-08-03T04:17:25Z"])
    assert out["result"] is False
    assert out["data"] == []
    vm.assert_not_called()


def test_all_uncollected_skips_victoria_logs(mocker):
    mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, []))
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE)
    assert out["result"] is True
    assert out["data"][0]["login_status"] == "uncollected"
    assert out["data"][0]["login_count"] is None
    vm.assert_not_called()


def test_counted_windows_queries_winlogbeat_4624(mocker):
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    auth = mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    scope = mocker.patch.object(nm, "_apply_log_group_scope", side_effect=_map_log_group_scope)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"host": "web-1", "entry_count": "4"}]
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    assert out["data"][0]["login_status"] == "counted"
    assert out["data"][0]["login_count"] == 4
    auth.assert_called_once_with(USER_INFO)
    scope.assert_called()
    assert scope.call_args.args[1] is USER_INFO
    assert vm.query.call_count == 1
    query = vm.query.call_args.args[0]
    assert "winlogbeat" in query
    assert "4624" in query
    assert "stats by (host)" in query
    assert "entry_count" in query
    _assert_host_clause(query, "web-1", "10.0.0.1")
    assert _query_limit(vm.query.call_args) == 1


def test_counted_linux_queries_success_tokens(mocker):
    inst = SimpleNamespace(node_id="n2", collect_type=SimpleNamespace(name="file"))
    auth = mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    scope = mocker.patch.object(nm, "_apply_log_group_scope", side_effect=_map_log_group_scope)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"host": "lnx-1", "entry_count": "1"}]
    hosts = [{"host_name": "lnx-1", "ip": "10.0.0.2", "os_type": "1", "node_id": "n2"}]

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    assert out["data"][0]["login_count"] == 1
    auth.assert_called_once_with(USER_INFO)
    scope.assert_called()
    assert scope.call_args.args[1] is USER_INFO
    query = vm.query.call_args.args[0]
    assert '_msg:"Accepted password"' in query
    assert '_msg:"Accepted publickey"' in query
    assert '_msg:"session opened"' in query
    assert 'message:"Accepted password"' not in query
    assert 'message:"Accepted publickey"' not in query
    assert 'message:"session opened"' not in query
    assert "Failed" in query
    assert "Invalid user" in query
    assert "stats by (host)" in query
    _assert_host_clause(query, "lnx-1", "10.0.0.2")
    assert _query_limit(vm.query.call_args) == 1


def test_mixed_os_issues_at_most_one_query_each(mocker):
    instances = [
        SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat")),
        SimpleNamespace(node_id="n2", collect_type=SimpleNamespace(name="filebeat")),
    ]
    auth = mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, instances))
    mocker.patch.object(nm, "_apply_log_group_scope", side_effect=_map_log_group_scope)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI").return_value

    def fake_query(query, *args, **kwargs):
        if "winlogbeat" in query:
            return [{"host": "web-1", "entry_count": "2"}]
        return [{"host": "lnx-1", "entry_count": "5"}]

    vm.query.side_effect = fake_query
    hosts = [
        {"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"},
        {"host_name": "lnx-1", "ip": "10.0.0.2", "os_type": "1", "node_id": "n2"},
    ]

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    auth.assert_called_once_with(USER_INFO)
    assert vm.query.call_count == 2
    queries = [call.args[0] for call in vm.query.call_args_list]
    assert any("winlogbeat" in q and "4624" in q for q in queries)
    assert any("Accepted password" in q for q in queries)
    windows_query = next(q for q in queries if "winlogbeat" in q)
    linux_query = next(q for q in queries if "Accepted password" in q)
    _assert_host_clause(windows_query, "web-1", "10.0.0.1")
    _assert_host_clause(linux_query, "lnx-1", "10.0.0.2")
    for call in vm.query.call_args_list:
        assert _query_limit(call) == 2
    by_name = {row["host_name"]: row["login_count"] for row in out["data"]}
    assert by_name == {"web-1": 2, "lnx-1": 5}


def test_deny_all_log_group_scope_skips_vl_and_counts_zero(mocker):
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    scope = mocker.patch.object(nm, "_apply_log_group_scope", return_value=LogGroupQueryBuilder.DENY_ALL_QUERY)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    assert out["data"][0]["login_status"] == "counted"
    assert out["data"][0]["login_count"] == 0
    scope.assert_called()
    assert scope.call_args.args[1] is USER_INFO
    vm.assert_not_called()


def test_counted_hosts_without_names_skip_victoria_logs(mocker):
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI")
    hosts = [{"host_name": "", "ip": "", "os_type": "2", "node_id": "n1"}]

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    assert out["data"][0]["login_status"] == "counted"
    assert out["data"][0]["login_count"] == 0
    vm.assert_not_called()


# ----------------------- §8.4 logging -----------------------


def test_completed_info_logs_counts_not_hosts(mocker, caplog):
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    mocker.patch.object(nm, "_apply_log_group_scope", side_effect=_map_log_group_scope)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI").return_value
    vm.query.return_value = []
    hosts = [
        {"host_name": f"web-1-{SECRET_SENTINEL}", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"},
        {"host_name": "web-2", "ip": "10.0.0.2", "os_type": "2", "node_id": "missing"},
    ]
    caplog.set_level(logging.INFO, logger="log")

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is True
    assert out["data"][0]["login_status"] == "counted"
    assert out["data"][0]["login_count"] == 0
    assert out["data"][1]["login_status"] == "uncollected"
    records = [record for record in caplog.records if record.name == "log" and record.msg.startswith("event=successful_login_count_completed")]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.msg == "event=successful_login_count_completed counted_hosts=%s uncollected_hosts=%s"
    assert record.args == (1, 1)
    assert record.getMessage() == "event=successful_login_count_completed counted_hosts=1 uncollected_hosts=1"
    formatted = logging.Formatter().format(record)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in record.getMessage()
    assert SECRET_SENTINEL not in "".join(str(arg) for arg in record.args)
    assert "winlogbeat" not in formatted
    assert "web-1" not in formatted


def test_query_failure_has_one_safe_traceback_owner(mocker, caplog):
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    mocker.patch.object(nm, "_authorized_log_instances", return_value=_fake_instance_qs(mocker, [inst]))
    mocker.patch.object(nm, "_apply_log_group_scope", side_effect=_map_log_group_scope)
    vm = mocker.patch.object(nm, "VictoriaMetricsAPI").return_value
    original_error = RuntimeError(f"password={SECRET_SENTINEL} query=collect_type:winlogbeat")
    vm.query.side_effect = original_error
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    caplog.set_level(logging.ERROR, logger="log")

    out = nm.count_successful_logins_by_host(hosts, RFC3339_TIME_RANGE, user_info=USER_INFO)

    assert out["result"] is False
    assert out["data"] == []
    records = [record for record in caplog.records if record.name == "log" and "event=successful_login_count_failed" in record.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.msg == "event=successful_login_count_failed failed_stage=%s error_type=%s"
    assert record.args == ("victoria_logs_query", "RuntimeError")
    assert record.getMessage() == "event=successful_login_count_failed failed_stage=victoria_logs_query error_type=RuntimeError"
    assert record.exc_info is not None
    assert record.exc_info[2] is original_error.__traceback__
    assert original_error.args == (f"password={SECRET_SENTINEL} query=collect_type:winlogbeat",)
    formatted = logging.Formatter().format(record)
    assert SECRET_SENTINEL not in record.getMessage()
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text
    assert "collect_type:winlogbeat" not in record.getMessage()
