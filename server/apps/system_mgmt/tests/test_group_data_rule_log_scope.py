import json
import types

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet


def _request_user(group_ids, *, is_superuser=False):
    return types.SimpleNamespace(
        username="log-scope-operator",
        domain="domain.com",
        locale="en",
        is_authenticated=True,
        is_superuser=is_superuser,
        permission={"system-manager": {"data_permission-View"}},
        group_list=[{"id": group_id} for group_id in group_ids],
    )


def _get_log_app_data(monkeypatch, *, group_ids, group_id, is_superuser=False):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "log",
            "module": "log_group",
            "child_module": "",
            "page": "1",
            "page_size": "10",
            "group_id": group_id,
        },
    )
    force_authenticate(request, user=_request_user(group_ids, is_superuser=is_superuser))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    return response, json.loads(response.content), captured


def test_log_get_app_data_rejects_unauthorized_group(monkeypatch):
    response, payload, captured = _get_log_app_data(monkeypatch, group_ids=[7], group_id="8")

    assert response.status_code == 403
    assert payload == {
        "result": False,
        "message": "You do not have permission to access this group.",
    }
    assert captured == {}


def test_log_get_app_data_allows_authorized_group(monkeypatch):
    response, payload, captured = _get_log_app_data(monkeypatch, group_ids=[7], group_id="7")

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured == {
        "module": "log_group",
        "child_module": "",
        "page": 1,
        "page_size": 10,
        "group_id": "7",
    }


def test_log_get_app_data_allows_superuser(monkeypatch):
    response, payload, captured = _get_log_app_data(monkeypatch, group_ids=[], group_id="8", is_superuser=True)

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured == {
        "module": "log_group",
        "child_module": "",
        "page": 1,
        "page_size": 10,
        "group_id": "8",
    }


def test_log_get_app_data_rejects_invalid_group_id(monkeypatch):
    response, payload, captured = _get_log_app_data(monkeypatch, group_ids=[7], group_id="invalid")

    assert response.status_code == 400
    assert payload == {"result": False, "message": "group_id 参数非法"}
    assert captured == {}
