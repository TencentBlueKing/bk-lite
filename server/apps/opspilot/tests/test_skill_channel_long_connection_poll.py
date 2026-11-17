"""长连接轮询在数据库断连后的恢复。不连接真实飞书或企微。"""

import logging
import threading
import traceback

import pytest
from django.db import OperationalError, connection, connections

from apps.core.logger import SafeLogException
from apps.opspilot.management.commands.run_feishu_long_connection import DB_CLEANUP_FAILED_LOG_TEMPLATE as FEISHU_CLEANUP_TEMPLATE
from apps.opspilot.management.commands.run_feishu_long_connection import LOOP_FAILED_LOG_TEMPLATE as FEISHU_LOOP_TEMPLATE
from apps.opspilot.management.commands.run_feishu_long_connection import Command as FeishuCommand
from apps.opspilot.management.commands.run_wecom_aibot_long_connection import DB_CLEANUP_FAILED_LOG_TEMPLATE as WECOM_CLEANUP_TEMPLATE
from apps.opspilot.management.commands.run_wecom_aibot_long_connection import LOOP_FAILED_LOG_TEMPLATE as WECOM_LOOP_TEMPLATE
from apps.opspilot.management.commands.run_wecom_aibot_long_connection import Command as WecomCommand
from apps.opspilot.services.skill_channel_long_connection_poll import STAGE_LOAD_CHANNELS, STAGE_PUMP, STAGE_RECONCILE, poll_long_connection_once

SECRET_SENTINEL = "db-password-should-not-be-logged"
POLL_MODULE = "apps.opspilot.services.skill_channel_long_connection_poll"


def _poll(load, reconcile, pump, *, loop_template=FEISHU_LOOP_TEMPLATE, cleanup_template=FEISHU_CLEANUP_TEMPLATE):
    return poll_long_connection_once(
        load,
        reconcile,
        pump,
        loop_failed_template=loop_template,
        cleanup_failed_template=cleanup_template,
    )


def _patch_close(monkeypatch, closes):
    def close():
        closes.append("close")

    monkeypatch.setattr(f"{POLL_MODULE}.close_old_connections", close)


def _assert_single_error(caplog, template, stage, error_type, exc):
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR and record.name == "opspilot"]
    assert len(errors) == 1
    record = errors[0]
    assert record.msg == template
    assert record.args == (stage, error_type)
    rendered = record.getMessage()
    formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
    traceback_text = "".join(traceback.format_exception(*record.exc_info))
    assert rendered == template % (stage, error_type)
    for text in (rendered, formatted, traceback_text, caplog.text, str(record.args)):
        assert SECRET_SENTINEL not in text
    assert record.exc_info[0] is SafeLogException
    assert str(record.exc_info[1]) == error_type
    assert record.exc_info[2] is exc.__traceback__
    assert SECRET_SENTINEL in str(exc)


def test_load_failure_closes_connection_and_skips_later_stages(monkeypatch, caplog):
    closes = []
    seen = {}
    _patch_close(monkeypatch, closes)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    def load():
        exc = OperationalError(f"password={SECRET_SENTINEL}")
        seen["exc"] = exc
        raise exc

    def reconcile(_channels):
        raise AssertionError("load failure must not reconcile")

    def pump():
        raise AssertionError("load failure must not pump")

    _poll(load, reconcile, pump)

    assert closes == ["close", "close"]
    _assert_single_error(caplog, FEISHU_LOOP_TEMPLATE, STAGE_LOAD_CHANNELS, "OperationalError", seen["exc"])


def test_reconcile_failure_skips_pump(monkeypatch, caplog):
    closes = []
    seen = {}
    _patch_close(monkeypatch, closes)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    def load():
        return ["channel"]

    def reconcile(channels):
        assert channels == ["channel"]
        exc = OperationalError(f"password={SECRET_SENTINEL}")
        seen["exc"] = exc
        raise exc

    def pump():
        raise AssertionError("reconcile failure must not pump")

    _poll(load, reconcile, pump)

    assert closes == ["close", "close"]
    _assert_single_error(caplog, FEISHU_LOOP_TEMPLATE, STAGE_RECONCILE, "OperationalError", seen["exc"])


def test_pump_failure_runs_once(monkeypatch, caplog):
    closes = []
    seen = {}
    pumps = []
    _patch_close(monkeypatch, closes)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    def load():
        return ["channel"]

    def reconcile(channels):
        assert channels == ["channel"]

    def pump():
        pumps.append("pump")
        exc = OperationalError(f"password={SECRET_SENTINEL}")
        seen["exc"] = exc
        raise exc

    _poll(load, reconcile, pump)
    _poll(load, reconcile, lambda: pumps.append("next"))

    assert pumps == ["pump", "next"]
    assert closes == ["close", "close", "close", "close"]
    _assert_single_error(caplog, FEISHU_LOOP_TEMPLATE, STAGE_PUMP, "OperationalError", seen["exc"])


