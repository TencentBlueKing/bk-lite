import sys
import types
from unittest.mock import MagicMock


def test_manageone_uses_stargazer_logger():
    from common.cmp.cloud_apis.resource_apis import cw_manageone
    from core.logger import logger

    assert cw_manageone.logger is logger


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
    log_args = logger.debug.call_args.args
    assert log_args[0].startswith("获取运维面token成功")
    assert log_args[1:] == (True,)
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

    assert result == {
        "result": False,
        "message": '请求错误,status_code:401,message:rejected password="response-secret"',
        "data": {},
    }
    logged = repr(logger.mock_calls)
    assert "header-secret" not in logged
    assert "password-secret" not in logged
    assert "response-secret" not in logged
    log_args = logger.error.call_args.args
    assert log_args[0].startswith("请求失败")
    assert log_args[1:] == ("https://manageone.example/token", "PUT", 401)


def test_manageone_request_uses_fixed_transport_timeout(monkeypatch):
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    response = MagicMock(status_code=200)
    response.json.return_value = {"result": "ok"}
    request = MagicMock(return_value=response)
    monkeypatch.setattr(cw_manageone.requests, "request", request)

    assert (
        cw_manageone.handle_request(
            "GET",
            "https://manageone.example/resources",
            timeout=999,
        )["result"]
        is True
    )
    assert request.call_args.kwargs["timeout"] == (10, 60)


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
    log_args = logger.debug.call_args.args
    assert log_args[0].startswith("请求成功")
    assert log_args[1:] == ("https://manageone.example/token", "PUT")
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
    assert "header-secret" in result["message"]
    assert "password-secret" in result["message"]
    log_args = logger.exception.call_args.args
    assert log_args[0].startswith("请求失败")
    assert log_args[1:] == ("https://manageone.example/token", "PUT")
    assert "header-secret" not in repr(logger.mock_calls)
    assert "password-secret" not in repr(logger.mock_calls)


def test_manageone_inventory_returns_data_without_printing_cloud_response(monkeypatch, capsys):
    from common.cmp.cloud_apis.resource_apis import cw_manageone

    client = object.__new__(cw_manageone.ManageOne)
    resources = {
        "list_biz_regions": [{"id": "cloud-1"}],
        "list_hosts": [{"host_id": "host-1", "biz_region_id": "cloud-1"}],
        "list_ds": [{"id": "ds-1", "biz_region_id": "cloud-1"}],
        "list_vms": [{"resource_id": "vm-1", "host_id": "host-1", "floating_ip": "192.0.2.1"}],
        "list_floating_ips": [{"id": "ip-1", "floatingIpAddress": "192.0.2.1"}],
        "list_elb": [{"id": "elb-1"}],
        "list_elb_pool": [{"id": "pool-1", "elbId": "elb-1"}],
        "list_elb_pool_members": [{"vmId": "vm-1", "poolId": "pool-1"}],
    }
    for method_name, data in resources.items():
        client.__dict__[method_name] = lambda data=data: {"result": True, "data": data}
    logger = MagicMock()
    monkeypatch.setattr(cw_manageone, "logger", logger)

    result = client.list_all_resources()

    assert result["result"] == "True"
    assert result["data"]["mo_server"][0]["floating_ip_id"] == "ip-1"
    assert capsys.readouterr().out == ""
    logger.debug.assert_called_once_with(
        "event=manageone_inventory_collected clouds=%s hosts=%s datastores=%s servers=%s floating_ips=%s elbs=%s",
        1,
        1,
        1,
        1,
        1,
        1,
    )
