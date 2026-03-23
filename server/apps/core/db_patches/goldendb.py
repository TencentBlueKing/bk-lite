"""
GoldenDB 数据库（中兴通讯分布式数据库）兼容性补丁集合。

GoldenDB 基于 MySQL 协议，主要限制：
1. 不支持在 JSON 列上直接创建索引（错误码 3152）
2. 需要通过 generated column 来实现 JSON 路径索引

补丁分类：
1. 常规补丁 (patch): 在 CoreConfig.ready() 中应用
   - 包括 JSONField 兼容性补丁（如需要）

Migration 补丁：
- 位于 migrate_patch/patches/goldendb/ 目录
- 由 cw_cornerstone.migrate_patch 自动加载
- 主要用于跳过不兼容的索引创建（GinIndex/BTreeIndex on JSONField）
"""

import json
import logging

logger = logging.getLogger(__name__)


def patch():
    """
    应用 GoldenDB 数据库的常规补丁。

    这些补丁在 CoreConfig.ready() 中调用，
    用于修复 ORM 层面的兼容性问题。
    """
    # GoldenDB 基于 MySQL 协议，大部分情况下兼容性较好
    # 目前主要问题是 JSON 列索引不支持，已通过 Migration 补丁处理
    _patch_jsonfield_contains_lookup()
    logger.info("GoldenDB ORM patches applied (JSON contains lookup)")


def _patch_jsonfield_contains_lookup():
    """
    修复 GoldenDB 数据库 JSONField 的 __contains 查询问题。

    问题：
    GoldenDB 使用 MySQL 协议，JSON 类型支持有限。
    PostgreSQL 的 @> 操作符不可用，需要使用 MySQL 的 JSON_CONTAINS 函数。

    修复策略：
    注册自定义的 Lookup，将 JSON 包含查询转换为 JSON_CONTAINS 函数调用。
    """
    from django.db.models import Lookup
    from django.db.models.fields.json import JSONField

    class GoldenDBJSONContains(Lookup):
        """GoldenDB 数据库的 JSON 包含查询 Lookup"""

        lookup_name = "contains"

        def as_sql(self, compiler, connection):
            lhs, lhs_params = self.process_lhs(compiler, connection)
            value = self.rhs

            # 如果值已经是 JSON 字符串，尝试解析
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass

            # 使用 MySQL 的 JSON_CONTAINS 函数
            # JSON_CONTAINS(target, candidate[, path])
            json_str = json.dumps(value, ensure_ascii=False)
            return f"JSON_CONTAINS({lhs}, %s)", lhs_params + [json_str]

    # 注册新的 lookup（覆盖默认的）
    JSONField.register_lookup(GoldenDBJSONContains)
    logger.debug("JSONField.contains lookup patched for GoldenDB")
