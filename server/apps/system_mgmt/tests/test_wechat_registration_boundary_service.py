import pytest

import nats_client
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt import nats_api
from apps.system_mgmt.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_wechat_user_register_keeps_local_app_client_path(monkeypatch):
    monkeypatch.setattr(nats_api._wechat, "_build_jwt_payload", lambda user_id: {"user_id": user_id})
    monkeypatch.setattr(nats_api._wechat.jwt, "encode", lambda **kwargs: "local-wechat-token")

    result = SystemMgmt().wechat_user_register("wechat-local-user", "WeChat Local User")

    assert result["result"] is True
    assert result["data"]["token"] == "local-wechat-token"
    assert User.objects.filter(username="wechat-local-user").exists()
    assert "bklite.wechat_user_register" not in nats_client.registry.default_registry.registry
