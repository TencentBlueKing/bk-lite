"""系统管理代理运营分析目录查询时的组织授权契约。"""

from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet


def _get_operation_analysis_app_data(monkeypatch, api_client, authenticated_user, *, group_ids, group_id, is_superuser=False):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))
    authenticated_user.group_list = [{"id": item} for item in group_ids]
    authenticated_user.is_superuser = is_superuser
    authenticated_user.permission = {"system-manager": {"data_permission-View"}}
    api_client.force_authenticate(user=authenticated_user)
    response = api_client.get(
        "/api/v1/system_mgmt/group_data_rule/get_app_data/",
        {
            "app": "ops-analysis",
            "module": "directory",
            "child_module": "dashboard",
            "page": "1",
            "page_size": "10",
            "group_id": group_id,
        },
    )
    return response, response.json(), captured


def test_operation_analysis_get_app_data_rejects_unauthorized_group(monkeypatch, api_client, authenticated_user):
    response, payload, captured = _get_operation_analysis_app_data(
        monkeypatch, api_client, authenticated_user, group_ids=[7], group_id="8"
    )

    assert response.status_code == 403
    assert payload == {
        "result": False,
        "message": "You do not have permission to access this group.",
    }
    assert captured == {}


def test_operation_analysis_get_app_data_allows_authorized_group(monkeypatch, api_client, authenticated_user):
    response, payload, captured = _get_operation_analysis_app_data(
        monkeypatch, api_client, authenticated_user, group_ids=[7], group_id="7"
    )

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured == {
        "module": "directory",
        "child_module": "dashboard",
        "page": 1,
        "page_size": 10,
        "group_id": "7",
    }


def test_operation_analysis_get_app_data_allows_superuser(monkeypatch, api_client, authenticated_user):
    response, payload, captured = _get_operation_analysis_app_data(
        monkeypatch,
        api_client,
        authenticated_user,
        group_ids=[],
        group_id="8",
        is_superuser=True,
    )

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured["group_id"] == "8"


def test_operation_analysis_get_app_data_rejects_invalid_group_id(monkeypatch, api_client, authenticated_user):
    response, payload, captured = _get_operation_analysis_app_data(
        monkeypatch, api_client, authenticated_user, group_ids=[7], group_id="invalid"
    )

    assert response.status_code == 400
    assert payload == {"result": False, "message": "group_id parameter is invalid"}
    assert captured == {}
