"""补丁管理数据权限 NATS 契约测试。"""

import pytest

from apps.patch_mgmt.models import PatchTarget
from apps.patch_mgmt.nats_api import (
    get_patch_mgmt_module_data,
    get_patch_mgmt_module_list,
)
from apps.rpc.patch_mgmt import PatchMgmt


pytestmark = pytest.mark.django_db


def test_module_list_only_exposes_target_management():
    assert get_patch_mgmt_module_list() == [
        {"name": "patch_target", "display_name": "目标管理"}
    ]


def test_module_data_returns_target_instances_and_supports_pagination():
    first = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", team=[1])
    second = PatchTarget.objects.create(name="host-b", ip="10.0.0.2", team=[1])

    result = get_patch_mgmt_module_data(
        "patch_target", "", 2, 1, 1, team=[1]
    )

    assert result == {
        "count": 2,
        "items": [{"id": second.id, "name": "host-b"}],
    }
    assert first.id < second.id


@pytest.mark.parametrize(
    "module",
    [
        "patch",
        "patch_source",
        "patch_baseline",
        "patch_governance",
        "patch_risk",
        "patch_dashboard",
    ],
)
def test_retired_data_permission_modules_are_not_queryable(module):
    result = get_patch_mgmt_module_data(module, "", 1, 10, 1, team=[1])

    assert result["result"] is False


def test_unknown_module_returns_business_error():
    result = get_patch_mgmt_module_data("unknown", "", 1, 10, 1, team=[1])

    assert result["result"] is False


def test_module_data_rejects_group_outside_authorized_teams():
    result = get_patch_mgmt_module_data(
        "patch_target", "", 1, 10, 2, team=[1]
    )

    assert result["result"] is False


def test_rpc_client_forwards_module_data(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    client = PatchMgmt(is_local_client=False)
    calls = []
    client.client.run = lambda method, **kwargs: calls.append((method, kwargs)) or {
        "count": 0,
        "items": [],
    }

    result = client.get_module_data(module="patch_target", page=1)

    assert result == {"count": 0, "items": []}
    assert calls == [("get_patch_mgmt_module_data", {"module": "patch_target", "page": 1})]
