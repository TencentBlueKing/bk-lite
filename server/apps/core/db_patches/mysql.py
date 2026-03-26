"""
MySQL 数据库兼容性补丁集合。

MySQL 主要限制：
1. 不支持在 JSON 列上直接创建索引（错误码 3152: JSON column cannot be used in key specification）
2. 需要通过 generated column + 函数索引来实现 JSON 路径索引

补丁分类：
1. 常规补丁 (patch): 在 CoreConfig.ready() 中应用
   - 注册 cw_cornerstone.migrate_patch 对 MySQL 的支持

Migration 补丁：
- 位于 migrate_patch/patches/mysql/ 目录
- 由 cw_cornerstone.migrate_patch 自动加载（需先注册 MySQL 驱动映射）
- 主要用于跳过不兼容的索引创建（GinIndex/BTreeIndex on JSONField）
"""

import json
import logging

logger = logging.getLogger(__name__)


def patch():
    """
    应用 MySQL 数据库的常规补丁。

    这些补丁在 CoreConfig.ready() 中调用，
    用于修复 ORM 层面的兼容性问题。
    """
    _patch_migrate_patch_mysql_support()
    _patch_jsonfield_contains_lookup()
    logger.info("MySQL patches applied (migrate_patch MySQL support + JSON contains lookup)")


def _patch_migrate_patch_mysql_support():
    """
    为 cw_cornerstone.migrate_patch 添加 MySQL 数据库支持。

    问题：
    cw_cornerstone.migrate_patch.management.get_db_driver() 函数
    没有处理 cw_cornerstone.db.mysql.backend 引擎。

    修复策略：
    Monkey patch get_db_driver 函数，添加 MySQL 引擎的识别。
    """
    try:
        from cw_cornerstone.migrate_patch import management

        original_get_db_driver = management.get_db_driver

        def patched_get_db_driver(using: str) -> str:
            """扩展的 get_db_driver，增加 MySQL 支持"""
            from django.db import connections

            try:
                db_backend = connections[using].settings_dict["ENGINE"]
            except KeyError:
                return ""

            # 先检查 MySQL
            if db_backend == "cw_cornerstone.db.mysql.backend":
                return "mysql"

            # 其他引擎走原逻辑
            return original_get_db_driver(using)

        management.get_db_driver = patched_get_db_driver
        logger.debug("cw_cornerstone.migrate_patch.get_db_driver patched for MySQL support")

    except ImportError:
        logger.warning("cw_cornerstone.migrate_patch not installed, skipping MySQL migrate patch support")


def _patch_jsonfield_contains_lookup():
    """
    修复 MySQL 数据库 JSONField 的 __contains 查询问题。

    问题：
    MySQL 的 JSON 类型支持与 PostgreSQL 不同。
    PostgreSQL 的 @> 操作符不可用，需要使用 MySQL 的 JSON_CONTAINS 函数。

    修复策略：
    注册自定义的 Lookup，将 JSON 包含查询转换为 JSON_CONTAINS 函数调用。
    """
    from django.db.models import Lookup
    from django.db.models.fields.json import JSONField

    class MySQLJSONContains(Lookup):
        """MySQL 数据库的 JSON 包含查询 Lookup"""

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
    JSONField.register_lookup(MySQLJSONContains)
    logger.debug("JSONField.contains lookup patched for MySQL")
