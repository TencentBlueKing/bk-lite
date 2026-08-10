from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.system_mgmt.providers.adapters.feishu import FeishuUserSyncAdapter


class _FeishuResponse:
    status_code = 200
    headers = {"X-Tt-Logid": "req-1"}

    def __init__(self, items=None, *, data=None, request_id="req-1"):
        self.items = items or []
        self.data = data
        self.headers = {"X-Tt-Logid": request_id}

    def json(self):
        return {"code": 0, "data": self.data or {"items": self.items, "has_more": False}}


def test_list_departments_builds_visible_forest_from_paginated_scopes():
    requested_urls = []
    requested_params = []

    def get_contact_data(url, **kwargs):
        requested_urls.append(url)
        requested_params.append(kwargs.get("params") or {})
        if url.endswith("/scopes"):
            if kwargs["params"].get("page_token") == "scope-page-2":
                return _FeishuResponse(
                    data={"department_ids": ["dept-b", "dept-a"], "has_more": False},
                    request_id="scope-2",
                )
            return _FeishuResponse(
                data={"department_ids": ["dept-a", "dept-a1"], "has_more": True, "page_token": "scope-page-2"},
                request_id="scope-1",
            )
        if url.endswith("/departments/batch"):
            return _FeishuResponse(
                data={"items": [
                    {"department_id": "dept-a", "name": "研发部", "parent_department_id": "hidden-parent"},
                    {"department_id": "dept-a1", "name": "后端组", "parent_department_id": "dept-a"},
                    {"department_id": "dept-b", "name": "财务部", "parent_department_id": "0"},
                ], "has_more": False},
                request_id="batch-details",
            )
        if url.endswith("/departments/dept-a/children"):
            return _FeishuResponse(
                [
                    {"department_id": "dept-a1", "name": "后端组", "parent_department_id": "dept-a"},
                    {"department_id": "dept-a2", "name": "平台组", "parent_department_id": "dept-a1"},
                ],
                request_id="children-a",
            )
        if url.endswith("/departments/dept-a1/children") or url.endswith("/departments/dept-b/children"):
            return _FeishuResponse([], request_id="children-last")
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.list_departments(
            {},
            "feishu",
            "user_sync",
            business_config={"department_id_type": "department_id"},
        )

    assert result.success is True
    assert result.payload["items"] == [
            {
                "id": "dept-a",
                "name": "研发部",
                "parent_id": None,
                "children": [
                    {
                        "id": "dept-a1",
                        "name": "后端组",
                        "parent_id": "dept-a",
                        "children": [
                            {"id": "dept-a2", "name": "平台组", "parent_id": "dept-a1", "children": [], "selectable": True}
                        ],
                        "selectable": True,
                    }
                ],
                "selectable": True,
            },
            {"id": "dept-b", "name": "财务部", "parent_id": None, "children": [], "selectable": True},
        ]
    assert result.payload["external_request_id"] == "children-last"
    assert result.payload["server_timing"].startswith("feishu-token;dur=")
    assert all("/departments/0/children" not in url for url in requested_urls)
    assert sum(url.endswith("/departments/batch") for url in requested_urls) == 1
    assert all("/departments/dept-a" not in url or url.endswith("/children") for url in requested_urls)
    assert all(params["department_id_type"] == "department_id" for params in requested_params)
    batch_request = next(params for url, params in zip(requested_urls, requested_params) if url.endswith("/departments/batch"))
    assert batch_request["department_ids"] == ["dept-a", "dept-a1", "dept-b"]
    children_requests = [
        (url, params)
        for url, params in zip(requested_urls, requested_params)
        if url.endswith("/children")
    ]
    assert [url.rsplit("/", 2)[-2] for url, _params in children_requests] == ["dept-a", "dept-a1", "dept-b"]
    assert all(params["fetch_child"] == "true" for _url, params in children_requests)


def test_list_departments_returns_empty_list_for_empty_scopes():
    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=_FeishuResponse(data={"department_ids": [], "has_more": False}, request_id="scope-empty"),
    ) as get:
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.success is True
    assert result.payload["items"] == []
    assert result.payload["external_request_id"] == "scope-empty"
    assert result.payload["server_timing"].startswith("feishu-token;dur=")
    assert get.call_args.args[0].endswith("/scopes")


def test_list_departments_exposes_stage_timings_for_department_options():
    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=_FeishuResponse(data={"department_ids": [], "has_more": False}),
    ), patch(
        "apps.system_mgmt.providers.adapters.feishu.time.perf_counter",
        side_effect=[
            100.0,
            100.1,
            100.2,
            100.3,
            100.4,
            100.5,
            100.8,
            100.8,
            100.8,
            100.8,
            100.8,
            100.9,
        ],
    ):
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.payload["server_timing"] == (
        "feishu-token;dur=100, feishu-scopes;dur=500, feishu-root-details;dur=0, "
        "feishu-children;dur=0, feishu-total;dur=900"
    )


