import sys
import types
from unittest.mock import MagicMock


def test_manageone_token_is_returned_without_entering_logs(monkeypatch):
    requests_module = types.ModuleType("requests")
    requests_module.request = MagicMock()
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    monkeypatch.delitem(
        sys.modules,
        "common.cmp.cloud_apis.resource_apis.cw_manageone",
        raising=False,
    )
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    token = "manageone-secret-token"
    logger = MagicMock()
    client = object.__new__(cw_manageone.CwManageOne)
    client.basic_url = "https://manageone.example"
    client.cw_headers = {"Content-Type": "application/json"}
    client.account = "operator"
    client.password = "password"
    client._handle_request = lambda *args, **kwargs: {
        "result": True,
        "data": {"accessSession": token},
    }
    monkeypatch.setattr(cw_manageone, "logger", logger)

    assert client.get_token() == token
    logger.debug.assert_called_once_with(
        "manageone.token_acquired token_present=%s",
        True,
    )
    assert token not in repr(logger.mock_calls)


def test_manageone_request_logs_exclude_credentials_and_raw_response(monkeypatch):
    requests_module = types.ModuleType("requests")
    response = MagicMock()
    response.status_code = 401
    response.content = b'rejected password="response-secret"'
    requests_module.request = MagicMock(return_value=response)
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    logger = MagicMock()
    monkeypatch.setattr(
        cw_manageone.requests,
        "request",
        MagicMock(return_value=response),
        raising=False,
    )
    monkeypatch.setattr(cw_manageone, "logger", logger)

    result = cw_manageone.handle_request(
        "PUT",
        "https://manageone.example/token",
        headers={"X-Auth-Token": "header-secret"},
        json={"value": "password-secret"},
    )

    assert result["result"] is False
    logged = repr(logger.mock_calls)
    assert "header-secret" not in logged
    assert "password-secret" not in logged
    assert "response-secret" not in logged
    logger.error.assert_called_once_with(
        "manageone.request.failed method=%s url=%s failed_stage=%s status_code=%s",
        "PUT",
        "https://manageone.example/token",
        "http_response",
        401,
    )
    assert "header-secret" not in repr(result)
    assert "password-secret" not in repr(result)
    assert "response-secret" not in repr(result)


def test_manageone_success_log_is_bounded(monkeypatch):
    requests_module = types.ModuleType("requests")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"result": "ok"}
    requests_module.request = MagicMock(return_value=response)
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    logger = MagicMock()
    monkeypatch.setattr(
        cw_manageone.requests,
        "request",
        MagicMock(return_value=response),
        raising=False,
    )
    monkeypatch.setattr(cw_manageone, "logger", logger)

    result = cw_manageone.handle_request(
        "PUT",
        "https://manageone.example/token",
        headers={"X-Auth-Token": "header-secret"},
        json={"value": "password-secret"},
    )

    assert result == {"result": True, "data": {"result": "ok"}}
    logger.debug.assert_called_once_with(
        "manageone.request.completed method=%s url=%s status_code=%s",
        "PUT",
        "https://manageone.example/token",
        200,
    )
    assert "header-secret" not in repr(logger.mock_calls)
    assert "password-secret" not in repr(logger.mock_calls)


def test_manageone_transport_failure_owns_traceback_without_credentials(monkeypatch):
    requests_module = types.ModuleType("requests")
    requests_module.request = MagicMock(side_effect=RuntimeError("connection failed"))
    monkeypatch.setitem(sys.modules, "requests", requests_module)
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    logger = MagicMock()
    monkeypatch.setattr(
        cw_manageone.requests,
        "request",
        MagicMock(side_effect=RuntimeError("connection failed")),
        raising=False,
    )
    monkeypatch.setattr(cw_manageone, "logger", logger)

    result = cw_manageone.handle_request(
        "PUT",
        "https://manageone.example/token",
        headers={"X-Auth-Token": "header-secret"},
        json={"value": "password-secret"},
    )

    assert result["result"] is False
    logger.exception.assert_called_once_with(
        "manageone.request.failed method=%s url=%s failed_stage=%s",
        "PUT",
        "https://manageone.example/token",
        "transport",
    )
    assert "header-secret" not in repr(logger.mock_calls)
    assert "password-secret" not in repr(logger.mock_calls)
