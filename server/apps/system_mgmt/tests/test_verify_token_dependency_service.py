"""Token 校验保留依赖异常，不将数据库不可用伪装成凭据失效。"""

import pytest
from django.db import InterfaceError, OperationalError


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_verify_token_propagates_database_failure(monkeypatch, error_type):
    from apps.system_mgmt.nats import auth

    error = error_type("database unavailable")

    def fail(token):
        raise error

    monkeypatch.setattr(auth, "_verify_token", fail)
    with pytest.raises(error_type) as caught:
        auth.verify_token("test-token")
    assert caught.value is error


def test_verify_token_preserves_invalid_credential_response(monkeypatch):
    from apps.system_mgmt.nats import auth

    def invalid(token):
        raise Exception("Token is invalid")

    monkeypatch.setattr(auth, "_verify_token", invalid)
    assert auth.verify_token("test-token") == {"result": False, "message": "Token is invalid"}
