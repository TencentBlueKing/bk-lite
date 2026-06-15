import importlib.util
import sys
import threading
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_policy_scan_module(monkeypatch):
    _install_module(monkeypatch, "django", db=types.SimpleNamespace(transaction=types.SimpleNamespace()))
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace())

    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(
        monkeypatch,
        "apps.log.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(STATUS_NEW="new", STATUS_CLOSED="closed"),
    )
    _install_module(monkeypatch, "apps.log.constants.database", DatabaseConstants=types.SimpleNamespace(DEFAULT_BATCH_SIZE=100))
    _install_module(monkeypatch, "apps.log.constants.web", WebConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.log.models.policy",
        Alert=object,
        Event=object,
        EventRawData=object,
        AlertSnapshot=object,
    )
    _install_module(monkeypatch, "apps.log.tasks.utils.policy", period_to_seconds=lambda period: 300)
    _install_module(monkeypatch, "apps.log.utils.query_log", VictoriaMetricsAPI=lambda: None)
    _install_module(
        monkeypatch,
        "apps.log.utils.log_group",
        LogGroupQueryBuilder=types.SimpleNamespace(build_query_with_groups=lambda query, groups: (query, [])),
    )
    _install_module(monkeypatch, "apps.monitor.utils.system_mgmt_api", SystemMgmtUtils=object)
    _install_module(
        monkeypatch,
        "apps.core.logger",
        celery_logger=types.SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
            debug=lambda *args, **kwargs: None,
        ),
    )

    module_path = Path(__file__).resolve().parents[1] / "tasks" / "services" / "policy_scan.py"
    spec = importlib.util.spec_from_file_location("policy_scan_keyword_grouping_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeVictoriaLogs:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def query(self, query, start, end, limit):
        self.calls.append(
            {
                "query": query,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        if not self.responses:
            return []
        return self.responses.pop(0)


def make_policy(alert_condition, alert_name="${level} ${log.service.name} error"):
    return SimpleNamespace(
        id=7,
        alert_condition=alert_condition,
        alert_name=alert_name,
        alert_level="error",
        alert_type="keyword",
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc),
        collect_type=None,
    )


def make_scan(policy_scan_module, policy, fake_api):
    scan = policy_scan_module.LogPolicyScan(policy, scan_time=policy.last_run_time)
    scan.vlogs_api = fake_api
    scan._build_query_with_log_groups = lambda query: query
    return scan


def test_keyword_without_group_by_keeps_single_policy_source_id(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "error"}],
            [{"total_count": "3"}],
        ]
    )
    policy = make_policy({"query": "error", "limit": 5, "group_by": []}, alert_name="error alert")
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events == [
        {
            "source_id": "policy_7",
            "level": "error",
            "content": "error alert: 检测到 3 条匹配日志",
            "value": 3,
            "raw_data": [{"timestamp": "2026-06-09T08:00:00Z", "message": "error"}],
        }
    ]
    assert fake_api.calls[0]["query"] == "error"
    assert fake_api.calls[1]["query"] == "error | stats count() as total_count"


def test_keyword_without_group_by_renders_level_variable(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "error"}],
            [{"total_count": "3"}],
        ]
    )
    policy = make_policy({"query": "error", "limit": 5}, alert_name="${level} alert")
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events[0]["content"] == "error alert: 检测到 3 条匹配日志"


