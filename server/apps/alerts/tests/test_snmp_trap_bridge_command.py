"""SNMP Trap bridge 管理命令：NATS 连接、JSON 解析与投递契约。

对照 spec/prd/告警中心·集成：常驻订阅 vector subject，只处理合法 JSON SNMP 消息。
"""

import asyncio
import json
import logging
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.aio.errors import ErrNoServers, ErrTimeout

from apps.alerts.management.commands import snmp_trap_bridge as cmd_mod


def _make_command(config=None):
    with patch.object(cmd_mod, "load_bridge_config", return_value=config or {"subject": "vector"}):
        command = cmd_mod.Command()
    command.stdout = StringIO()
    command.style = SimpleNamespace(SUCCESS=lambda text: text)
    command.nats = AsyncMock()
    return command


# --------------------------------------------------------------------------
# add_arguments / handle
# --------------------------------------------------------------------------


def test_add_arguments_registers_reload_flag():
    command = _make_command()
    parser = MagicMock()
    command.add_arguments(parser)
    parser.add_argument.assert_called_once()
    kwargs = parser.add_argument.call_args.kwargs
    assert kwargs["dest"] == "reload"
    assert kwargs["action"] == "store_true"


def test_handle_without_reload_calls_inner_run():
    command = _make_command()
    with patch.object(command, "inner_run") as inner:
        command.handle(reload=False)
    inner.assert_called_once()
    output = command.stdout.getvalue()
    assert "Starting SNMP trap bridge" in output
    assert "with reload enabled" not in output


def test_handle_with_reload_uses_autoreload():
    command = _make_command()
    with patch.object(cmd_mod.autoreload, "run_with_reloader") as reloader:
        command.handle(reload=True)
    reloader.assert_called_once()
    assert reloader.call_args.args[0] == command.inner_run
    assert "with reload enabled" in command.stdout.getvalue()


# --------------------------------------------------------------------------
# inner_run：事件循环生命周期
# --------------------------------------------------------------------------


_REAL_NEW_EVENT_LOOP = asyncio.new_event_loop


def _run_on_fresh_loop(awaitable):
    # 测试会替换命令模块上的 new_event_loop；这里必须用导入时保存的真实实现。
    loop = _REAL_NEW_EVENT_LOOP()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


def test_inner_run_runs_forever_then_closes_loop():
    """启动协程完成后才常驻；中断时关闭 NATS，且不把中断当成连接失败。"""
    command = _make_command()
    fake_loop = MagicMock()
    bridge = object()
    close_coro = object()
    command.nats.close = MagicMock(return_value=close_coro)
    order = []

    def run_until_complete(awaitable):
        order.append(awaitable)

    def run_forever():
        order.append("forever")
        raise KeyboardInterrupt()

    fake_loop.run_until_complete.side_effect = run_until_complete
    fake_loop.run_forever.side_effect = run_forever

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(command, "bridge_coroutine", new=MagicMock(return_value=bridge)),
    ):
        command.inner_run()

    assert order == [bridge, "forever", close_coro]
    fake_loop.run_forever.assert_called_once()
    fake_loop.close.assert_called_once()


def test_inner_run_closes_loop_without_interrupt():
    """常驻循环正常返回后仍关闭 NATS 和事件循环，且启动阶段已被等待。"""
    command = _make_command()
    fake_loop = MagicMock()
    bridge = object()
    close_coro = object()
    command.nats.close = MagicMock(return_value=close_coro)
    order = []

    def run_until_complete(awaitable):
        order.append(awaitable)

    def run_forever():
        order.append("forever")

    fake_loop.run_until_complete.side_effect = run_until_complete
    fake_loop.run_forever.side_effect = run_forever

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(command, "bridge_coroutine", new=MagicMock(return_value=bridge)),
    ):
        command.inner_run()

    assert order == [bridge, "forever", close_coro]
    fake_loop.close.assert_called_once()


