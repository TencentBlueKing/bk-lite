"""旧 apps.system_mgmt.nats_api 路径兼容层回归测试。"""
import types

from apps.system_mgmt import nats_api


def test_nats_api_compat_syncs_sensitive_monkeypatch_helpers(monkeypatch):
    def fake_verify_token(token):
        return types.SimpleNamespace(username="alice", domain="domain.com")

    def fake_build_jwt_payload(user_id):
        return {"patched_user_id": user_id}

    monkeypatch.setattr(nats_api, "_verify_token", fake_verify_token)
    monkeypatch.setattr(nats_api, "_build_jwt_payload", fake_build_jwt_payload)

    nats_api._sync_compat_globals()

    assert nats_api._auth._verify_token is fake_verify_token
    assert nats_api._login._verify_token is fake_verify_token
    assert nats_api._login._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._otp._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._settings._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._wechat._build_jwt_payload is fake_build_jwt_payload


def test_reset_pwd_uses_legacy_nats_api_verify_token_patch(monkeypatch):
    monkeypatch.setattr(
        nats_api,
        "_verify_token",
        lambda token: types.SimpleNamespace(username="bob", domain="domain.com"),
    )

    result = nats_api.reset_pwd("alice", "domain.com", "ValidPass1!", caller_token="bob-token")

    assert result == {"result": False, "message": "Unauthorized: caller does not match target user"}


def test_get_user_login_token_uses_legacy_nats_api_jwt_payload_patch(monkeypatch):
    captured = {}

    def fake_build_jwt_payload(user_id):
        return {"patched_user_id": user_id}

    def fake_jwt_encode(**kwargs):
        captured.update(kwargs)
        return "patched-token"

    class EmptySystemSettings:
        class objects:
            @staticmethod
            def filter(key):
                return types.SimpleNamespace(first=lambda: None)

    user = types.SimpleNamespace(
        id=42,
        username="alice",
        display_name="Alice",
        domain="domain.com",
        locale="zh-Hans",
        timezone="Asia/Shanghai",
        temporary_pwd=False,
        disabled=False,
        otp_secret="",
        last_login=None,
        save=lambda: None,
    )
    monkeypatch.setattr(nats_api, "_build_jwt_payload", fake_build_jwt_payload)
    monkeypatch.setattr(nats_api._login, "SystemSettings", EmptySystemSettings)
    monkeypatch.setattr(nats_api.jwt, "encode", fake_jwt_encode)

    result = nats_api.get_user_login_token(user, "alice")

    assert result["result"] is True
    assert result["data"]["token"] == "patched-token"
    assert captured["payload"] == {"patched_user_id": 42}