def test_list_departments_fetches_authorized_root_children_concurrently():
    children_barrier = Barrier(3)

    def get_contact_data(url, **kwargs):
        if url.endswith("/scopes"):
            return _FeishuResponse(
                data={"department_ids": ["dept-a", "dept-b", "dept-c"], "has_more": False}
            )
        if url.endswith("/departments/batch"):
            return _FeishuResponse(
                data={
                    "items": [
                        {"department_id": "dept-a", "name": "A", "parent_department_id": "0"},
                        {"department_id": "dept-b", "name": "B", "parent_department_id": "0"},
                        {"department_id": "dept-c", "name": "C", "parent_department_id": "0"},
                    ],
                    "has_more": False,
                }
            )
        if url.endswith("/children"):
            children_barrier.wait(timeout=0.5)
            return _FeishuResponse([])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.success is True
    assert [item["id"] for item in result.payload["items"]] == ["dept-a", "dept-b", "dept-c"]


def test_list_departments_ignores_synthetic_scope_roots():
    requested_urls = []

    def get_contact_data(url, **kwargs):
        requested_urls.append(url)
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["", "0", "__all__", "**all**", "dept-a"], "has_more": False})
        if url.endswith("/departments/batch"):
            return _FeishuResponse(data={"items": [{"department_id": "dept-a", "name": "研发部", "parent_department_id": "0"}], "has_more": False})
        if url.endswith("/departments/dept-a/children"):
            return _FeishuResponse([])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.success is True
    assert [item["id"] for item in result.payload["items"]] == ["dept-a"]
    assert all("/departments/0" not in url for url in requested_urls)
    assert all("/departments/__all__" not in url for url in requested_urls)
    assert all("/departments/**all**" not in url for url in requested_urls)


def test_list_departments_breaks_parent_cycles_without_losing_nodes():
    def get_contact_data(url, **kwargs):
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["self", "cycle-a", "cycle-b"], "has_more": False})
        details = {
            "self": {"department_id": "self", "name": "自环", "parent_department_id": "self"},
            "cycle-a": {"department_id": "cycle-a", "name": "循环甲", "parent_department_id": "cycle-b"},
            "cycle-b": {"department_id": "cycle-b", "name": "循环乙", "parent_department_id": "cycle-a"},
        }
        if url.endswith("/departments/batch"):
            return _FeishuResponse(data={"items": list(details.values()), "has_more": False})
        for department_id, detail in details.items():
            if url.endswith(f"/departments/{department_id}/children"):
                return _FeishuResponse([])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.success is True
    assert result.payload["items"] == [
        {"id": "self", "name": "自环", "parent_id": None, "children": [], "selectable": True},
        {
            "id": "cycle-a",
            "name": "循环甲",
            "parent_id": None,
            "children": [
                {"id": "cycle-b", "name": "循环乙", "parent_id": "cycle-a", "children": [], "selectable": True}
            ],
            "selectable": True,
        },
    ]


def test_list_departments_breaks_only_cycle_entry_edge_for_chain_entering_cycle():
    def get_contact_data(url, **kwargs):
        if url.endswith("/scopes"):
            return _FeishuResponse(data={"department_ids": ["chain-x", "cycle-a", "cycle-b"], "has_more": False})
        details = {
            "chain-x": {"department_id": "chain-x", "name": "入链节点", "parent_department_id": "cycle-a"},
            "cycle-a": {"department_id": "cycle-a", "name": "循环甲", "parent_department_id": "cycle-b"},
            "cycle-b": {"department_id": "cycle-b", "name": "循环乙", "parent_department_id": "cycle-a"},
        }
        if url.endswith("/departments/batch"):
            return _FeishuResponse(data={"items": list(details.values()), "has_more": False})
        for department_id, detail in details.items():
            if url.endswith(f"/departments/{department_id}/children"):
                return _FeishuResponse([])
        raise AssertionError(url)

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=get_contact_data):
        result = FeishuUserSyncAdapter.list_departments({}, "feishu", "user_sync")

    assert result.success is True
    assert result.payload["items"] == [
        {
            "id": "cycle-a",
            "name": "循环甲",
            "parent_id": None,
            "children": [
                {"id": "chain-x", "name": "入链节点", "parent_id": "cycle-a", "children": [], "selectable": True},
                {"id": "cycle-b", "name": "循环乙", "parent_id": "cycle-a", "children": [], "selectable": True},
            ],
            "selectable": True,
        }
    ]


@pytest.mark.parametrize("root_department_id", ["", "0", "__all__", "**all**"])
def test_sync_users_rejects_invalid_inherited_root_before_contact_request(root_department_id):
    source = SimpleNamespace(name="飞书测试", business_config={"root_department_id": root_department_id})

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
    ) as fetch_token, patch("apps.system_mgmt.providers.adapters.feishu.requests.get") as get:
        result = FeishuUserSyncAdapter.sync_users({}, "feishu", "user_sync", source=source)

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "root_department_id"
    fetch_token.assert_not_called()
    get.assert_not_called()


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
