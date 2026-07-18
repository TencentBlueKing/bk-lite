import asyncio
import traceback
from unittest import mock

import pytest

from nats_client import clients
from nats_client.exceptions import NatsClientException


class _FakeNatsClient:
    def __init__(self):
        self.connect_kwargs = None

    async def connect(self, **kwargs):
        self.connect_kwargs = kwargs


def test_get_nc_client_passes_credentials_separately():
    nc = _FakeNatsClient()

    result = asyncio.run(
        clients.get_nc_client(
            nc=nc,
            server="nats://nats.example.com:4222",
            user="alice",
            password="plain-secret",
        )
    )

    assert result is nc
    assert nc.connect_kwargs["servers"] == ["nats://nats.example.com:4222"]
    assert nc.connect_kwargs["user"] == "alice"
    assert nc.connect_kwargs["password"] == "plain-secret"


def test_request_v2_redacts_legacy_url_and_separate_credentials_on_connect_error():
    raw_server = "nats://legacy:legacy-secret@nats.example.com:4222"
    error = RuntimeError(f"failed to connect {raw_server} as alice/alice-secret")

    with mock.patch.object(clients, "get_nc_client", side_effect=error) as get_client, mock.patch.object(
        clients, "logger"
    ) as logger:
        with pytest.raises(NatsClientException) as exc_info:
            asyncio.run(
                clients.request_v2(
                    "namespace",
                    "method",
                    server=raw_server,
                    user="alice",
                    password="alice-secret",
                )
            )

    get_client.assert_awaited_once_with(server=raw_server, user="alice", password="alice-secret")
    public_error = str(exc_info.value)
    public_traceback = "".join(traceback.format_exception(exc_info.value))
    log_call = str(logger.error.call_args)
    assert "legacy-secret" not in public_error
    assert "legacy-secret" not in public_traceback
    assert "legacy-secret" not in log_call
    assert "alice-secret" not in public_error
    assert "alice-secret" not in public_traceback
    assert "alice-secret" not in log_call
    assert "***-secret" not in log_call
    assert "***:***@nats.example.com:4222" in public_error
