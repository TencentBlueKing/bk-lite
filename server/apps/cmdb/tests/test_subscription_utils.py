"""cmdb.utils.subscription_utils 测试。

规格：
- truncate_value：None→"(空)"，超长截断为 max_length（含 "..."）；
- get_inst_display_name：inst_name→ip_addr→fallback_id→"(未知)" 优先级；
- check_subscription_manage_permission：空/非法 team→False；
  include_descendants=False 仅本组织；=True 含子组织（依赖组织树，真实 DB）。
"""

import pytest

from apps.cmdb.utils.subscription_utils import (
    check_subscription_manage_permission,
    get_inst_display_name,
    truncate_value,
)


class TestTruncateValue:
    pytestmark = pytest.mark.unit

    def test_none_为空(self):
        assert truncate_value(None) == "(空)"

    def test_短值原样(self):
        assert truncate_value("abc") == "abc"

    def test_超长截断含省略号(self):
        out = truncate_value("x" * 100, max_length=10)
        assert len(out) == 10
        assert out.endswith("...")

    def test_非字符串转字符串(self):
        assert truncate_value(12345) == "12345"


class TestDisplayName:
    pytestmark = pytest.mark.unit

    def test_优先_inst_name(self):
        assert get_inst_display_name({"inst_name": "web01", "ip_addr": "1.1.1.1"}) == "web01"

    def test_次选_ip_addr(self):
        assert get_inst_display_name({"ip_addr": "1.1.1.1"}) == "1.1.1.1"

    def test_回退_id(self):
        assert get_inst_display_name(None, fallback_id=42) == "42"
        assert get_inst_display_name({}, fallback_id=7) == "7"

    def test_未知(self):
        assert get_inst_display_name(None) == "(未知)"


class TestManagePermissionPure:
    pytestmark = pytest.mark.unit

    @pytest.mark.parametrize("team", [None, "", "abc"])
    def test_空或非法team拒绝(self, team):
        assert check_subscription_manage_permission(1, team) is False

    def test_仅本组织匹配(self):
        assert check_subscription_manage_permission(5, 5, include_descendants=False) is True
        assert check_subscription_manage_permission(5, 6, include_descendants=False) is False


@pytest.mark.django_db
@pytest.mark.integration
class TestManagePermissionWithTree:
    def test_含子组织权限(self):
        from apps.system_mgmt.models import Group

        root = Group.objects.create(name="r", parent_id=0)
        child = Group.objects.create(name="c", parent_id=root.id)
        # 规则属于子组织，当前团队是父组织 + 含子孙 -> 有权限
        assert check_subscription_manage_permission(child.id, root.id, include_descendants=True) is True
        # 不含子孙 -> 无权限
        assert check_subscription_manage_permission(child.id, root.id, include_descendants=False) is False
