import asyncio

import pytest

import nats_client
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt import nats_api
from apps.system_mgmt.models import User
from nats_client.handlers import nats_handler
from nats_client.management.commands import nats_listener

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_wechat_user_register_keeps_local_app_client_path(monkeypatch):
    monkeypatch.setattr(nats_api, "_build_jwt_payload", lambda user_id: {"user_id": user_id})
    monkeypatch.setattr(nats_api._wechat.jwt, "encode", lambda **kwargs: "local-wechat-token")

    result = SystemMgmt().wechat_user_register("wechat-local-user", "WeChat Local User")

    assert result["result"] is True
    assert result["data"]["token"] == "local-wechat-token"
    assert User.objects.filter(username="wechat-local-user").exists()
    assert "bklite.wechat_user_register" not in nats_client.registry.default_registry.registry


def test_nats_listener_and_dispatch_reject_wechat_user_register(monkeypatch, settings):
    subscribed = []

    class FakeNats:
        async def subscribe(self, subject, queue, cb, **kwargs):
            subscribed.append(subject)

    async def fake_get_nc_client(client):
        return client

    monkeypatch.setattr(nats_listener, "get_nc_client", fake_get_nc_client)
    settings.NATS_JETSTREAM_ENABLED = False
    command = nats_listener.Command()
    command.nats = FakeNats()

    asyncio.run(command.nats_coroutine())

    assert "bklite.wechat_user_register" not in subscribed
    with pytest.raises(ValueError, match="No function found"):
        asyncio.run(
            nats_handler(
                "bklite.wechat_user_register",
                {"args": ["remote-user", "Remote User"], "kwargs": {}},
            )
        )
