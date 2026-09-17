import pytest
from enterprise.plugins.inputs.smartx.smartx_info import SmartXManager


def test_smartx_login_verifies_tls_certificate():
    manager = SmartXManager({"host": "smartx.example", "username": "ops", "password": "fixture-secret"})
    sent = []

    def fake_handle(method, url, **kwargs):
        sent.append(kwargs)
        return {"result": True, "data": {"data": {"token": "fixture-token"}}}

    manager._handle_request = fake_handle

    assert manager.login() == "fixture-token"
    assert sent[0].get("verify", True) is True


def test_smartx_rejects_disabled_tls_verification():
    with pytest.raises(ValueError, match="TLS"):
        SmartXManager({"host": "smartx.example", "scheme": "https", "verify_tls": False})