def test_success_closes_before_and_after_without_an_error(monkeypatch, caplog):
    trace = []
    _patch_close(monkeypatch, trace)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    def load():
        trace.append("load")
        return ["channel"]

    def reconcile(channels):
        trace.append(("reconcile", tuple(channels)))

    def pump():
        trace.append("pump")

    _poll(load, reconcile, pump)

    assert trace == ["close", "load", ("reconcile", ("channel",)), "pump", "close"]
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_cleanup_failure_does_not_replace_the_loop_error(monkeypatch, caplog):
    seen = {}
    calls = {"n": 0}

    def close():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError(f"dsn={SECRET_SENTINEL}")

    monkeypatch.setattr(f"{POLL_MODULE}.close_old_connections", close)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    def load():
        exc = OperationalError(f"password={SECRET_SENTINEL}")
        seen["exc"] = exc
        raise exc

    _poll(load, lambda _channels: None, lambda: None)

    _assert_single_error(caplog, FEISHU_LOOP_TEMPLATE, STAGE_LOAD_CHANNELS, "OperationalError", seen["exc"])
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING and record.name == "opspilot"]
    assert len(warnings) == 1
    assert warnings[0].msg == FEISHU_CLEANUP_TEMPLATE
    assert warnings[0].args == ("RuntimeError",)
    assert warnings[0].exc_info is None
    assert SECRET_SENTINEL not in warnings[0].getMessage()


def _run_command_once(monkeypatch, caplog, command_module, command, loop_template):
    closes = []
    monkeypatch.setattr(f"{POLL_MODULE}.close_old_connections", lambda: closes.append("close"))
    monkeypatch.setattr(f"{command_module}.redis_client_from_env", lambda: None)
    monkeypatch.setattr(f"{command_module}.time.sleep", lambda _seconds: (_ for _ in ()).throw(InterruptedError("stop")))
    seen = {}

    def load():
        exc = OperationalError(f"password={SECRET_SENTINEL}")
        seen["exc"] = exc
        raise exc

    monkeypatch.setattr(f"{command_module}.load_long_connection_channels", load)

    class Leader:
        def __init__(self, *args, **kwargs):
            return None

        def reconcile(self, _channels):
            raise AssertionError("load failure must not reconcile")

        def pump(self):
            raise AssertionError("load failure must not pump")

    leader_name = "FeishuLongConnectionLeader" if "feishu" in command_module else "WecomAibotLongConnectionLeader"
    monkeypatch.setattr(f"{command_module}.{leader_name}", Leader)
    caplog.set_level(logging.DEBUG, logger="opspilot")

    with pytest.raises(InterruptedError, match="stop"):
        command.handle()

    assert closes == ["close", "close"]
    _assert_single_error(caplog, loop_template, STAGE_LOAD_CHANNELS, "OperationalError", seen["exc"])


def test_feishu_command_logs_the_load_stage(monkeypatch, caplog):
    _run_command_once(
        monkeypatch,
        caplog,
        "apps.opspilot.management.commands.run_feishu_long_connection",
        FeishuCommand(),
        FEISHU_LOOP_TEMPLATE,
    )


def test_wecom_command_logs_the_load_stage(monkeypatch, caplog):
    _run_command_once(
        monkeypatch,
        caplog,
        "apps.opspilot.management.commands.run_wecom_aibot_long_connection",
        WecomCommand(),
        WECOM_LOOP_TEMPLATE,
    )
    assert WECOM_CLEANUP_TEMPLATE.endswith("failed_stage=db_cleanup error_type=%s")


@pytest.mark.django_db
def test_closed_driver_connection_recovers_on_the_next_poll(monkeypatch, caplog):
    if connection.vendor != "postgresql":
        pytest.skip("断连恢复需要 PostgreSQL")
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 3600)
    monkeypatch.setitem(connections.settings["default"], "CONN_HEALTH_CHECKS", False)
    caplog.set_level(logging.DEBUG, logger="opspilot")
    outcome = {}

    def worker():
        from django.contrib.sessions.models import Session
        from django.db import close_old_connections
        from django.db import connection as thread_connection

        try:
            thread_connection.ensure_connection()
            raw = thread_connection.connection
            raw.close()
            calls = {"reconcile": 0, "pump": 0}

            def load():
                Session.objects.count()
                return ["channel"]

            def reconcile(channels):
                assert channels == ["channel"]
                calls["reconcile"] += 1

            def pump():
                calls["pump"] += 1

            _poll(load, reconcile, pump)
            _poll(load, reconcile, pump)
            outcome["calls"] = calls
            outcome["reopened"] = thread_connection.connection is not None and not thread_connection.connection.closed
        except Exception as exc:
            outcome["error"] = exc
        finally:
            close_old_connections()
            thread_connection.close()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert "error" not in outcome
    assert outcome["calls"] == {"reconcile": 1, "pump": 1}
    assert outcome["reopened"] is True
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR and record.name == "opspilot"]
    assert len(errors) == 1
    assert errors[0].msg == FEISHU_LOOP_TEMPLATE
    assert errors[0].args == (STAGE_LOAD_CHANNELS, "OperationalError")
    assert errors[0].getMessage() == FEISHU_LOOP_TEMPLATE % (STAGE_LOAD_CHANNELS, "OperationalError")
    assert errors[0].exc_info[0] is SafeLogException
    assert str(errors[0].exc_info[1]) == "OperationalError"
    assert errors[0].exc_info[2] is not None
    # 真实堆栈会带上 psycopg 源码行，那一行本身写着这句；日志正文和代理异常不能带上它。
    assert "the connection is closed" not in errors[0].getMessage()
    assert "the connection is closed" not in str(errors[0].exc_info[1])
