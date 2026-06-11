"""issue #3035 回归测试：批量组织角色详情接口必须做对象级权限收口。

revert 准则：移除 batch_get_group_detail_with_roles 中的 authorized_group_ids 过滤后，
test_..._skips_unauthorized_groups 必失败（未授权组织会被泄露）。
"""

import json
from types import SimpleNamespace

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.viewset.group_viewset import GroupViewSet


def _request(user, data):
    return SimpleNamespace(user=user, data=data)


@pytest.mark.django_db
def test_batch_group_detail_skips_unauthorized_groups():
    authorized = Group.objects.create(name="Authorized Org", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="Other Org", parent_id=0, is_virtual=False)

    # 非超管用户：具备 user_group-View 模块权限，但只在 authorized 组织内
    user = SimpleNamespace(
        is_superuser=False,
        permission={"system-manager": {"user_group-View"}},
        group_list=[{"id": authorized.id}],
        locale="en",
    )
    request = _request(user, {"group_ids": [authorized.id, other.id]})

    response = GroupViewSet().batch_get_group_detail_with_roles(request)
    payload = json.loads(response.content)

    assert payload["result"] is True
    returned_ids = {item["group_id"] for item in payload["data"]}
    assert authorized.id in returned_ids
    assert other.id not in returned_ids  # 未授权组织角色配置不得泄露


@pytest.mark.django_db
def test_batch_group_detail_superuser_sees_all():
    g1 = Group.objects.create(name="Org1", parent_id=0, is_virtual=False)
    g2 = Group.objects.create(name="Org2", parent_id=0, is_virtual=False)

    user = SimpleNamespace(is_superuser=True, permission={}, group_list=[], locale="en")
    request = _request(user, {"group_ids": [g1.id, g2.id]})

    response = GroupViewSet().batch_get_group_detail_with_roles(request)
    payload = json.loads(response.content)

    returned_ids = {item["group_id"] for item in payload["data"]}
    assert returned_ids == {g1.id, g2.id}
