from unittest.mock import patch

from apps.system_mgmt.providers.builtin.feishu.adapters.im_notification import FeishuIMNotificationAdapter


class _FeishuResponse:
    status_code = 200
    headers = {"X-Tt-Logid": "req-1"}

    def __init__(self, items=None, *, data=None, request_id="req-1"):
        self.items = items or []
        self.data = data
        self.headers = {"X-Tt-Logid": request_id}

    def json(self):
        return {"code": 0, "data": self.data or {"items": self.items, "has_more": False}}


class _FeishuDeniedResponse:
    status_code = 200
    headers = {"X-Tt-Logid": "denied"}

    @staticmethod
    def json():
        return {"code": 40004, "msg": "no permission"}


def test_list_external_users_walks_partial_visible_departments_not_company_root():
    requested = []

    def get_contact_data(url, **kwargs):
        requested.append({"url": url, "params": dict(kwargs.get("params") or {})})
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["dept-a"], "has_more": False})
        if url.endswith("/departments/dept-a/children"):
            return _FeishuResponse(
                [{"department_id": "dept-a1", "name": "后端组", "parent_department_id": "dept-a"}]
            )
        if "find_by_department" in url:
            department_id = kwargs["params"]["department_id"]
            if department_id == "0":
                return _FeishuDeniedResponse()
            users = {
                "dept-a": [{"user_id": "root-user", "open_id": "ou_root", "name": "根组用户"}],
                "dept-a1": [{"user_id": "child-user", "open_id": "ou_child", "name": "子组用户"}],
            }
            return _FeishuResponse(users[department_id])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.im_notification._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.builtin.feishu.adapters.client.requests.get", side_effect=get_contact_data):
        result = FeishuIMNotificationAdapter.list_external_users({}, "feishu", "im_notification")

    assert result.success is True
    assert sorted(user["user_id"] for user in result.payload["external_users"]) == ["child-user", "root-user"]
    user_calls = [item for item in requested if "find_by_department" in item["url"]]
    assert [item["params"]["department_id"] for item in user_calls] == ["0", "dept-a", "dept-a1"]
    assert all(item["params"]["user_id_type"] == "user_id" for item in user_calls)
    assert all(item["params"]["department_id_type"] == "department_id" for item in user_calls)
    assert all("/departments/0/" not in item["url"] for item in requested)


def test_list_external_users_includes_company_root_members_when_scopes_omit_zero():
    requested = []

    def get_contact_data(url, **kwargs):
        requested.append({"url": url, "params": dict(kwargs.get("params") or {})})
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["dept-a"], "has_more": False})
        if url.endswith("/departments/dept-a/children"):
            return _FeishuResponse([])
        if "find_by_department" in url:
            department_id = kwargs["params"]["department_id"]
            users = {
                "0": [{"user_id": "root-direct", "open_id": "ou_root", "name": "根组织用户"}],
                "dept-a": [{"user_id": "dept-user", "open_id": "ou_dept", "name": "部门用户"}],
            }
            return _FeishuResponse(users[department_id])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.im_notification._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.builtin.feishu.adapters.client.requests.get", side_effect=get_contact_data):
        result = FeishuIMNotificationAdapter.list_external_users({}, "feishu", "im_notification")

    assert result.success is True
    assert sorted(user["user_id"] for user in result.payload["external_users"]) == ["dept-user", "root-direct"]
    user_calls = [item for item in requested if "find_by_department" in item["url"]]
    assert [item["params"]["department_id"] for item in user_calls] == ["0", "dept-a"]


def test_list_external_users_uses_company_root_when_scope_is_all_members():
    requested = []

    def get_contact_data(url, **kwargs):
        requested.append({"url": url, "params": dict(kwargs.get("params") or {})})
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["0"], "has_more": False})
        if url.endswith("/departments/0/children"):
            return _FeishuResponse(
                [{"department_id": "dept-a", "name": "研发部", "parent_department_id": "0"}]
            )
        if "find_by_department" in url:
            department_id = kwargs["params"]["department_id"]
            users = {
                "0": [{"user_id": "3cc3b1a8", "open_id": "ou_root", "name": "赵"}],
                "dept-a": [{"user_id": "synced-user", "open_id": "ou_synced", "name": "已同步用户"}],
            }
            return _FeishuResponse(users[department_id])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.im_notification._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.builtin.feishu.adapters.client.requests.get", side_effect=get_contact_data):
        result = FeishuIMNotificationAdapter.list_external_users({}, "feishu", "im_notification")

    assert result.success is True
    assert sorted(user["user_id"] for user in result.payload["external_users"]) == ["3cc3b1a8", "synced-user"]
    user_calls = [item for item in requested if "find_by_department" in item["url"]]
    assert [item["params"]["department_id"] for item in user_calls] == ["0", "dept-a"]


def test_list_external_users_skips_company_root_children_permission_denied_without_failing():
    requested = []

    def get_contact_data(url, **kwargs):
        requested.append({"url": url, "params": dict(kwargs.get("params") or {})})
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": [], "has_more": False})
        if url.endswith("/departments/0/children"):
            return _FeishuDeniedResponse()
        if "find_by_department" in url:
            department_id = kwargs["params"]["department_id"]
            if department_id == "0":
                return _FeishuDeniedResponse()
            raise AssertionError(f"unexpected department_id={department_id}")
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.im_notification._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.builtin.feishu.adapters.client.requests.get", side_effect=get_contact_data):
        result = FeishuIMNotificationAdapter.list_external_users({}, "feishu", "im_notification")

    assert result.success is True
    assert result.payload["external_users"] == []
    assert any(item["url"].endswith("/departments/0/children") for item in requested)
    assert any("find_by_department" in item["url"] for item in requested)
