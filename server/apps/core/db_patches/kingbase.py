"""
KingbaseES（人大金仓）MySQL 兼容模式补丁集合。

背景
====
客户的 Kingbase 实例运行在 **MySQL 兼容模式**，但 BK-Lite 通过 ``DB_ENGINE=postgresql``
（psycopg2 + Django postgresql 后端）连接它 —— 因为 Kingbase 始终走 PostgreSQL 线协议，
用 mysql 引擎（pymysql，MySQL 线协议）根本连不上。

问题出在 SQL 方言：Django 的 postgresql 后端发出的 SQL 用 ``||`` 做**字符串拼接**，
而在 MySQL 兼容模式下 ``||`` 被解释为**逻辑 OR**，返回布尔值，导致：

1. **迁移期**（migrate 阻断点）：
   ``django/db/backends/postgresql/introspection.py`` 的 ``get_constraints`` 用
   ``fkc.relname || '.' || fka.attname`` 拼外键的“表.列”，MySQL 模式下返回 ``bool``，
   随后 ``used_cols.split('.')`` 抛 ``AttributeError: 'bool' object has no attribute 'split'``。
   任何触发约束反查的迁移（如 ``AlterUniqueTogether``）都会中招。

2. **运行期**：
   ``django/db/backends/postgresql/base.py`` 的 ``DatabaseWrapper.pattern_ops``
   （``__contains`` / ``__startswith`` / ``__endswith`` 等基于列的模式匹配）生成的
   ``'%' || col || '%'`` 在 MySQL 模式下语义错误。

修复策略
========
把这些 ``||`` 拼接改写成 ``concat(...)``。``concat()`` 在原生 PostgreSQL 和
Kingbase MySQL 模式下都返回字符串，是**模式中立**的，因此补丁本身在两种库上都安全。
补丁仅在环境变量 ``PG_COMPAT=kingbase`` 时启用，正常 PostgreSQL 部署完全不受影响。

启用方式
========
保持 ``DB_ENGINE=postgresql``，额外设置环境变量 ``PG_COMPAT=kingbase``。
在 ``config/components/database.py`` 的 settings 加载阶段调用 ``apply_early_patches()``
（与达梦 ``apply_early_patches`` 同一注入时机，确保在 migrate / introspection 之前生效）。

重要提醒
========
本补丁只是让系统在 Kingbase MySQL 模式下“先跑起来”的兜底，**并非完整适配**。
MySQL 模式与原生 PG 的方言差异远不止 ``||``（如 ``pattern_esc`` 里的 ``E'...'`` 转义串、
JSONB、数组、GIN 索引、``ON CONFLICT``、正则 ``~`` 等），运行期仍可能遇到其他不兼容点，
必须在真实 Kingbase MySQL 环境回归验证，按需在本模块继续补充。
"""

import logging

logger = logging.getLogger(__name__)

# 标记补丁是否已应用，避免重复
_patches_applied = False


def apply_early_patches():
    """
    应用 KingbaseES MySQL 兼容模式补丁。

    在 ``config/components/database.py`` 中、当 ``DB_ENGINE=postgresql`` 且
    ``PG_COMPAT=kingbase`` 时调用。幂等：重复调用只生效一次。
    """
    global _patches_applied
    if _patches_applied:
        return
    _patches_applied = True

    # 1. 迁移期：修复 introspection.get_constraints 的外键拼接（migrate 阻断点）
    _patch_introspection_pipe_concat()

    # 2. 运行期：修复 pattern_ops 的模式匹配拼接（__contains/__startswith/__endswith 等）
    _patch_pattern_ops_pipe_concat()

    # 3. 仅 psycopg(v3)：容忍 Kingbase MySQL 模式 timestamptz 不带时区偏移（migrate 收尾阻断点）
    _patch_psycopg3_timestamptz_missing_tz()

    logger.info("KingbaseES MySQL-mode patches applied (introspection + pattern_ops + psycopg3 timestamptz)")


