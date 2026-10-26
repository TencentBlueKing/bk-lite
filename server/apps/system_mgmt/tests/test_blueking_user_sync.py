from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.providers.builtin.blueking.adapters.client import ALL_DEPARTMENT_ID, PAGE_SIZE
from apps.system_mgmt.providers.builtin.blueking.adapters.user_sync import BlueKingUserSyncAdapter

CONFIG = {
    "bk_url": "https://bk.example.com",
    "app_id": "bk-app",
    "app_token": "app-token-sentinel-SECRET",
    "bk_username": "bk-sync-user",
}

DEPARTMENTS = [
    {"id": 1, "name": "Company", "parent": 0},
    {"id": 2, "name": "R&D", "parent": 1},
    {"id": 3, "name": "Finance", "parent": 1},
    {"id": 4, "name": "Backend", "parent": 2},
]
USERS = [
    {
        "username": "alice",
        "display_name": "Alice",
        "email": "alice@example.com",
        "telephone": "13800000001",
        "departments": [{"id": 2}],
    },
    {
        "username": "bob",
        "display_name": "Bob",
        "email": "bob@example.com",
        "telephone": "13800000002",
        "departments": [{"id": 4}, {"id": 3}],
    },
    {
        "username": "carol",
        "display_name": "Carol",
        "email": "carol@example.com",
        "telephone": "13800000003",
        "departments": [{"id": 3}],
    },
]


def response(payload, status_code=200):
    item = MagicMock()
    item.status_code = status_code
    item.json.return_value = payload
    return item


def page_payload(results, count=None):
    return {"result": True, "data": {"count": count if count is not None else len(results), "results": results}}


def _source(root_department_id, include_child=True):
    return SimpleNamespace(
        name="blueking-sync",
        business_config={
            "root_department_id": root_department_id,
            "include_child_departments": include_child,
        },
    )


def test_list_departments_paginates_and_prepends_bk_all():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(DEPARTMENTS[:2], count=4)),
            response(page_payload(DEPARTMENTS[2:], count=4)),
        ],
    ) as get:
        result = BlueKingUserSyncAdapter.list_departments(CONFIG, "blueking", "user_sync", locale="zh-Hans")

    assert result.success is True
    items = result.payload["items"]
    assert items[0]["id"] == ALL_DEPARTMENT_ID
    assert items[0]["name"] == "全部"
    child_ids = {item["id"] for item in items[0]["children"]}
    assert child_ids == {"1"}
    rd = next(item for item in items[0]["children"][0]["children"] if item["id"] == "2")
    assert {child["id"] for child in rd["children"]} == {"4"}
    assert all(call.kwargs["params"]["page_size"] == PAGE_SIZE for call in get.call_args_list)
    assert all(call.kwargs["params"]["bk_username"] == "admin" for call in get.call_args_list)
    assert all("bk_token" not in call.kwargs["params"] for call in get.call_args_list)
    assert [call.kwargs["params"]["page"] for call in get.call_args_list] == [1, 2]
    assert all("bk_all" not in str(call.kwargs["params"]) for call in get.call_args_list)
    assert all(call.args[0] == "https://bk.example.com/api/c/compapi/v2/usermanage/list_departments/" for call in get.call_args_list)


def test_list_departments_accepts_numeric_count_string():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(DEPARTMENTS[:2], count="4")),
            response(page_payload(DEPARTMENTS[2:], count="4")),
        ],
    ) as get:
        result = BlueKingUserSyncAdapter.list_departments(CONFIG, "blueking", "user_sync", locale="zh-Hans")

    assert result.success is True
    assert {item["id"] for item in result.payload["items"][0]["children"]} == {"1"}
    assert [call.kwargs["params"]["page"] for call in get.call_args_list] == [1, 2]


@pytest.mark.parametrize("count", ["not-a-count", True, 1.5])
def test_list_departments_rejects_non_numeric_count(count):
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response(page_payload(DEPARTMENTS[:1], count=count)),
    ) as get:
        result = BlueKingUserSyncAdapter.list_departments(CONFIG, "blueking", "user_sync")

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"
    assert result.errors[0].field == "count"
    assert get.call_count == 1


