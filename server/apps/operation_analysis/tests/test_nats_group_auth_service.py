"""运营分析 NATS 目录查询的可信调用契约。"""

import pytest
from django.core import signing
from django.test import override_settings
from rest_framework.exceptions import PermissionDenied

from apps.operation_analysis.nats import nats as nats_module

pytestmark = pytest.mark.unit

AUTH_SALT = "apps.operation_analysis.nats.get_operation_analysis_module_data.v1"


def _request_params(group_id=1):
    return {
        "module": "directory",
        "child_module": "dashboard",
        "page": 1,
        "page_size": 100,
        "group_id": group_id,
    }


def _sign_request(**params):
    return signing.dumps(params, salt=AUTH_SALT)


def test_get_module_data_rejects_unsigned_request(monkeypatch):
    called = False

    def fake_get_module_data(**kwargs):
        nonlocal called
        called = True
        return {"count": 1, "items": []}

    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        fake_get_module_data,
    )

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(
            module="directory",
            child_module="dashboard",
            page=1,
            page_size=100,
            group_id=999,
        )

    assert called is False


def test_get_module_data_rejects_forged_auth(monkeypatch):
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("伪造令牌不得到达目录服务"),
    )

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(**_request_params(group_id=999), _internal_auth="forged")


@pytest.mark.parametrize("group_id", [None, "invalid", 0, -1, True, 1.5])
def test_get_module_data_rejects_signed_invalid_group_id(monkeypatch, group_id):
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("非法组织不得到达目录服务"),
    )

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(
            **_request_params(group_id=group_id),
            _internal_auth=signing.dumps(_request_params(group_id=group_id), salt=AUTH_SALT),
        )


@pytest.mark.parametrize("group_id", [None, "invalid", 0, -1, True, 1.5])
def test_rpc_rejects_invalid_group_id_before_publish(group_id):
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    rpc = OperationAnalysisRPC()
    rpc.client = type("FailIfCalled", (), {"run": lambda *args, **kwargs: pytest.fail("非法组织不得发往 NATS")})()

    with pytest.raises(ValueError, match="group_id must be a positive integer"):
        rpc.get_module_data(**_request_params(group_id=group_id))


@pytest.mark.parametrize(
    ("field", "value"),
    [("page", 0), ("page", True), ("page", 1.5), ("page_size", -1), ("page_size", 501), ("page_size", "invalid")],
)
def test_rpc_rejects_invalid_pagination_before_publish(field, value):
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    rpc = OperationAnalysisRPC()
    rpc.client = type("FailIfCalled", (), {"run": lambda *args, **kwargs: pytest.fail("非法分页不得发往 NATS")})()
    params = {**_request_params(group_id=1), field: value}

    with pytest.raises(ValueError, match=field):
        rpc.get_module_data(**params)


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("module", "datasource"),
        ("child_module", "topology"),
        ("page", 2),
        ("page_size", 1000),
        ("group_id", 999),
    ],
)
def test_get_module_data_rejects_signed_parameter_tampering(monkeypatch, field, tampered_value):
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("篡改查询参数不得到达目录服务"),
    )
    signed_params = _request_params(group_id=1)
    request_params = {**signed_params, field: tampered_value}
    token = _sign_request(**signed_params)

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(**request_params, _internal_auth=token)


def test_get_module_data_accepts_exact_signed_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: captured.update(kwargs) or {"count": 1, "items": []},
    )
    params = _request_params(group_id=1)

    result = nats_module.get_operation_analysis_module_data_v2(**params, _internal_auth=_sign_request(**params))

    assert captured == params
    assert result == {"count": 1, "items": []}


def test_get_module_data_rejects_expired_auth(monkeypatch):
    monkeypatch.setenv("OPERATION_ANALYSIS_NATS_AUTH_MAX_AGE", "-1")
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("过期令牌不得到达目录服务"),
    )
    params = _request_params(group_id=1)

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(**params, _internal_auth=_sign_request(**params))


