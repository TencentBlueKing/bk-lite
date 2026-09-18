"""
GaussDB 数据库（华为云数据库）兼容性补丁集合。

GaussDB 基于 PostgreSQL 协议（openGauss 内核、PG 9.2 血统），主要限制：
1. 不支持 GIN 索引用于 ustore 表（错误: gin index is not supported for ustore）
2. 不支持 PG 9.4+ 的聚合 ``FILTER (WHERE ...)`` 子句
3. 部分 PostgreSQL 扩展功能可能不支持

补丁分类：
1. 常规补丁 (patch): 在 CoreConfig.ready() 中应用
   - 聚合 FILTER 子句降级为 CASE WHEN（见 ``pg_aggregate_filter``）
   - 包括 JSONField 兼容性补丁（如需要）

Migration 补丁：
- 位于 migrate_patch/patches/gaussdb/ 目录
- 由 cw_cornerstone.migrate_patch 自动加载
- 主要用于跳过不兼容的索引创建（GinIndex/BTreeIndex on JSONField）
"""

from apps.core.logger import logger


def patch():
    """
    应用 GaussDB 数据库的常规补丁。

    这些补丁在 CoreConfig.ready() 中调用，
    用于修复 ORM 层面的兼容性问题。
    """
    # GaussDB 基于 PostgreSQL 协议，大部分情况下兼容性较好
    # GIN 索引不支持 ustore 已通过 Migration 补丁处理；这里处理运行期 SQL 生成
    _patch_aggregate_filter_clause()
    logger.info("GaussDB ORM patches applied (aggregate filter)")


def _gaussdb_feature_classes():
    """cw_cornerstone 的 GaussDB 后端自带 DatabaseFeatures 子类；本地开发环境可能未安装。"""
    try:
        from cw_cornerstone.db.gaussdb.backend.features import DatabaseFeatures
    except ImportError:
        return ()
    return (DatabaseFeatures,)


def _patch_aggregate_filter_clause():
    """聚合 ``FILTER (WHERE ...)`` 降级为 ``CASE WHEN``（PG 9.4 语法，openGauss 内核不支持）。"""
    from apps.core.db_patches.pg_aggregate_filter import disable_aggregate_filter_clause

    disable_aggregate_filter_clause(*_gaussdb_feature_classes())
