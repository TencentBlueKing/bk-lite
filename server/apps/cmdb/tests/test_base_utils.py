"""cmdb.utils.base 纯逻辑测试。

规格：
- format_group_params/format_groups_params：组织参数格式化(后者按 set 去重)；
- get_organization_and_children_ids：从 subGroups 树收集目标及其所有子孙 id；
- get_current_team_from_request：Cookie 取 current_team，缺失按 required 抛错/返回 0，非法抛错。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.utils.base import (
    format_group_params,
    format_groups_params,
    get_current_team_from_request,
    get_organization_and_children_ids,
)
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


def _req(cookies):
    return SimpleNamespace(COOKIES=cookies)


class TestFormatGroupParams:
    def test_单组织(self):
        assert format_group_params("5") == [{"id": 5}]

    def test_多组织去重(self):
        out = format_groups_params([1, 2, 2, 3])
        ids = sorted(d["id"] for d in out)
        assert ids == [1, 2, 3]


class TestOrgChildrenIds:
    TREE = [
        {"id": 1, "subGroups": [
            {"id": 2, "subGroups": [{"id": 4, "subGroups": []}]},
            {"id": 3, "subGroups": []},
        ]},
        {"id": 9, "subGroups": []},
    ]

    def test_根含全部子孙(self):
        assert sorted(get_organization_and_children_ids(self.TREE, 1)) == [1, 2, 3, 4]

    def test_中间节点含其子树(self):
        assert sorted(get_organization_and_children_ids(self.TREE, 2)) == [2, 4]

    def test_叶子只含自身(self):
        assert get_organization_and_children_ids(self.TREE, 4) == [4]

    def test_不存在返回空(self):
        assert get_organization_and_children_ids(self.TREE, 999) == []


class TestCurrentTeamFromRequest:
    def test_正常取值(self):
        assert get_current_team_from_request(_req({"current_team": "7"})) == 7

    def test_缺失且required抛错(self):
        with pytest.raises(BaseAppException):
            get_current_team_from_request(_req({}))

    def test_缺失且非required返回0(self):
        assert get_current_team_from_request(_req({}), required=False) == 0

    def test_非法值抛错(self):
        with pytest.raises(BaseAppException):
            get_current_team_from_request(_req({"current_team": "abc"}))
