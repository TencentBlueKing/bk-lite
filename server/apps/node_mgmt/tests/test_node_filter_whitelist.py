# -*- coding: utf-8 -*-
"""
Issue #3609: 节点搜索接口 filters 参数白名单校验

验证 NodeFilterHandler.build_standard_filters 对 field_name 和 lookup_expr
实施白名单校验，防止 ORM 注入攻击。

关键判定准则：若将修复代码 revert（删除白名单校验），以下测试必须失败。
"""
import pytest
from django.db.models import Q

from apps.node_mgmt.views.node import NodeFilterHandler


class TestFieldNameWhitelist:
    """field_name 白名单校验"""

    def test_allowed_field_name_is_included_in_query(self):
        """白名单内字段应正常构建 Q 条件"""
        params = {
            "name": [{"lookup_expr": "icontains", "value": "web"}],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        # 白名单字段应产生非空 Q 对象
        assert result != Q()

    def test_non_whitelisted_field_name_is_silently_skipped(self):
        """非白名单字段必须被静默跳过，不得出现在最终 Q 对象中"""
        params = {
            "collectorconfiguration__env_config": [
                {"lookup_expr": "icontains", "value": "password"}
            ],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        # 非白名单字段被跳过后，Q 对象应为空
        assert result == Q(), (
            "非白名单字段 collectorconfiguration__env_config 未被正确过滤，"
            "ORM 注入防护失效"
        )

    def test_cross_relation_traversal_is_blocked(self):
        """跨关联查询（多层 __）必须被阻断"""
        malicious_params = {
            "collectorconfiguration__env_config__icontains": [
                {"lookup_expr": "exact", "value": "secret"}
            ],
            "nodeorganization__organization": [
                {"lookup_expr": "exact", "value": "1"}
            ],
            "__class__.__mro__": [
                {"lookup_expr": "exact", "value": "anything"}
            ],
        }
        result = NodeFilterHandler.build_standard_filters(malicious_params)
        assert result == Q(), "跨关联查询注入未被阻断"

    def test_only_whitelisted_fields_pass_through_mixed_params(self):
        """混合参数中只有白名单字段应生效，非白名单字段被跳过"""
        params = {
            "name": [{"lookup_expr": "icontains", "value": "server"}],  # 允许
            "collectorconfiguration__env_config": [  # 不允许
                {"lookup_expr": "icontains", "value": "password"}
            ],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        # 应包含 name 字段的过滤
        expected = Q(name__icontains="server")
        assert result == expected, (
            f"期望只有 name 字段的 Q 条件，实际得到: {result}"
        )

    def test_allowed_filter_fields_constant_exists_and_is_non_empty(self):
        """ALLOWED_FILTER_FIELDS 常量必须存在且非空"""
        assert hasattr(NodeFilterHandler, "ALLOWED_FILTER_FIELDS")
        assert len(NodeFilterHandler.ALLOWED_FILTER_FIELDS) > 0

    def test_node_model_direct_fields_are_in_whitelist(self):
        """Node 模型核心直接字段必须在白名单内"""
        required_fields = {"name", "ip", "operating_system", "install_method", "node_type"}
        missing = required_fields - NodeFilterHandler.ALLOWED_FILTER_FIELDS
        assert not missing, f"核心字段未加入白名单: {missing}"


class TestLookupExprWhitelist:
    """lookup_expr 白名单校验"""

    def test_valid_lookup_expr_is_used(self):
        """白名单内 lookup_expr 应被正常使用"""
        params = {
            "name": [{"lookup_expr": "icontains", "value": "web"}],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        assert result == Q(name__icontains="web")

    def test_invalid_lookup_expr_is_downgraded_to_exact(self):
        """非白名单 lookup_expr 应被降级为 exact，不报错也不传递原值"""
        params = {
            "name": [{"lookup_expr": "regex", "value": ".*admin.*"}],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        # regex 不在白名单，应降级为 exact
        assert result == Q(name__exact=".*admin.*"), (
            "非白名单 lookup_expr 'regex' 未被正确降级为 'exact'"
        )

    def test_raw_sql_injection_in_lookup_expr_is_blocked(self):
        """SQL 注入式 lookup_expr 必须被阻断"""
        params = {
            "name": [{"lookup_expr": "exact OR 1=1--", "value": "x"}],
        }
        # 不应抛出异常，返回降级后的安全 Q 对象
        result = NodeFilterHandler.build_standard_filters(params)
        assert result == Q(name__exact="x")

    def test_allowed_lookup_exprs_constant_exists_and_is_non_empty(self):
        """ALLOWED_LOOKUP_EXPRS 常量必须存在且非空"""
        assert hasattr(NodeFilterHandler, "ALLOWED_LOOKUP_EXPRS")
        assert len(NodeFilterHandler.ALLOWED_LOOKUP_EXPRS) > 0

    def test_common_lookup_exprs_are_in_whitelist(self):
        """常用 lookup_expr 必须在白名单内"""
        required_exprs = {"exact", "icontains", "in", "isnull", "gte", "lte"}
        missing = required_exprs - NodeFilterHandler.ALLOWED_LOOKUP_EXPRS
        assert not missing, f"常用 lookup_expr 未加入白名单: {missing}"


class TestBoolLookupCompatibility:
    """bool lookup_expr 向后兼容性（已有功能，不应被破坏）"""

    def test_bool_lookup_expr_is_still_normalized(self):
        """'bool' lookup_expr 应仍被正确归一化为 exact + 布尔值"""
        params = {
            "status": [{"lookup_expr": "bool", "value": "true"}],
        }
        result = NodeFilterHandler.build_standard_filters(params)
        # bool 应归一化为 exact，值为 True
        assert result == Q(status__exact=True)

    def test_empty_params_returns_empty_q(self):
        """空参数应返回空 Q 对象"""
        assert NodeFilterHandler.build_standard_filters({}) == Q()
        assert NodeFilterHandler.build_standard_filters(None) == Q()