def test_inner_run_connect_failure_skips_forever_and_subscribe():
    """首次连接抛 ErrNoServers 时进程失败退出，不进入常驻循环，也不订阅。"""
    command = _make_command()
    fake_loop = MagicMock()

    def run_until_complete(awaitable):
        return _run_on_fresh_loop(awaitable)

    fake_loop.run_until_complete.side_effect = run_until_complete

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(cmd_mod, "get_nc_client", AsyncMock(side_effect=ErrNoServers("nats down"))),
    ):
        with pytest.raises(ErrNoServers):
            command.inner_run()

    fake_loop.run_forever.assert_not_called()
    command.nats.subscribe.assert_not_called()
    fake_loop.close.assert_called_once()


def test_inner_run_subscribe_failure_skips_forever():
    command = _make_command()
    fake_loop = MagicMock()
    command.nats.subscribe = AsyncMock(side_effect=RuntimeError("subscribe failed"))

    def run_until_complete(awaitable):
        return _run_on_fresh_loop(awaitable)

    fake_loop.run_until_complete.side_effect = run_until_complete

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(cmd_mod, "get_nc_client", AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="subscribe failed"):
            command.inner_run()

    fake_loop.run_forever.assert_not_called()
    fake_loop.close.assert_called_once()


def test_inner_run_subscribes_before_run_forever():
    command = _make_command({"subject": "vector"})
    fake_loop = MagicMock()
    order = []

    async def subscribe(subject, cb=None):
        order.append(("subscribe", subject, cb))

    command.nats.subscribe = subscribe

    def run_until_complete(awaitable):
        return _run_on_fresh_loop(awaitable)

    def run_forever():
        order.append("forever")

    fake_loop.run_until_complete.side_effect = run_until_complete
    fake_loop.run_forever.side_effect = run_forever

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(cmd_mod, "get_nc_client", AsyncMock()),
    ):
        command.inner_run()

    subscribe_at = next(index for index, item in enumerate(order) if isinstance(item, tuple))
    assert order[subscribe_at][0] == "subscribe"
    assert order[subscribe_at][1] == "vector"
    assert order[subscribe_at][2] is not None
    assert order.index("forever") > subscribe_at
    assert "** Listening on subject: vector" in command.stdout.getvalue()
    fake_loop.close.assert_called_once()


def test_inner_run_cleanup_errors_do_not_mask_connect_failure(caplog):
    command = _make_command()
    fake_loop = MagicMock()
    secret = "SECRET-NATS-PASSWORD"
    connect_error = ErrNoServers("nats down")
    close_nats_error = RuntimeError(f"nats://ops:{secret}@127.0.0.1:4222")
    close_loop_error = RuntimeError(f"loop close {secret}")
    calls = {"n": 0}

    def run_until_complete(_awaitable):
        calls["n"] += 1
        if calls["n"] == 1:
            raise connect_error
        raise close_nats_error

    fake_loop.run_until_complete.side_effect = run_until_complete
    fake_loop.close.side_effect = close_loop_error

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(command, "bridge_coroutine", new=MagicMock(return_value=object())),
    ):
        with caplog.at_level(logging.ERROR, logger="alert"):
            with pytest.raises(ErrNoServers) as raised:
                command.inner_run()

    assert raised.value is connect_error
    fake_loop.run_forever.assert_not_called()
    assert secret in str(close_nats_error)
    assert secret in str(close_loop_error)

    records = [record for record in caplog.records if record.name == "alert" and record.levelno >= logging.ERROR]
    assert [(record.args[0], record.args[1]) for record in records] == [
        ("close_nats", "RuntimeError"),
        ("close_event_loop", "RuntimeError"),
    ]
    formatter = logging.Formatter("%(message)s")
    for record, err in zip(records, (close_nats_error, close_loop_error)):
        assert record.msg == "event=snmp_trap_bridge_shutdown_failed failed_stage=%s error_type=%s"
        assert record.exc_info[2] is err.__traceback__
        assert record.exc_info[1] is not err
        rendered = formatter.format(record)
        assert secret not in record.getMessage()
        assert secret not in rendered
        assert "event=snmp_trap_bridge_shutdown_failed" in rendered
    assert secret not in caplog.text


