from types import SimpleNamespace

import pytest
from core.infra import nats as nats_module
from core.infra.nats import NATS, NATSConfig


def test_nats_config_reads_explicit_credentials_without_url_embedding(monkeypatch):
    monkeypatch.setenv("NATS_URLS", "tls://nats.example:4222")
    monkeypatch.setenv("NATS_USERNAME", "stargazer")
    monkeypatch.setenv("NATS_PASSWORD", "secret-value")

    config = NATSConfig.from_env("stargazer-test")

    assert config.servers == ["tls://nats.example:4222"]
    assert config.user == "stargazer"
    assert config.password == "secret-value"


def test_nats_config_defaults_to_unlimited_reconnects_and_explicit_pending_buffer(monkeypatch):
    monkeypatch.delenv("NATS_MAX_RECONNECT_ATTEMPTS", raising=False)
    monkeypatch.setenv("NATS_PENDING_SIZE_BYTES", "4194304")

    config = NATSConfig.from_env("stargazer-test")
    options = config.to_connect_options()

    assert config.max_reconnect_attempts == -1
    assert options["pending_size"] == 4194304


def test_subscriber_transport_readiness_tracks_actual_connection(monkeypatch):
    monkeypatch.setattr(
        nats_module,
        "_nats_instance",
        SimpleNamespace(nc=SimpleNamespace(is_connected=True, is_reconnecting=False)),
    )
    assert nats_module.subscriber_transport_ready() is True

    monkeypatch.setattr(
        nats_module,
        "_nats_instance",
        SimpleNamespace(nc=SimpleNamespace(is_connected=False, is_reconnecting=True)),
    )
    assert nats_module.subscriber_transport_ready() is False


@pytest.mark.asyncio
async def test_late_pong_ignores_cancelled_flush_future():
    client = NATS()
    future = __import__("asyncio").get_running_loop().create_future()
    future.cancel()
    client._pongs.append(future)

    await client._process_pong()

    assert future.cancelled()
    assert client._pongs == []
