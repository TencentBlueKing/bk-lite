from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from django.core.management.base import CommandError
from nats.js.errors import BadRequestError

from apps.monitor.management.commands import ensure_monitor_metrics_stream as command_module


pytestmark = pytest.mark.unit


def test_command_declares_expected_metrics_stream():
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=lambda *_: None)
    command.style = SimpleNamespace(SUCCESS=lambda message: message)

    with patch.object(command_module, "ensure_stream_sync") as ensure_stream:
        command.handle()

    ensure_stream.assert_called_once_with(
        "BK_MONITOR_METRICS",
        ["metrics.*"],
        3 * 24 * 60 * 60,
        1024 * 1024 * 1024,
    )


def test_command_allows_stream_retention_to_be_configured(monkeypatch):
    monkeypatch.setenv("MONITOR_METRICS_STREAM_MAX_AGE_SECONDS", "3600")
    monkeypatch.setenv("MONITOR_METRICS_STREAM_MAX_BYTES", "2097152")
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=lambda *_: None)
    command.style = SimpleNamespace(SUCCESS=lambda message: message)

    with patch.object(command_module, "ensure_stream_sync") as ensure_stream:
        command.handle()

    ensure_stream.assert_called_once_with(
        "BK_MONITOR_METRICS",
        ["metrics.*"],
        3600,
        2097152,
    )


def test_command_rejects_non_positive_stream_capacity(monkeypatch):
    monkeypatch.setenv("MONITOR_METRICS_STREAM_MAX_BYTES", "0")
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=lambda *_: None)
    command.style = SimpleNamespace(SUCCESS=lambda message: message)

    with patch.object(command_module, "ensure_stream_sync") as ensure_stream:
        with pytest.raises(CommandError, match="MONITOR_METRICS_STREAM_MAX_BYTES"):
            command.handle()

    ensure_stream.assert_not_called()


def test_command_explains_jetstream_requirement_when_declaration_fails():
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=lambda *_: None)
    command.style = SimpleNamespace(SUCCESS=lambda message: message)

    with (
        patch.object(command_module, "ensure_stream_sync", side_effect=RuntimeError("JetStream unavailable")),
        patch.object(command_module, "get_nc_client", AsyncMock(side_effect=RuntimeError("JetStream unavailable"))),
    ):
        with pytest.raises(CommandError, match="NATS 已启用 JetStream"):
            command.handle()


def test_command_accepts_existing_stream_with_metrics_subject():
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=lambda *_: None)
    command.style = SimpleNamespace(SUCCESS=lambda message: message)
    manager = SimpleNamespace(find_stream_name_by_subject=AsyncMock(return_value="OLD_METRICS"))
    nc = SimpleNamespace(jetstream_manager=lambda: manager, close=AsyncMock())

    with (
        patch.object(
            command_module,
            "ensure_stream_sync",
            side_effect=BadRequestError(code=400, err_code=10065, description="subjects overlap"),
        ),
        patch.object(command_module, "get_nc_client", AsyncMock(return_value=nc)),
    ):
        command.handle()

    manager.find_stream_name_by_subject.assert_awaited_once_with("metrics.*")
    nc.close.assert_awaited_once()
