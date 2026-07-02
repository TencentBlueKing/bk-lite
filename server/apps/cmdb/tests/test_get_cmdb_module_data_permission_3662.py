"""测试 get_cmdb_module_data PERMISSION_INSTANCES 分支的权限过滤。

Issue #3662: 原先 permission_map={} 硬编码绕过权限，本测试验证修复后：
1. user_info 缺失时返回空列表（安全兜底）
2. _build_nats_permission_map 返回 None 时返回空列表
3. 有效 permission_map 时调用 InstanceManage.instance_list 并使用该 map

revert 修复后测试必须失败（验证覆盖修复点本身）。
"""

import pytest
from unittest.mock import MagicMock, patch

from apps.cmdb.nats.nats import get_cmdb_module_data
from apps.cmdb.constants.constants import PERMISSION_INSTANCES


@pytest.mark.unit
class TestGetCmdbModuleDataPermission:
    """PERMISSION_INSTANCES 分支权限过滤测试。"""

    def test_no_user_info_returns_empty(self):
        """user_info 缺失时返回空列表（安全兜底，不泄露任何实例）。"""
        result = get_cmdb_module_data(
            module=PERMISSION_INSTANCES,
            child_module="host",
            page=1,
            page_size=10,
            group_id=1,
            user_info=None,
        )
        assert result == {"count": 0, "items": []}, (
            "缺少 user_info 时应返回空列表，不得泄露实例名称"
        )

    def test_permission_map_none_returns_empty(self):
        """_build_nats_permission_map 返回 None（用户无权或信息不完整）时返回空列表。"""
        with patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=None):
            result = get_cmdb_module_data(
                module=PERMISSION_INSTANCES,
                child_module="host",
                page=1,
                page_size=10,
                group_id=1,
                user_info={"user": "alice", "team": 1},
            )
        assert result == {"count": 0, "items": []}, (
            "_build_nats_permission_map 返回 None 时应返回空列表"
        )

    def test_valid_user_info_uses_real_permission_map(self):
        """有效 user_info 时将真实 permission_map 传入 InstanceManage.instance_list。"""
        fake_permission_map = {1: {"inst_names": ["host-001"], "permission_instances_map": {}}}
        fake_instances = [{"inst_name": "host-001"}]

        with patch("apps.cmdb.nats.nats._build_nats_permission_map", return_value=fake_permission_map) as mock_build, \
             patch("apps.cmdb.nats.nats.InstanceManage.instance_list", return_value=(fake_instances, 1)) as mock_list:

            result = get_cmdb_module_data(
                module=PERMISSION_INSTANCES,
                child_module="host",
                page=1,
                page_size=10,
                group_id=1,
                user_info={"user": "alice", "team": 1, "domain": "domain.com"},
            )

        # 验证 _build_nats_permission_map 用了正确参数
        mock_build.assert_called_once_with(
            {"user": "alice", "team": 1, "domain": "domain.com"},
            model_id="host",
        )
        # 验证 instance_list 收到的 permission_map 是真实的，而非空字典
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["permission_map"] is fake_permission_map, (
            "instance_list 必须使用从 user_info 构建的真实 permission_map，不得传入 {}"
        )
        assert call_kwargs["permission_map"] != {}, (
            "permission_map 不得为空字典（空字典会绕过权限过滤）"
        )
        assert result == {"count": 1, "items": [{"name": "host-001", "id": "host-001"}]}

    def test_empty_permission_map_dict_would_bypass_filter(self):
        """回归测试：若 permission_map={} 传入 instance_list，确认可被检测。

        此测试验证修复点：revert 修复（改回 permission_map={}）后，
        test_valid_user_info_uses_real_permission_map 中的断言会失败。
        """
        # 使用空字典验证 _build_format_permission_dict 的语义
        from apps.cmdb.services.instance import InstanceManage
        # 空 permission_map 产生空 format_permission_dict → 无权限条件 → 越权
        result = InstanceManage._build_format_permission_dict({})
        assert result == {}, "空 permission_map 产生空过滤条件，验证旁路场景"

        # 非空 permission_map 产生有效过滤条件
        permission_map = {1: {"inst_names": ["host-001"], "permission_instances_map": {}}}
        result = InstanceManage._build_format_permission_dict(permission_map)
        assert 1 in result, "非空 permission_map 必须产生有效权限过滤条件"
