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


def test_dashboard_handlers_require_a_token_bound_to_team_and_action(monkeypatch):
    from apps.operation_analysis.nats.auth import sign_dashboard_request

    seen = {}

    def fake_briefs(team_id, group_ids=None):
        seen["team_id"] = team_id
        seen["group_ids"] = group_ids
        return [{"id": 2}]

    def fake_prepare(proposal, briefs):
        seen["proposal"] = proposal
        seen["briefs"] = briefs
        return {"ok": True}

    def fake_search(requirements, briefs):
        seen["requirements"] = requirements
        seen["search_briefs"] = briefs
        return [{"id": 2}]

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_proposal_service.list_visible_briefs",
        fake_briefs,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_proposal_service.prepare_dashboard_proposal",
        fake_prepare,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_proposal_service.search_briefs",
        fake_search,
    )

    class FakeMgmt:
        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            seen["include_children"] = include_children
            if actor_context.get("username") == "intruder":
                return {"result": True, "data": []}
            return {"result": True, "data": [7, 9] if include_children else [7]}

    monkeypatch.setattr(nats_module, "SystemMgmt", lambda: FakeMgmt())
    user_info = {"user": "alice", "domain": "default", "team": 7, "include_children": False}

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources([], 7)
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources([], "nope", _internal_auth="forged")

    list_token = sign_dashboard_request(7, "search_dashboard_data_sources", user_info)
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources([], 8, _internal_auth=list_token)
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.prepare_dashboard_proposal({}, 7, _internal_auth=list_token)

    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources([{"text": "告警趋势"}], 7, _internal_auth=list_token)
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources(
            [{"text": "告警趋势"}],
            7,
            user_info={**user_info, "user": "intruder"},
            _internal_auth=list_token,
        )

    with pytest.raises(ValueError, match="requirements must be a list of objects"):
        nats_module.search_dashboard_data_sources(["告警趋势"], 7, user_info=user_info, _internal_auth=list_token)
    assert "requirements" not in seen

    listed = nats_module.search_dashboard_data_sources(
        [{"text": "告警趋势"}],
        7,
        user_info=user_info,
        _internal_auth=list_token,
    )
    assert listed == {"candidates": [{"id": 2}]}
    assert seen["team_id"] == 7
    assert seen["group_ids"] == [7]
    assert seen["include_children"] is False
    assert seen["requirements"] == [{"text": "告警趋势"}]
    assert seen["search_briefs"] == [{"id": 2}]

    child_info = {**user_info, "include_children": True}
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources(
            [{"text": "告警趋势"}],
            7,
            user_info=child_info,
            _internal_auth=list_token,
        )
    with pytest.raises(PermissionDenied, match="NATS authentication failed"):
        nats_module.search_dashboard_data_sources(
            [{"text": "告警趋势"}],
            7,
            user_info={**user_info, "user": "bob"},
            _internal_auth=list_token,
        )
    assert seen["group_ids"] == [7]
    assert seen["include_children"] is False

    child_token = sign_dashboard_request(7, "search_dashboard_data_sources", child_info)
    nats_module.search_dashboard_data_sources(
        [{"text": "告警趋势"}],
        7,
        user_info=child_info,
        _internal_auth=child_token,
    )
    assert seen["group_ids"] == [7, 9]
    assert seen["include_children"] is True

    prepare_token = sign_dashboard_request(7, "prepare_dashboard_proposal", user_info)
    prepared = nats_module.prepare_dashboard_proposal(
        {"schemaVersion": "1.0"},
        7,
        user_info=user_info,
        _internal_auth=prepare_token,
    )
    assert prepared == {"ok": True}
    assert seen["briefs"] == [{"id": 2}]
    assert seen["proposal"] == {"schemaVersion": "1.0"}

    within_requirements = [{"text": "告警趋势"}] * nats_module.MAX_DASHBOARD_REQUIREMENTS
    nats_module.search_dashboard_data_sources(within_requirements, 7, user_info=user_info, _internal_auth=list_token)
    assert seen["requirements"] == within_requirements
    with pytest.raises(ValueError, match="requirements exceed the dashboard search limit"):
        nats_module.search_dashboard_data_sources(
            within_requirements + [{"text": "再一条"}],
            7,
            user_info=user_info,
            _internal_auth=list_token,
        )
    assert seen["requirements"] == within_requirements

    within_layout = [{"valueConfig": {"chartType": "single"}}] * nats_module.MAX_DASHBOARD_LAYOUT_ITEMS
    accepted = nats_module.prepare_dashboard_proposal(
        {"schemaVersion": "1.0", "layout": within_layout},
        7,
        user_info=user_info,
        _internal_auth=prepare_token,
    )
    assert accepted == {"ok": True}
    assert seen["proposal"]["layout"] == within_layout
    with pytest.raises(ValueError, match="layout exceeds the dashboard proposal limit"):
        nats_module.prepare_dashboard_proposal(
            {"schemaVersion": "1.0", "layout": within_layout + [{"valueConfig": {"chartType": "single"}}]},
            7,
            user_info=user_info,
            _internal_auth=prepare_token,
        )
    assert seen["proposal"]["layout"] == within_layout


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
    subject = next(key for key, registration in default_registry.registry.items() if registration["name"] == rpc_call["method_name"])

    result = await nats_handler(subject, {"kwargs": rpc_call["kwargs"]})

    assert result == {"count": 1, "items": [7]}
