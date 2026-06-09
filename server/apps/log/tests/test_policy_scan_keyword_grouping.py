import importlib.util
import sys
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
    assert events[0]["source_id"] == "policy_7_log.service.name=api"
    assert events[0]["content"] == "error:api"
    assert events[0]["value"] == 2
    assert events[0]["raw_data"][0]["message"] == "api error"
    assert events[1]["source_id"] == "policy_7_log.service.name=web"
    assert events[1]["content"] == "error:web"
    assert events[1]["value"] == 5
    assert 'log.service.name:"api"' in fake_api.calls[1]["query"]
    assert 'log.service.name:"web"' in fake_api.calls[2]["query"]
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
            "source_id": "policy_7_log.service.name=api",
            "level": "error",
            "content": "error|api|",
            "value": 4,
            "raw_data": [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
        }
    ]