def test_keyword_with_group_by_uses_stats_by_and_returns_one_event_per_group(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [
                {"log.service.name": "api", "total_count": "2"},
                {"log.service.name": "web", "total_count": "5"},
            ],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
            [{"timestamp": "2026-06-09T08:00:10Z", "message": "web error", "log.service.name": "web"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${level}:${log.service.name}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert fake_api.calls[0]["query"] == "error | stats by (log.service.name) count() as total_count"
    assert len(events) == 2
    assert events[0]["source_id"].startswith("policy_7_")
    assert len(events[0]["source_id"]) <= 100
    assert events[0]["content"] == "error:api"
    assert events[0]["value"] == 2
    assert events[0]["raw_data"][0]["message"] == "api error"
    assert events[1]["source_id"].startswith("policy_7_")
    assert len(events[1]["source_id"]) <= 100
    assert events[1]["source_id"] != events[0]["source_id"]
    assert events[1]["content"] == "error:web"
    assert events[1]["value"] == 5
    assert 'log.service.name:="api"' in fake_api.calls[1]["query"]
    assert 'log.service.name:="web"' in fake_api.calls[2]["query"]


def test_keyword_group_alert_name_supports_log_prefixed_plain_field(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"host": "node-1", "total_count": "2"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "node error", "host": "node-1"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["host"]},
        alert_name="${level}:${log.host}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events[0]["content"] == "error:node-1"


def test_keyword_group_by_skips_rows_without_group_key_and_renders_missing_variables(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"total_count": "2"}, {"log.service.name": "api", "total_count": "4"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${level}|${log.service.name}|${missing}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events == [
        {
            "source_id": events[0]["source_id"],
            "level": "error",
            "content": "error|api|",
            "value": 4,
            "raw_data": [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
        }
    ]


def test_alert_name_template_renders_empty_when_only_variable_is_missing(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"log.service.name": "api", "total_count": "4"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${missing}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events[0]["content"] == ""


def test_keyword_group_sample_query_inserts_group_filter_before_pipeline(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"log.service.name": 'api"v1', "total_count": "4"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": 'api"v1'}],
        ]
    )
    policy = make_policy(
        {"query": "error | unpack_json", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${log.service.name}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    scan.keyword_alert_detection()

    assert fake_api.calls[1]["query"] == 'error | unpack_json | filter log.service.name:="api\\"v1"'


def test_keyword_group_sample_query_uses_stream_selector_for_stream_group(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    stream_value = '{instance_id="1761206c-e547-40f0-91f1-a4d62c3c7db8",source_type="docker_logs"}'
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"_stream": stream_value, "total_count": "42"}],
            [{"_time": "2026-06-11T06:30:00Z", "_msg": "ERROR example", "_stream": stream_value}],
        ]
    )
    policy = make_policy(
        {"query": "ERROR", "limit": 5, "group_by": ["_stream"]},
        alert_name="错误日志",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert fake_api.calls[1]["query"] == f"ERROR | filter _stream:{stream_value}"
    assert events[0]["value"] == 42
    assert events[0]["raw_data"] == [{"_time": "2026-06-11T06:30:00Z", "_msg": "ERROR example", "_stream": stream_value}]


def test_aggregate_alert_detection_returns_raw_query_result_for_matching_group(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"log.service.name": "api", "count__msg": "12"}],
        ]
    )
    policy = make_policy(
        {
            "query": "ERROR",
            "group_by": ["log.service.name"],
            "rule": {
                "mode": "and",
                "conditions": [{"field": "_msg", "func": "count", "op": ">", "value": 10}],
            },
        },
        alert_name="${level}:${log.service.name}",
    )
    policy.alert_type = "aggregate"
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.aggregate_alert_detection()

    assert fake_api.calls[0]["query"] == "ERROR | stats by (log.service.name) count() as count__msg"
    assert events == [
        {
            "source_id": "policy_7_log.service.name=api",
            "level": "error",
            "content": "error:api",
            "value": 12,
            "raw_data": {
                "aggregate_result": {"count__msg": 12, "count": 12},
                "rule": {
                    "mode": "and",
                    "conditions": [{"field": "_msg", "func": "count", "op": ">", "value": 10}],
                },
                "query_result": {"log.service.name": "api", "count__msg": "12"},
            },
        }
    ]


def test_keyword_grouped_source_id_is_bounded_for_long_group_values(monkeypatch):
    policy_scan_module = _load_policy_scan_module(monkeypatch)
    long_service_name = "api-" + ("x" * 200)
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"log.service.name": long_service_name, "total_count": "4"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": long_service_name}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${log.service.name}",
    )
    scan = make_scan(policy_scan_module, policy, fake_api)

    events = scan.keyword_alert_detection()

    assert events[0]["source_id"].startswith("policy_7_")
    assert len(events[0]["source_id"]) <= 100
    assert long_service_name not in events[0]["source_id"]


def test_keyword_grouped_alert_detection_issues_sample_queries_concurrently(monkeypatch):
    """验证多分组样本查询是并发（而非串行）发起的：N 个分组的最大并发线程数 > 1。
    若将修复 revert（改回串行 for 循环），此测试因无并发而失败。"""
    policy_scan_module = _load_policy_scan_module(monkeypatch)

    # 准备 5 个分组（group_query 返回）+ 5 个样本响应
    group_results = [{"host": f"node-{i}", "total_count": str(i + 1)} for i in range(5)]
    sample_responses = [[{"message": f"log from node-{i}"}] for i in range(5)]

    # 并发感知 FakeVictoriaLogs：group_query 同步返回，sample_query 用 barrier 保证并发
    concurrent_peak = []
    active_count = [0]
    lock = threading.Lock()
    barrier = threading.Barrier(5, timeout=15)

    call_count = [0]
    sample_iter = iter(sample_responses)

    class ConcurrentFakeVlogs:
        def query(self, query, start, end, limit):
            with lock:
                call_count[0] += 1
            # 第一次调用是 group_query（主线程），其余是 sample_query（线程池）
            if "stats by" in query:
                return group_results
            # sample_query：用 barrier 使所有样本查询同时就绪，确认并发
            with lock:
                active_count[0] += 1
                concurrent_peak.append(active_count[0])
            barrier.wait()
            with lock:
                active_count[0] -= 1
            try:
                return next(sample_iter)
            except StopIteration:
                return []

    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["host"]},
        alert_name="${host}",
    )
    scan = policy_scan_module.LogPolicyScan(policy, scan_time=policy.last_run_time)
    scan.vlogs_api = ConcurrentFakeVlogs()
    scan._build_query_with_log_groups = lambda query: query

    events = scan.keyword_alert_detection()

    # 并发峰值应 > 1（若串行则 max == 1）
    assert max(concurrent_peak) > 1, "样本查询未并发执行，缺少 ThreadPoolExecutor"
    # 所有 5 个分组都得到了 event
    assert len(events) == 5
    # 结果按原始分组顺序（node-0 … node-4）
    for i, event in enumerate(events):
        assert event["value"] == i + 1
