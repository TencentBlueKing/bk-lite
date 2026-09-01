"""SNMP Trap bridge 管理命令：NATS 连接、JSON 解析与投递契约。

对照 spec/prd/告警中心·集成：常驻订阅 vector subject，只处理合法 JSON SNMP 消息。
"""

import asyncio
import json
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


def test_inner_run_runs_forever_then_closes_loop():
    command = _make_command()
    fake_loop = MagicMock()
    fake_loop.run_forever.side_effect = KeyboardInterrupt()
    close_coro = object()
    command.nats.close = MagicMock(return_value=close_coro)

    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(cmd_mod.asyncio, "ensure_future"),
        patch.object(command, "bridge_coroutine", return_value=object()),
    ):
        command.inner_run()

    fake_loop.run_forever.assert_called_once()
    fake_loop.run_until_complete.assert_called_once_with(close_coro)
    fake_loop.close.assert_called_once()


def test_inner_run_closes_loop_without_interrupt():
    command = _make_command()
    fake_loop = MagicMock()
    with (
        patch.object(cmd_mod.asyncio, "new_event_loop", return_value=fake_loop),
        patch.object(cmd_mod.asyncio, "set_event_loop"),
        patch.object(cmd_mod.asyncio, "ensure_future"),
        patch.object(command, "bridge_coroutine", return_value=object()),
    ):
        command.inner_run()
    fake_loop.run_until_complete.assert_not_called()
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
