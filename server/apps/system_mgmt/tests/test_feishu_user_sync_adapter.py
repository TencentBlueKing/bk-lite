from types import SimpleNamespace
from unittest.mock import patch

from apps.system_mgmt.providers.adapters.feishu import FeishuUserSyncAdapter


class _FeishuResponse:
    status_code = 200
    headers = {"X-Tt-Logid": "req-1"}

    def __init__(self, items):
        self.items = items

    def json(self):
        return {"code": 0, "data": {"items": self.items, "has_more": False}}


def test_sync_users_includes_users_in_recursively_discovered_departments():
    source = SimpleNamespace(
        name="飞书测试",
        business_config={"root_department_id": "root", "department_id_type": "department_id"},
    )
    requested_department_ids = []

    def get_contact_data(url, **kwargs):
        if "/departments/root/children" in url:
            return _FeishuResponse(
                [
                    {
                        "department_id": "child",
                        "parent_department_id": "root",
                        "name": "子组织",
                    }
                ]
            )

        department_id = kwargs["params"]["department_id"]
        requested_department_ids.append(department_id)
        users = {
            "root": [{"user_id": "root-user", "name": "根组织用户", "department_ids": ["root"]}],
            "child": [{"user_id": "child-user", "name": "子组织用户", "department_ids": ["child"]}],
        }
        return _FeishuResponse(users[department_id])

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.sync_users({}, "feishu", "user_sync", source=source)

    assert result.success is True
    assert requested_department_ids == ["root", "child"]
    assert [item["user_id"] for item in result.payload["user_list"]] == ["root-user", "child-user"]


def test_sync_users_deduplicates_users_returned_by_multiple_departments():
    source = SimpleNamespace(name="飞书测试", business_config={"root_department_id": "root"})

    def get_contact_data(url, **kwargs):
        if "/departments/root/children" in url:
            return _FeishuResponse(
                [{"department_id": "child", "parent_department_id": "root", "name": "子组织"}]
            )

        department_id = kwargs["params"]["department_id"]
        return _FeishuResponse(
            [
                {
                    "user_id": "shared-user",
                    "name": "跨组织用户",
                    "department_ids": [department_id],
                }
            ]
        )

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.sync_users({}, "feishu", "user_sync", source=source)

    assert result.success is True
    assert result.payload["user_list"] == [
        {
            "user_id": "shared-user",
            "open_id": "",
            "name": "跨组织用户",
            "email": "",
            "mobile": "",
            "department_ids": ["root", "child"],
        }
    ]
