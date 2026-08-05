import asyncio
import json
from unittest import mock

import pytest

from nats_client import clients
from nats_client.exceptions import NatsClientException


class _FakeResponse:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode()


class _FakeNatsClient:
    def __init__(self, payload):
        self.response = _FakeResponse(payload)

    async def request(self, *_args, **_kwargs):
        return self.response

    async def close(self):
        return None


def _legacy_exception_payload(message):
    return json.dumps(
        {
            "py/reduce": [
                {"py/type": "apps.core.exceptions.base_app_exception.BaseAppException"},
                {"py/tuple": [message]},
                {"message": message, "data": None},
            ]
        }
    )


def test_legacy_exception_parser_treats_recursion_failure_as_unrecognized():
    with mock.patch.object(clients.json, "loads", side_effect=RecursionError):
        assert clients._extract_legacy_exception_message("legacy exception") is None


@pytest.mark.parametrize("request_func", [clients.request, clients.request_v2])
def test_nats_request_reads_legacy_exception_message_without_object_restore(request_func):
    nats_client = _FakeNatsClient(
        {
            "success": False,
            "error": "BaseAppException",
            "pickled_exc": _legacy_exception_payload("collector default config missing"),
        }
    )

    with mock.patch.object(clients, "get_nc_client", return_value=nats_client), mock.patch(
        "jsonpickle.decode",
        side_effect=AssertionError("NATS error responses must not restore Python objects"),
    ) as decode:
        with pytest.raises(
            NatsClientException,
            match="BaseAppException: collector default config missing",
        ):
            asyncio.run(request_func("namespace", "method"))

    decode.assert_not_called()


@pytest.mark.parametrize("request_func", [clients.request, clients.request_v2])
def test_nats_request_keeps_message_from_legacy_only_error_response(request_func):
    nats_client = _FakeNatsClient(
        {
            "success": False,
            "pickled_exc": _legacy_exception_payload("legacy service error"),
        }
    )

    with mock.patch.object(clients, "get_nc_client", return_value=nats_client):
        with pytest.raises(NatsClientException, match=r"^legacy service error$"):
            asyncio.run(request_func("namespace", "method"))


@pytest.mark.parametrize("request_func", [clients.request, clients.request_v2])
def test_nats_request_ignores_unrecognized_legacy_exception_shape(request_func):
    nats_client = _FakeNatsClient(
        {
            "success": False,
            "error": "BaseAppException",
            "pickled_exc": json.dumps({"message": "untrusted detail"}),
        }
    )

    with mock.patch.object(clients, "get_nc_client", return_value=nats_client):
        with pytest.raises(NatsClientException, match=r"^BaseAppException$"):
            asyncio.run(request_func("namespace", "method"))


@pytest.mark.parametrize("request_func", [clients.request, clients.request_v2])
@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (
            {"success": False, "error": "RemoteError", "message": "request rejected"},
            "RemoteError: request rejected",
        ),
        ({"success": False, "result": "service unavailable"}, "service unavailable"),
    ],
)
def test_nats_request_preserves_structured_error_contract(request_func, payload, expected_message):
    nats_client = _FakeNatsClient(payload)

    with mock.patch.object(clients, "get_nc_client", return_value=nats_client):
        with pytest.raises(NatsClientException, match=f"^{expected_message}$"):
            asyncio.run(request_func("namespace", "method"))