def test_inner_run_interrupt_during_close_does_not_mask_connect_failure():
    command = _make_command()
    fake_loop = MagicMock()
    connect_error = ErrNoServers("nats down")
    calls = {"n": 0}

    def run_until_complete(_awaitable):
        calls["n"] += 1
        if calls["n"] == 1:
            raise connect_error
        raise KeyboardInterrupt()

    fake_loop.run_until_complete.side_effect = run_until_complete

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(command, "bridge_coroutine", new=MagicMock(return_value=object())),
    ):
        with pytest.raises(ErrNoServers) as raised:
            command.inner_run()

    assert raised.value is connect_error
    fake_loop.run_forever.assert_not_called()
    fake_loop.close.assert_called_once()


def test_inner_run_startup_interrupt_closes_without_running_forever():
    command = _make_command()
    fake_loop = MagicMock()
    close_coro = object()
    command.nats.close = MagicMock(return_value=close_coro)
    calls = {"n": 0}

    def run_until_complete(_awaitable):
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyboardInterrupt()
        return None

    fake_loop.run_until_complete.side_effect = run_until_complete

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(command, "bridge_coroutine", new=MagicMock(return_value=object())),
    ):
        command.inner_run()

    fake_loop.run_forever.assert_not_called()
    command.nats.close.assert_called_once()
    fake_loop.close.assert_called_once()


# --------------------------------------------------------------------------
# bridge_coroutine：连接失败 / 订阅 / 回调契约
# --------------------------------------------------------------------------


@pytest.mark.parametrize("exc_cls", [ErrNoServers, ErrTimeout])
def test_bridge_coroutine_connect_failure_reraises(exc_cls):
    command = _make_command()

    async def _run():
        with patch.object(cmd_mod, "get_nc_client", AsyncMock(side_effect=exc_cls("nats down"))):
            with pytest.raises(exc_cls):
                await command.bridge_coroutine()

    asyncio.run(_run())
    command.nats.subscribe.assert_not_called()


def test_bridge_callback_ignores_non_json_and_dispatches_valid():
    """非 JSON 必须忽略；合法 payload 交给 handle_vector_message；处理失败不得打断订阅。"""
    command = _make_command({"subject": "vector"})
    captured = {}

    async def fake_subscribe(subject, cb=None):
        captured["subject"] = subject
        captured["cb"] = cb

    command.nats.subscribe = fake_subscribe

    async def _run():
        with patch.object(cmd_mod, "get_nc_client", AsyncMock()):
            await command.bridge_coroutine()

        assert captured["subject"] == "vector"
        assert "** Listening on subject: vector" in command.stdout.getvalue()
        callback = captured["cb"]

        await callback(SimpleNamespace(data=b"not-json{", subject="vector"))

        with patch.object(cmd_mod, "handle_vector_message", return_value=True) as handled:
            payload = {"collect_type": "snmp_trap", "trap_message": "linkDown"}
            await callback(SimpleNamespace(data=json.dumps(payload).encode(), subject="vector"))
        handled.assert_called_once_with(payload, command.config)

        with patch.object(cmd_mod, "handle_vector_message", return_value=False) as skipped:
            await callback(SimpleNamespace(data=b'{"collect_type":"log"}', subject="vector"))
        skipped.assert_called_once()

        with patch.object(cmd_mod, "handle_vector_message", side_effect=RuntimeError("dispatch boom")):
            await callback(SimpleNamespace(data=b'{"collect_type":"snmp_trap"}', subject="vector"))

    asyncio.run(_run())
