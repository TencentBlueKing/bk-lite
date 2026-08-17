"""运营分析 NATS 目录查询的可信调用契约。"""

import pytest
from django.core import signing
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
    monkeypatch.delenv("OPERATION_ANALYSIS_NATS_ALLOW_UNSIGNED", raising=False)
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
        nats_module.get_operation_analysis_module_data(
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
        nats_module.get_operation_analysis_module_data(**_request_params(group_id=999), _internal_auth="forged")


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
        nats_module.get_operation_analysis_module_data(**request_params, _internal_auth=token)


def test_get_module_data_accepts_exact_signed_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: captured.update(kwargs) or {"count": 1, "items": []},
    )
    params = _request_params(group_id=1)

    result = nats_module.get_operation_analysis_module_data(**params, _internal_auth=_sign_request(**params))

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
        nats_module.get_operation_analysis_module_data(**params, _internal_auth=_sign_request(**params))


def test_get_module_data_legacy_rollback_is_explicit_and_audited(monkeypatch, caplog):
    monkeypatch.setenv("OPERATION_ANALYSIS_NATS_ALLOW_UNSIGNED", "true")
    nats_module._warn_legacy_unsigned_once.cache_clear()
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: {"count": 1, "items": []},
    )

    first_result = nats_module.get_operation_analysis_module_data(**_request_params(group_id=1))
    second_result = nats_module.get_operation_analysis_module_data(**_request_params(group_id=1))

    assert first_result == second_result == {"count": 1, "items": []}
    assert caplog.text.count("Accepted legacy unsigned operation analysis NATS request") == 1


def test_get_module_data_legacy_rollback_does_not_accept_invalid_auth(monkeypatch):
    monkeypatch.setenv("OPERATION_ANALYSIS_NATS_ALLOW_UNSIGNED", "true")
    monkeypatch.setattr(
        nats_module.DictDirectoryService,
        "get_operation_analysis_module_data",
        lambda **kwargs: pytest.fail("错误令牌不得通过 legacy 回滚开关"),
    )

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.get_operation_analysis_module_data(**_request_params(group_id=1), _internal_auth="forged")


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
    result = nats_module.get_operation_analysis_module_data(**rpc_call["kwargs"])

    assert rpc_call["method_name"] == "get_operation_analysis_module_data"
    assert captured == params
    assert result == {"count": 1, "items": []}