def _patch_introspection_pipe_concat():
    """
    迁移期修复：把 ``get_constraints`` 中外键子查询的 ``||`` 字符串拼接改写为 ``concat()``。

    该方法整体复制自 Django 4.2 的
    ``django.db.backends.postgresql.introspection.DatabaseIntrospection.get_constraints``，
    **仅改动一处**：第 202 行
        ``fkc.relname || '.' || fka.attname``  ->  ``concat(fkc.relname, '.', fka.attname)``
    其余逻辑保持与原方法一致。

    注意：本方法是对 Django 源码的逐字镜像，**升级 Django 版本时需重新同步**。
    """
    from django.db.backends.postgresql.introspection import DatabaseIntrospection

    def get_constraints(self, cursor, table_name):
        """
        Retrieve any constraints or keys (unique, pk, fk, check, index) across
        one or more columns. Also retrieve the definition of expression-based
        indexes.

        BK-Lite 补丁版：外键拼接 `||` 改为 `concat()`，兼容 Kingbase MySQL 模式。
        """
        from django.db.models import Index

        constraints = {}
        # Loop over the key table, collecting things as constraints. The column
        # array must return column names in the same order in which they were
        # created.
        cursor.execute(
            """
            SELECT
                c.conname,
                array(
                    SELECT attname
                    FROM unnest(c.conkey) WITH ORDINALITY cols(colid, arridx)
                    JOIN pg_attribute AS ca ON cols.colid = ca.attnum
                    WHERE ca.attrelid = c.conrelid
                    ORDER BY cols.arridx
                ),
                c.contype,
                (SELECT concat(fkc.relname, '.', fka.attname)
                FROM pg_attribute AS fka
                JOIN pg_class AS fkc ON fka.attrelid = fkc.oid
                WHERE fka.attrelid = c.confrelid AND fka.attnum = c.confkey[1]),
                cl.reloptions
            FROM pg_constraint AS c
            JOIN pg_class AS cl ON c.conrelid = cl.oid
            WHERE cl.relname = %s AND pg_catalog.pg_table_is_visible(cl.oid)
        """,
            [table_name],
        )
        for constraint, columns, kind, used_cols, options in cursor.fetchall():
            constraints[constraint] = {
                "columns": columns,
                "primary_key": kind == "p",
                "unique": kind in ["p", "u"],
                "foreign_key": tuple(used_cols.split(".", 1)) if kind == "f" else None,
                "check": kind == "c",
                "index": False,
                "definition": None,
                "options": options,
            }
        # Now get indexes
        cursor.execute(
            """
            SELECT
                indexname,
                array_agg(attname ORDER BY arridx),
                indisunique,
                indisprimary,
                array_agg(ordering ORDER BY arridx),
                amname,
                exprdef,
                s2.attoptions
            FROM (
                SELECT
                    c2.relname as indexname, idx.*, attr.attname, am.amname,
                    CASE
                        WHEN idx.indexprs IS NOT NULL THEN
                            pg_get_indexdef(idx.indexrelid)
                    END AS exprdef,
                    CASE am.amname
                        WHEN %s THEN
                            CASE (option & 1)
                                WHEN 1 THEN 'DESC' ELSE 'ASC'
                            END
                    END as ordering,
                    c2.reloptions as attoptions
                FROM (
                    SELECT *
                    FROM
                        pg_index i,
                        unnest(i.indkey, i.indoption)
                            WITH ORDINALITY koi(key, option, arridx)
                ) idx
                LEFT JOIN pg_class c ON idx.indrelid = c.oid
                LEFT JOIN pg_class c2 ON idx.indexrelid = c2.oid
                LEFT JOIN pg_am am ON c2.relam = am.oid
                LEFT JOIN
                    pg_attribute attr ON attr.attrelid = c.oid AND attr.attnum = idx.key
                WHERE c.relname = %s AND pg_catalog.pg_table_is_visible(c.oid)
            ) s2
            GROUP BY indexname, indisunique, indisprimary, amname, exprdef, attoptions;
        """,
            [self.index_default_access_method, table_name],
        )
        for (
            index,
            columns,
            unique,
            primary,
            orders,
            type_,
            definition,
            options,
        ) in cursor.fetchall():
            if index not in constraints:
                basic_index = (
                    type_ == self.index_default_access_method
                    # '_btree' references
                    # django.contrib.postgres.indexes.BTreeIndex.suffix.
                    and not index.endswith("_btree")
                    and options is None
                )
                constraints[index] = {
                    "columns": columns if columns != [None] else [],
                    "orders": orders if orders != [None] else [],
                    "primary_key": primary,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix if basic_index else type_,
                    "definition": definition,
                    "options": options,
                }
        return constraints

    DatabaseIntrospection.get_constraints = get_constraints
    logger.info("[KINGBASE] postgresql introspection.get_constraints patched (`||` -> concat) for migrate")


