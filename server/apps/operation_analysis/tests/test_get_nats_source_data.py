# -- coding: utf-8 --
# Tests for apps.operation_analysis.common.get_nats_source_data
# Regression tests for issue #3702: int(get_current_team()) has no guard,
# cookie anomaly triggers 500.
import importlib
import types

import pytest
from rest_framework.exceptions import ValidationError

from apps.operation_analysis.common.get_nats_source_data import GetNatsData


def _make_request(current_team_cookie=None, api_team=None, username="testuser", locale="en", group_tree=None):
    """Build a minimal fake request object."""
    user = types.SimpleNamespace(
        username=username,
        domain="domain.com",
        locale=locale,
        timezone="Asia/Shanghai",
        permission={},
        group_tree=list(group_tree or []),
        is_superuser=False,
    )
    cookies = {}
    if current_team_cookie is not None:
        cookies["current_team"] = current_team_cookie

    request = types.SimpleNamespace(
        user=user,
        COOKIES=cookies,
    )
    if api_team is not None:
        request._api_current_team = api_team
    return request


def _make_get_nats_data(request):
    """Instantiate GetNatsData without calling __init__ so we can call
    update_request_params() in isolation with full control."""
    obj = GetNatsData.__new__(GetNatsData)
    obj.request = request
    obj.params = {}
    obj.param_specs = []
    return obj


class _Namespace:
    id = 1
    name = "custom"
    namespace = "custom_namespace"
    account = "nats-user"
    decrypt_password = "plain-secret"
    domain = "nats.example.com"
    enable_tls = False


class TestNamespaceCredentials:
    def test_instance_state_does_not_retain_plaintext_credentials(self):
        obj = GetNatsData(
            namespace="custom",
            path="query",
            namespace_list=[_Namespace()],
            request=_make_request(current_team_cookie="1"),
        )

        assert obj.namespace_server_map == {1: "nats://nats.example.com:4222"}
        assert "plain-secret" not in repr(obj.__dict__)

    def test_credentials_are_only_passed_at_rpc_call_boundary(self):
        captured = {}

        class FakeClient:
            DEFAULT_NATS = True

            def __init__(self, **kwargs):
                captured["init"] = kwargs

            def get_customization_nast_data(self, **kwargs):
                captured["call"] = kwargs
                return {"ok": True}

        class TestGetNatsData(GetNatsData):
            @property
            def default_nats_client(self):
                return FakeClient

        obj = TestGetNatsData(
            namespace="custom",
            path="query",
            namespace_list=[_Namespace()],
            request=_make_request(current_team_cookie="1"),
        )

        assert obj.get_data() == {"ok": True}
        assert captured["init"]["server"] == "nats://nats.example.com:4222"
        assert captured["call"]["_nats_user"] == "nats-user"
        assert captured["call"]["_nats_password"] == "plain-secret"
        assert "organization_param" not in captured["call"]