def test_sync_users_paginates_departments_and_users_for_bk_all():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(DEPARTMENTS[:2], count=4)),
            response(page_payload(DEPARTMENTS[2:], count=4)),
            response(page_payload(USERS[:2], count=3)),
            response(page_payload(USERS[2:], count=3)),
        ],
    ) as get:
        result = BlueKingUserSyncAdapter.sync_users(
            CONFIG,
            "blueking",
            "user_sync",
            source=_source(ALL_DEPARTMENT_ID),
        )

    assert result.success is True
    assert {item["id"] for item in result.payload["group_list"]} == {"1", "2", "3", "4"}
    parent_by_id = {item["id"]: item["parent_id"] for item in result.payload["group_list"]}
    assert parent_by_id["1"] == ALL_DEPARTMENT_ID
    assert parent_by_id["2"] == "1"
    assert parent_by_id["4"] == "2"
    assert ALL_DEPARTMENT_ID not in parent_by_id
    usernames = {user["username"] for user in result.payload["user_list"]}
    assert usernames == {"alice", "bob", "carol"}
    bob = next(user for user in result.payload["user_list"] if user["username"] == "bob")
    assert bob["display_name"] == "Bob"
    assert bob["email"] == "bob@example.com"
    assert bob["mobile"] == "13800000002"
    assert set(bob["department_ids"]) == {"4", "3"}
    urls = [call.args[0] for call in get.call_args_list]
    assert urls[:2] == ["https://bk.example.com/api/c/compapi/v2/usermanage/list_departments/"] * 2
    assert urls[2:] == ["https://bk.example.com/api/c/compapi/v2/usermanage/list_users/"] * 2
    user_params = [call.kwargs["params"] for call in get.call_args_list[2:]]
    assert all(params["page_size"] == PAGE_SIZE for params in user_params)
    assert all(params["bk_username"] == "admin" for params in user_params)
    assert all("bk_token" not in params for params in user_params)
    assert all("id" not in params for params in user_params)
    assert all("department_id" not in params for params in user_params)
    assert all(ALL_DEPARTMENT_ID not in str(params) for params in user_params)


def test_sync_users_bk_all_attaches_every_top_level_department():
    departments = [
        {"id": 1, "name": "Local", "parent": 0},
        {"id": 8, "name": "LDAP", "parent": None},
        {"id": 2, "name": "R&D", "parent": 1},
    ]
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(departments)),
            response(page_payload([])),
        ],
    ):
        result = BlueKingUserSyncAdapter.sync_users(
            CONFIG,
            "blueking",
            "user_sync",
            source=_source(ALL_DEPARTMENT_ID),
        )

    assert result.success is True
    parent_by_id = {item["id"]: item["parent_id"] for item in result.payload["group_list"]}
    assert parent_by_id == {"1": ALL_DEPARTMENT_ID, "8": ALL_DEPARTMENT_ID, "2": "1"}
    assert ALL_DEPARTMENT_ID not in parent_by_id


def test_sync_users_keeps_subtree_when_include_child_departments_is_true():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(DEPARTMENTS)),
            response(page_payload(USERS)),
        ],
    ):
        result = BlueKingUserSyncAdapter.sync_users(
            CONFIG,
            "blueking",
            "user_sync",
            source=_source("2", include_child=True),
        )

    assert result.success is True
    assert {item["id"] for item in result.payload["group_list"]} == {"2", "4"}
    parent_by_id = {item["id"]: item["parent_id"] for item in result.payload["group_list"]}
    assert parent_by_id["2"] == "1"
    assert parent_by_id["4"] == "2"
    assert ALL_DEPARTMENT_ID not in parent_by_id.values()
    assert {user["username"] for user in result.payload["user_list"]} == {"alice", "bob"}


def test_sync_users_keeps_only_selected_department_when_include_child_is_false():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=[
            response(page_payload(DEPARTMENTS)),
            response(page_payload(USERS)),
        ],
    ):
        result = BlueKingUserSyncAdapter.sync_users(
            CONFIG,
            "blueking",
            "user_sync",
            source=_source("2", include_child=False),
        )

    assert result.success is True
    assert [item["id"] for item in result.payload["group_list"]] == ["2"]
    assert [user["username"] for user in result.payload["user_list"]] == ["alice"]


@pytest.mark.parametrize("root_department_id", ["", "__all__", "**all**"])
def test_sync_users_rejects_legacy_virtual_roots_before_http(root_department_id):
    with patch("apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get") as get:
        result = BlueKingUserSyncAdapter.sync_users(
            CONFIG,
            "blueking",
            "user_sync",
            source=_source(root_department_id),
        )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "root_department_id"
    get.assert_not_called()