def _patch_pattern_ops_pipe_concat():
    """
    运行期修复：把 ``DatabaseWrapper.pattern_ops`` 中的 ``||`` 拼接改写为 ``concat()``。

    原始模板（Django 4.2 postgresql base.py）：
        "contains":    "LIKE '%%' || {} || '%%'"
        "icontains":   "LIKE '%%' || UPPER({}) || '%%'"
        "startswith":  "LIKE {} || '%%'"
        "istartswith": "LIKE UPPER({}) || '%%'"
        "endswith":    "LIKE '%%' || {}"
        "iendswith":   "LIKE '%%' || UPPER({})"

    这些模板用于 ``__contains`` / ``__startswith`` / ``__endswith`` 等当右值为列/表达式时的
    模式匹配。MySQL 模式下 ``||`` 变逻辑 OR，模式串会被算错。改用 ``concat()`` 后两种模式语义一致。
    """
    from django.db.backends.postgresql.base import DatabaseWrapper

    DatabaseWrapper.pattern_ops = {
        "contains": "LIKE concat('%%', {}, '%%')",
        "icontains": "LIKE concat('%%', UPPER({}), '%%')",
        "startswith": "LIKE concat({}, '%%')",
        "istartswith": "LIKE concat(UPPER({}), '%%')",
        "endswith": "LIKE concat('%%', {})",
        "iendswith": "LIKE concat('%%', UPPER({}))",
    }
    logger.info("[KINGBASE] postgresql DatabaseWrapper.pattern_ops patched (`||` -> concat) for runtime LIKE")


def _patch_psycopg3_timestamptz_missing_tz():
    """
    迁移收尾 / 运行期修复：psycopg(v3) 的 timestamptz 文本解析**强制要求带时区偏移**
    （见 psycopg/types/datetime.py 的 ``TimestamptzLoader._re_format``），但 Kingbase MySQL
    模式输出 timestamptz 时**不带偏移**（如 ``2026-06-23 09:59:57.794615``），导致
    ``DataError: can't parse timestamp ... (unknown)`` —— migrate 末尾 ``check_replacements``
    读 ``django_migrations.applied`` 时触发，使整条 migrate 在“全部迁移已 OK”之后仍失败。

    psycopg2 的解析更宽松、不受影响；因此仅当装了 psycopg(v3) 时才打此补丁。

    策略：包装 ``TimestamptzLoader.load``，原始解析抛 DataError 时，按连接时区补 ``+00``
    （本项目连接固定 ``-c timezone=UTC``）后重试；仍失败则抛出原始错误，不吞掉真正的异常。
    """
    try:
        from psycopg.errors import DataError
        from psycopg.types.datetime import TimestamptzLoader
    except ImportError:
        # 纯 psycopg2 环境（如客户现网）不需要此补丁
        logger.info("[KINGBASE] psycopg(v3) 未安装，timestamptz 补丁跳过（psycopg2 不受影响）")
        return

    original_load = TimestamptzLoader.load

    def patched_load(self, data):
        try:
            return original_load(self, data)
        except DataError:
            if data is None:
                raise
            # Kingbase MySQL 模式的 timestamptz 不带时区偏移，按连接时区(UTC)补 +00 重试
            return original_load(self, bytes(data) + b"+00")

    TimestamptzLoader.load = patched_load
    logger.info("[KINGBASE] psycopg3 TimestamptzLoader patched (tolerate missing tz offset, assume UTC)")
