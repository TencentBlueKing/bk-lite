import os
import subprocess
import sys
import threading

import pytest

from apps.log.services.log_extractor import preview_runtime
from apps.log.services.log_extractor import semantics
from apps.log.services.log_extractor.semantics import execute_rules, normalize_rule


def _regex_rule():
    return normalize_rule(
        {
            "extractor_type": "regex_replace",
            "source_field": "message",
            "target_field": "result",
            "condition": {},
            "config": {"pattern": "a+$", "replacement": "masked"},
            "delete_source": False,
        }
    )


@pytest.mark.unit
def test_extreme_integer_environment_value_falls_back_without_import_failure(monkeypatch):
    monkeypatch.setenv("LOG_EXTRACTOR_PREVIEW_TEST_LIMIT", "9" * 10_000)

    assert preview_runtime._positive_number_env("LOG_EXTRACTOR_PREVIEW_TEST_LIMIT", 7, int) == 7


@pytest.mark.integration
def test_regex_preview_terminates_catastrophic_backtracking():
    probe = """
from apps.log.services.log_extractor.semantics import execute_rules, normalize_rule

rule = normalize_rule(
    {
        "extractor_type": "regex_replace",
        "source_field": "message",
        "target_field": "result",
        "condition": {},
        "config": {"pattern": "(a+)+$", "replacement": "masked"},
        "delete_source": False,
    }
)
try:
    execute_rules({"message": "a" * 27 + "!"}, [rule])
except ValueError as exc:
    print(f"{type(exc).__name__}:{exc}")
"""
    env = {**os.environ, "LOG_EXTRACTOR_PREVIEW_TIMEOUT_SECONDS": "0.1"}

    try:
        completed = subprocess.run([sys.executable, "-c", probe], check=True, capture_output=True, text=True, timeout=3, env=env)
    except subprocess.TimeoutExpired:
        pytest.fail("灾难性回溯未被预览超时终止")

    assert completed.stdout.strip() == "RuleExecutionTimeoutError:正则预览执行超时"


@pytest.mark.unit
def test_regex_preview_rejects_work_when_local_capacity_is_exhausted(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(preview_runtime, "_REGEX_PREVIEW_SLOTS", slots)

    with pytest.raises(preview_runtime.RuleExecutionBusyError, match="并发已达上限"):
        execute_rules({"message": "aaaa"}, [_regex_rule()])

    slots.release()


@pytest.mark.unit
def test_regex_preview_rejects_oversized_field_before_starting_process(monkeypatch):
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_MAX_FIELD_BYTES", 3)
    started = False

    def unexpected_start(*args, **kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(preview_runtime, "_execute_rules_isolated", unexpected_start)

    with pytest.raises(preview_runtime.RuleExecutionLimitError, match="字段大小超过上限"):
        execute_rules({"message": "aaaa"}, [_regex_rule()])

    assert started is False


@pytest.mark.unit
def test_regex_preview_rejects_oversized_event_before_starting_process(monkeypatch):
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_MAX_FIELD_BYTES", 100)
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_MAX_EVENT_BYTES", 10)
    started = False

    def unexpected_start(*args, **kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(preview_runtime, "_execute_rules_isolated", unexpected_start)

    with pytest.raises(preview_runtime.RuleExecutionLimitError, match="事件大小超过上限"):
        execute_rules({"message": "aaaa"}, [_regex_rule()])

    assert started is False


@pytest.mark.unit
def test_non_regex_preview_preserves_legacy_path_without_regex_size_limit(monkeypatch):
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_MAX_FIELD_BYTES", 3)
    rule = normalize_rule(
        {
            "extractor_type": "copy",
            "source_field": "message",
            "target_field": "result",
            "condition": {},
            "config": {},
            "delete_source": False,
        }
    )

    result = execute_rules({"message": "a" * 100}, [rule])

    assert result.event["result"] == "a" * 100


@pytest.mark.unit
def test_regex_preview_releases_capacity_after_worker_failure(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(preview_runtime, "_REGEX_PREVIEW_SLOTS", slots)

    def fail_worker(*args, **kwargs):
        raise RuntimeError("worker failed")

    monkeypatch.setattr(preview_runtime, "_execute_rules_isolated", fail_worker)

    with pytest.raises(RuntimeError, match="worker failed"):
        execute_rules({"message": "aaaa"}, [_regex_rule()])

    assert slots.acquire(blocking=False) is True
    slots.release()


class _FakeConnection:
    def __init__(self, *, poll_result: bool, eof: bool = False):
        self.poll_result = poll_result
        self.eof = eof
        self.closed = False
        self.sent = None

    def poll(self, timeout):
        return self.poll_result

    def recv(self):
        if self.eof:
            raise EOFError
        return "success", None

    def send(self, payload):
        self.sent = payload

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self):
        self.alive = True
        self.started = False
        self.killed = False
        self.closed = False
        self.join_timeouts = []

    def start(self):
        self.started = True

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)
        if self.killed:
            self.alive = False

    def is_alive(self):
        return self.alive

    def kill(self):
        self.killed = True

    def close(self):
        self.closed = True


@pytest.mark.unit
@pytest.mark.parametrize(("poll_result", "eof", "error"), [(False, False, ValueError), (True, True, RuntimeError)])
def test_isolated_preview_reaps_process_on_timeout_or_eof(monkeypatch, poll_result, eof, error):
    parent = _FakeConnection(poll_result=poll_result, eof=eof)
    child = _FakeConnection(poll_result=False)
    process = _FakeProcess()

    class FakeContext:
        @staticmethod
        def Pipe(duplex):
            return parent, child

        @staticmethod
        def Process(target, args):
            return process

    monkeypatch.setattr(preview_runtime.multiprocessing, "get_context", lambda method: FakeContext())

    with pytest.raises(error):
        preview_runtime._execute_rules_isolated({"message": "aaaa"}, [_regex_rule()], 0.01)

    assert process.started and process.killed and process.closed
    assert process.join_timeouts == [0.1, 1]
    assert parent.closed and child.closed


@pytest.mark.unit
def test_isolated_preview_closes_process_handle_when_start_fails(monkeypatch):
    parent = _FakeConnection(poll_result=False)
    child = _FakeConnection(poll_result=False)
    process = _FakeProcess()

    def fail_start():
        raise RuntimeError("spawn failed")

    process.start = fail_start

    class FakeContext:
        @staticmethod
        def Pipe(duplex):
            return parent, child

        @staticmethod
        def Process(target, args):
            return process

    monkeypatch.setattr(preview_runtime.multiprocessing, "get_context", lambda method: FakeContext())

    with pytest.raises(RuntimeError, match="spawn failed"):
        preview_runtime._execute_rules_isolated({"message": "aaaa"}, [_regex_rule()], 0.01)

    assert process.closed is True
    assert parent.closed and child.closed


@pytest.mark.unit
def test_worker_reports_unexpected_failure_type_and_logs_traceback(monkeypatch, caplog):
    connection = _FakeConnection(poll_result=False)

    def fail_inline(event, rules):
        raise RuntimeError("unexpected worker failure")

    monkeypatch.setattr(semantics, "_execute_rules_inline", fail_inline)

    with caplog.at_level("ERROR", logger="log"):
        preview_runtime._execute_rules_worker(connection, {"message": "safe"}, [_regex_rule()])

    assert connection.sent == ("error", "RuntimeError")
    assert connection.closed is True
    assert "正则预览子进程执行失败" in caplog.text
    assert "unexpected worker failure" in caplog.text
