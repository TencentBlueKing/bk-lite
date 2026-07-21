import types

import pytest
import requests

from apps.cmdb.services.stargazer_collect_trigger import (
    StargazerCollectPermanentError,
    StargazerCollectRetryableError,
    StargazerCollectTriggerClient,
)

pytestmark = pytest.mark.unit


class Response:
    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def task():
    return types.SimpleNamespace(id=7, model_id="host", driver_type="snmp")


def node_params():
    return types.SimpleNamespace(
        custom_headers=lambda: {
            "cmdbplugin_name": "host_info",
            "cmdbpassword": "secret",
            "instance_id": "cmdb_7",
        },
        tags={
            "instance_id": "cmdb_7",
            "instance_type": "cmdb_host",
            "collect_type": "http",
            "config_type": "host",
        },
        env_config=lambda: {},
    )


def patch_node_params(mocker):
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
        return_value=node_params(),
    )


@pytest.mark.parametrize("failure_source", ["factory", "custom_headers"])
def test_request_build_errors_are_permanent_and_sanitized(mocker, failure_source):
    sensitive_message = (
        "token=top-secret broker=nats://user:password@broker.internal:4222"
    )
    if failure_source == "factory":
        mocker.patch(
            "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
            side_effect=ValueError(sensitive_message),
        )
    else:
        params = node_params()
        params.custom_headers = mocker.Mock(side_effect=ValueError(sensitive_message))
        mocker.patch(
            "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
            return_value=params,
        )

    with pytest.raises(StargazerCollectPermanentError) as exc:
        StargazerCollectTriggerClient().trigger(task())

    assert exc.value.__cause__ is None
    assert "top-secret" not in str(exc.value)
    assert "nats://" not in str(exc.value)
    assert "password" not in str(exc.value)


def test_request_build_keeps_defined_trigger_error_classification(mocker):
    expected = StargazerCollectRetryableError("already classified")
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
        side_effect=expected,
    )

    with pytest.raises(StargazerCollectRetryableError) as exc:
        StargazerCollectTriggerClient().trigger(task())

    assert exc.value is expected


def test_queued_builds_same_source_request(mocker):
    patch_node_params(mocker)
    get = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "queued"}),
    )
    result = StargazerCollectTriggerClient().trigger(task())
    assert result.status == "accepted"
    _, kwargs = get.call_args
    assert kwargs["params"] == {}
    assert kwargs["headers"]["cmdbplugin_name"] == "host_info"
    assert kwargs["headers"]["cmdbpassword"] == "secret"
    assert kwargs["headers"]["instance_id"] == "cmdb_7"
    assert kwargs["headers"]["instance_type"] == "cmdb_host"
    assert kwargs["headers"]["collect_type"] == "http"
    assert kwargs["headers"]["config_type"] == "host"
    assert "X-Instance-ID" not in kwargs["headers"]
    assert kwargs["timeout"] == 15


def test_direct_request_resolves_node_password_placeholders(mocker):
    params = node_params()
    params.custom_headers = lambda: {
        "cmdbplugin_name": "aliyun_info",
        "cmdbsecret_id": "${PASSWORD_secret_id_cmdb_7}",
        "cmdbsecret_key": "${PASSWORD_secret_key_cmdb_7}",
    }
    params.env_config = lambda: {
        "PASSWORD_secret_id_cmdb_7": "real-access-key",
        "PASSWORD_secret_key_cmdb_7": "real-access-secret",
    }
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
        return_value=params,
    )
    get = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "queued"}),
    )

    StargazerCollectTriggerClient().trigger(task())

    request_kwargs = get.call_args.kwargs
    assert request_kwargs["params"] == {}
    assert request_kwargs["headers"]["cmdbsecret_id"] == "real-access-key"
    assert request_kwargs["headers"]["cmdbsecret_key"] == "real-access-secret"


def test_direct_request_rejects_unresolved_placeholders(mocker):
    params = node_params()
    params.custom_headers = lambda: {
        "cmdbplugin_name": "aliyun_info",
        "cmdbsecret_id": "${PASSWORD_secret_id_cmdb_7}",
    }
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
        return_value=params,
    )
    get = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "queued"}),
    )

    with pytest.raises(StargazerCollectPermanentError, match="凭据配置无效"):
        StargazerCollectTriggerClient().trigger(task())

    get.assert_not_called()


def test_skipped_is_deduplicated(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "skipped"}),
    )
    assert StargazerCollectTriggerClient().trigger(task()).status == "deduplicated"


def test_complete_batch_is_accepted(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Count": "3", "X-Success-Count": "3"}),
    )
    result = StargazerCollectTriggerClient().trigger(task())
    assert (result.status, result.total, result.accepted) == ("accepted", 3, 3)


def test_partial_batch_is_permanent(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Count": "3", "X-Success-Count": "2"}),
    )
    with pytest.raises(StargazerCollectPermanentError, match="accepted=2, total=3"):
        StargazerCollectTriggerClient().trigger(task())


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Task-Count": "invalid", "X-Success-Count": "1"},
        {"X-Task-Count": "1", "X-Success-Count": "invalid"},
    ],
)
def test_invalid_batch_headers_do_not_keep_exception_cause(mocker, headers):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers=headers),
    )
    with pytest.raises(StargazerCollectPermanentError) as exc:
        StargazerCollectTriggerClient().trigger(task())
    assert exc.value.__cause__ is None


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_5xx_is_retryable(mocker, status_code):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(status_code=status_code),
    )
    with pytest.raises(StargazerCollectRetryableError, match=str(status_code)):
        StargazerCollectTriggerClient().trigger(task())


def test_timeout_error_does_not_leak_secret(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        side_effect=requests.Timeout("secret"),
    )
    with pytest.raises(StargazerCollectRetryableError) as exc:
        StargazerCollectTriggerClient().trigger(task())
    assert "secret" not in str(exc.value)
    assert exc.value.__cause__ is None


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ChunkedEncodingError("secret"),
        requests.exceptions.RetryError("secret"),
    ],
)
def test_recoverable_transport_errors_are_retryable_and_sanitized(mocker, error):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        side_effect=error,
    )
    with pytest.raises(StargazerCollectRetryableError) as exc:
        StargazerCollectTriggerClient().trigger(task())
    assert "secret" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_4xx_is_permanent(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(status_code=400),
    )
    with pytest.raises(StargazerCollectPermanentError, match="HTTP 400"):
        StargazerCollectTriggerClient().trigger(task())
