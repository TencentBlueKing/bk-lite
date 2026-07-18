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


def test_get_nc_client_redacts_credentials_from_settings_on_connect_error():
    class _FailingNatsClient:
        async def connect(self, **_kwargs):
            raise RuntimeError("authorization failed for settings-user/settings-secret")

    with mock.patch.object(
        clients.settings,
        "NATS_OPTIONS",
        {"user": "settings-user", "password": "settings-secret"},
    ), mock.patch.object(clients, "logger") as logger:
        with pytest.raises(RuntimeError):
            asyncio.run(
                clients.get_nc_client(
                    nc=_FailingNatsClient(),
                    server="nats://nats.example.com:4222",
                )
            )

    log_call = str(logger.error.call_args)
    assert "settings-user" not in log_call
    assert "settings-secret" not in log_call


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
                    _nats_user="alice",
                    _nats_password="alice-secret",
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


def test_request_v2_redacts_legacy_credentials_when_error_splits_url():
    raw_server = "nats://legacy:legacy-secret@nats.example.com:4222"
    error = RuntimeError("authorization failed for legacy using legacy-secret")

    with mock.patch.object(clients, "get_nc_client", side_effect=error), mock.patch.object(
        clients, "logger"
    ) as logger:
        with pytest.raises(NatsClientException):
            asyncio.run(clients.request_v2("namespace", "method", server=raw_server))

    log_call = str(logger.error.call_args)
    assert "legacy" not in log_call
    assert "legacy-secret" not in log_call


def test_request_v2_keeps_business_user_and_password_in_payload():
    class _FakeResponse:
        data = b'{"success": true, "result": "ok"}'

    class _RequestClient:
        def __init__(self):
            self.payload = None

        async def request(self, _subject, payload, timeout):
            self.payload = payload
            return _FakeResponse()

        async def close(self):
            return None

    nc = _RequestClient()
    with mock.patch.object(clients, "get_nc_client", return_value=nc) as get_client:
        result = asyncio.run(
            clients.request_v2(
                "namespace",
                "method",
                server="nats://nats.example.com:4222",
                user="business-user",
                password="business-password",
            )
        )

    assert result == "ok"
    assert b'"user": "business-user"' in nc.payload
    assert b'"password": "business-password"' in nc.payload
    get_client.assert_awaited_once_with(
        server="nats://nats.example.com:4222",
        user=None,
        password=None,
    )