class TestUpdateRequestParamsGuard:
    """
    Regression: int(get_current_team()) must not raise TypeError/ValueError.
    If this fix is reverted (the try/except removed), calling int(None) will
    raise TypeError and all tests in this class will fail — confirming coverage.
    """

    def test_valid_cookie_sets_team_int(self):
        """Normal flow: valid current_team cookie produces an integer team."""
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_api_key_injected_team_sets_team_int(self):
        """API key path: _api_current_team attribute is used and converted to int."""
        request = _make_request(api_team="42")
        obj = _make_get_nats_data(request)
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 42

    def test_missing_cookie_raises_validation_error_not_type_error(self):
        """
        Core regression: when current_team cookie is absent, update_request_params()
        must raise ValidationError (400-serialisable) instead of letting
        int(None) bubble up as a TypeError (which becomes a 500).

        Reverting the fix restores `team = int(get_current_team(self.request))`
        which raises TypeError for None → this test will fail.
        """
        request = _make_request(current_team_cookie=None)
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_non_numeric_cookie_raises_validation_error_not_value_error(self):
        """
        Edge case: a corrupt/tampered current_team cookie that is not numeric.
        Must raise ValidationError instead of raw ValueError.
        """
        request = _make_request(current_team_cookie="not-a-number")
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_empty_string_cookie_raises_validation_error(self):
        """Empty string for current_team is also invalid."""
        request = _make_request(current_team_cookie="")
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_organization_param_overrides_cookie_team(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "12", "organization_param": "organization"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 12
        assert obj.params["organization"] == "12"
        assert "organization_param" not in obj.params

    def test_renamed_organization_marker_overrides_cookie_team(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.params = {"org_id": "12", "organization_param": "org_id"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 12

    def test_organization_name_without_marker_or_spec_keeps_cookie_team(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "12"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_select_named_organization_does_not_override(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.param_specs = [
            {
                "name": "organization",
                "inputConfig": {"control": "select", "optionsSource": {"type": "static", "staticItems": []}},
            }
        ]
        obj.params = {"organization": "12"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_datasource_spec_control_overrides_without_marker(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.param_specs = [{"name": "org_id", "inputConfig": {"control": "organization"}}]
        obj.params = {"org_id": "12"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 12

    def test_legacy_input_mode_spec_overrides_without_marker(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.param_specs = [{"name": "organization", "inputMode": "organization"}]
        obj.params = {"organization": "12"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 12

    def test_marker_wins_without_requiring_datasource_control(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": [{"id": 12, "subGroups": []}]}],
        )
        obj = _make_get_nats_data(request)
        obj.param_specs = [
            {
                "name": "organization",
                "inputConfig": {"control": "select", "optionsSource": {"type": "static", "staticItems": []}},
            }
        ]
        obj.params = {"team_scope": "12", "organization_param": "team_scope"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 12

    def test_multiple_organization_specs_raise_validation_error(self):
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.param_specs = [
            {"name": "org_a", "inputConfig": {"control": "organization"}},
            {"name": "org_b", "inputMode": "organization"},
        ]
        obj.params = {"org_a": "12", "org_b": "7"}
        with pytest.raises(ValidationError, match="多个组织控件"):
            obj.update_request_params()

    def test_marker_with_multiple_organization_specs_raises_validation_error(self):
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.param_specs = [
            {"name": "org_a", "inputConfig": {"control": "organization"}},
            {"name": "org_b", "inputMode": "organization"},
        ]
        obj.params = {"org_a": "12", "organization_param": "org_a"}
        with pytest.raises(ValidationError, match="多个组织控件"):
            obj.update_request_params()

    def test_forged_organization_param_clears_team(self):
        request = _make_request(
            current_team_cookie="7",
            group_tree=[{"id": 7, "subGroups": []}],
        )
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "12", "organization_param": "organization"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] is None

    def test_organization_matching_cookie_is_allowed_without_group_tree(self):
        request = _make_request(current_team_cookie="7", group_tree=[])
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "7", "organization_param": "organization"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_empty_organization_param_keeps_cookie_team(self):
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "", "organization_param": "organization"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_invalid_organization_param_keeps_cookie_team(self):
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.params = {"organization": "not-a-team", "organization_param": "organization"}
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_valid_team_user_info_structure(self, monkeypatch):
        """Sanity check: user_info dict is correctly populated on success."""
        module = importlib.import_module("apps.operation_analysis.common.get_nats_source_data")
        monkeypatch.setattr(module.translation, "get_language", lambda: "en")
        request = _make_request(current_team_cookie="5")
        obj = _make_get_nats_data(request)
        obj.update_request_params()

        info = obj.params["user_info"]
        assert info["team"] == 5
        assert info["user"] == "testuser"
        assert info["domain"] == "domain.com"
        assert info["locale"] == "en"
        assert info["timezone"] == "Asia/Shanghai"
        assert isinstance(info["permission"], dict)
        assert isinstance(info["group_tree"], list)
        assert info["is_superuser"] is False
        assert isinstance(info["include_children"], bool)

    def test_active_authenticated_locale_overrides_stale_request_user_locale(self, monkeypatch):
        request = _make_request(current_team_cookie="5", locale="zh-Hans")
        module = importlib.import_module("apps.operation_analysis.common.get_nats_source_data")
        monkeypatch.setattr(module.translation, "get_language", lambda: "en")
        obj = _make_get_nats_data(request)

        obj.update_request_params()

        assert obj.params["user_info"]["locale"] == "en"


class TestLocalRpcOverlayHandlers:
    """IS_LOCAL_RPC=1 时叠色两个 rest_api 走本进程，避免远端旧 NATS worker 无 responder。"""

    @pytest.mark.parametrize(
        "namespace,path,module",
        [
            ("cmdb", "get_monitor_ids_by_inst_uuids", "apps.cmdb.nats.nats"),
            ("monitor", "query_latest_active_alerts", "apps.monitor.nats.monitor"),
            ("monitor", "query_latest_interface_metrics", "apps.monitor.nats.monitor"),
        ],
    )
    def test_overlay_apis_use_app_client_when_is_local_rpc(self, monkeypatch, namespace, path, module):
        monkeypatch.setenv("IS_LOCAL_RPC", "1")
        captured = {}

        class FakeAppClient:
            def __init__(self, client_path):
                captured["path"] = client_path

            def run(self, method_name, **kwargs):
                captured["method"] = method_name
                captured["kwargs"] = kwargs
                return {"result": True, "data": {"items": []}}

        class ExplodingNats:
            DEFAULT_NATS = True

            def __init__(self, **kwargs):
                raise AssertionError("IS_LOCAL_RPC overlay path must not call NATS")

        monkeypatch.setattr(
            "apps.operation_analysis.common.get_nats_source_data.AppClient",
            FakeAppClient,
        )

        class LocalGetNatsData(GetNatsData):
            @property
            def default_nats_client(self):
                return ExplodingNats

        obj = LocalGetNatsData(
            namespace=namespace,
            path=path,
            namespace_list=[_Namespace()],
            params={"inst_uuids": ["abc"]} if namespace == "cmdb" else {"instance_ids": ["mon-1"]},
            request=_make_request(current_team_cookie="1"),
        )
        assert obj.get_data() == {"result": True, "data": {"items": []}}
        assert captured["path"] == module
        assert captured["method"] == path
        assert "user_info" in captured["kwargs"]
        assert "organization_param" not in captured["kwargs"]

    def test_unrelated_api_still_uses_nats_when_is_local_rpc(self, monkeypatch):
        monkeypatch.setenv("IS_LOCAL_RPC", "1")
        captured = {}

        class FakeClient:
            DEFAULT_NATS = True

            def __init__(self, **kwargs):
                captured["init"] = kwargs

            def get_customization_nast_data(self, **kwargs):
                captured["call"] = kwargs
                return {"ok": True}

        class TestGetNatsData(GetNatsData):
            @property
            def default_nats_client(self):
                return FakeClient

        obj = TestGetNatsData(
            namespace="cmdb",
            path="get_room_list",
            namespace_list=[_Namespace()],
            request=_make_request(current_team_cookie="1"),
        )
        assert obj.get_data() == {"ok": True}
        assert "init" in captured
