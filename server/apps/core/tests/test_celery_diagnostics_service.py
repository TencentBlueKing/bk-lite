"""运行报告只返回结构化摘要，不输出 worker 的参数或凭据。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery import Celery

from apps.core.celery_runtime.diagnostics import periodic_report, worker_report
from apps.core.celery_runtime.routing import configure_routes

pytestmark = pytest.mark.unit


def test_explicit_periodic_route_conflict_is_reported_without_payload():
    app = Celery("diagnostic", broker="memory://", set_as_current=False)
    configure_routes(app)
    row = SimpleNamespace(
        pk=1,
        task="apps.monitor.tasks.monitor_policy.scan_policy_task",
        queue="celery",
        exchange=None,
        routing_key=None,
        args='["secret"]',
        kwargs='{"token":"secret"}',
    )
    report = periodic_report(app, [row], {row.task})
    assert report[0]["issues"] == ["route_conflict"]
    assert report[0]["effective"]["queue"] == "celery"
    assert "secret" not in str(report)
    app.close()


def test_missing_worker_replies_are_unknown_and_inspect_payload_is_redacted():
    inspector = Mock()
    inspector.active.return_value = {"critical@host": [{"name": "task", "args": "secret"}]}
    inspector.reserved.return_value = None
    inspector.scheduled.return_value = {}
    inspector.registered.return_value = {"critical@host": ["apps.monitor.tasks.monitor_policy.scan_policy_task [rate_limit=None]"]}
    inspector.active_queues.return_value = {"critical@host": [{"name": "critical", "exchange": {"secret": "value"}}]}
    inspector.stats.return_value = {
        "critical@host": {
            "pool": {"processes": [1, 2]},
            "autoscaler": {"min": 1, "max": 2, "current": 2},
            "rusage": {"maxrss": 100},
            "broker": {"password": "secret"},
        }
    }
    result = worker_report(inspector)
    assert result["workers"]["critical@host"]["active"] == 1
    assert result["workers"]["critical@host"]["reserved"] is None
    assert result["workers"]["critical@host"]["registered"] == ["apps.monitor.tasks.monitor_policy.scan_policy_task"]
    assert "secret" not in str(result)
    assert result["queue_consumers"]["background"] == 0


def test_worker_control_failure_has_no_exception_payload():
    inspector = Mock()
    inspector.active.side_effect = RuntimeError("redis://secret@host")
    for name in ("reserved", "scheduled", "active_queues", "stats", "registered"):
        getattr(inspector, name).return_value = None
    result = worker_report(inspector)
    assert "secret" not in str(result)
    assert "active" in result["unavailable"]


def test_partial_replies_are_reported_per_worker_instead_of_passing_strict_check():
    inspector = Mock()
    for method in ("active", "reserved", "scheduled", "registered", "active_queues"):
        getattr(inspector, method).return_value = {"critical@host": [], "state@host": []}
    inspector.stats.return_value = {"critical@host": {}, "state@host": {}}
    inspector.active.return_value = {"critical@host": []}
    result = worker_report(inspector)
    assert "state@host:active" in result["unavailable"]