def test_get_module_data_accepts_token_during_secret_key_rotation(monkeypatch):
    params = _request_params(group_id=1)
    with override_settings(SECRET_KEY="old-secret", SECRET_KEY_FALLBACKS=[]):
        token = _sign_request(**params)

    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: {"count": 1, "items": []},
    )
    with override_settings(SECRET_KEY="new-secret", SECRET_KEY_FALLBACKS=["old-secret"]):
        result = nats_module.get_operation_analysis_module_data_v2(**params, _internal_auth=token)

    assert result == {"count": 1, "items": []}


def test_get_module_data_accepts_new_token_on_prepared_old_verifier(monkeypatch):
    params = _request_params(group_id=1)
    with override_settings(SECRET_KEY="new-secret", SECRET_KEY_FALLBACKS=["old-secret"]):
        token = _sign_request(**params)

    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: {"count": 1, "items": []},
    )
    with override_settings(SECRET_KEY="old-secret", SECRET_KEY_FALLBACKS=["new-secret"]):
        result = nats_module.get_operation_analysis_module_data_v2(**params, _internal_auth=token)

    assert result == {"count": 1, "items": []}


def test_new_listener_does_not_register_legacy_subject():
    from nats_client.registry import default_registry

    registered_names = {registration["name"] for registration in default_registry.registry.values()}

    assert "get_operation_analysis_module_data_v2" in registered_names
    assert "get_operation_analysis_module_data" not in registered_names


def test_rpc_timeout_and_caller_retry_stay_on_versioned_subject():
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    calls = []

    class TimeoutOnce:
        def run(self, method_name, **kwargs):
            calls.append((method_name, kwargs))
            if len(calls) == 1:
                raise TimeoutError("simulated NATS timeout")
            return {"count": 0, "items": []}

    rpc = OperationAnalysisRPC()
    rpc.client = TimeoutOnce()
    params = _request_params(group_id=7)

    with pytest.raises(TimeoutError, match="simulated NATS timeout"):
        rpc.get_module_data(**params)
    result = rpc.get_module_data(**params)

    assert result == {"count": 0, "items": []}
    assert [method_name for method_name, _ in calls] == [
        "get_operation_analysis_module_data_v2",
        "get_operation_analysis_module_data_v2",
    ]
    for _, kwargs in calls:
        nats_module.verify_module_data_request(kwargs["_internal_auth"], **params)


def test_operation_analysis_rpc_signature_is_accepted_by_handler(monkeypatch):
    from apps.rpc.operation_analysis import OperationAnalysisRPC

    rpc_call = {}

    class Recorder:
        def run(self, method_name, **kwargs):
            rpc_call["method_name"] = method_name
            rpc_call["kwargs"] = kwargs
            return {"queued": True}

    rpc = OperationAnalysisRPC()
    rpc.client = Recorder()
    params = _request_params(group_id=7)
    rpc.get_module_data(**params)

    captured = {}
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: captured.update(kwargs) or {"count": 1, "items": []},
    )
    handler = getattr(nats_module, rpc_call["method_name"])
    result = handler(**rpc_call["kwargs"])

    assert rpc_call["method_name"] == "get_operation_analysis_module_data_v2"
    assert captured == params
    assert result == {"count": 1, "items": []}


def test_versioned_handler_rejects_unsigned_request(monkeypatch):
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("未签名 v2 请求不得到达目录服务"),
    )

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data_v2(**_request_params(group_id=999))


@pytest.mark.asyncio
async def test_versioned_request_crosses_real_dispatcher(monkeypatch):
    from apps.rpc.operation_analysis import OperationAnalysisRPC
    from nats_client.handlers import nats_handler
    from nats_client.registry import default_registry

    rpc_call = {}
    rpc = OperationAnalysisRPC()
    rpc.client = type(
        "Recorder",
        (),
        {"run": lambda self, method_name, **kwargs: rpc_call.update(method_name=method_name, kwargs=kwargs)},
    )()
    rpc.get_module_data(**_request_params(group_id=7))

    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: {"count": 1, "items": [kwargs["group_id"]]},
    )
    subject = next(
        key
        for key, registration in default_registry.registry.items()
        if registration["name"] == rpc_call["method_name"]
    )

    result = await nats_handler(subject, {"kwargs": rpc_call["kwargs"]})

    assert result == {"count": 1, "items": [7]}
