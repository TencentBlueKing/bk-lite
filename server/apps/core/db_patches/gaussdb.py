"""
GaussDB 数据库（华为云数据库）兼容性补丁集合。

GaussDB 基于 PostgreSQL 协议，主要限制：
1. 不支持 GIN 索引用于 ustore 表（错误: gin index is not supported for ustore）
2. 部分 PostgreSQL 扩展功能可能不支持

补丁分类：
1. 常规补丁 (patch): 在 CoreConfig.ready() 中应用
   - 包括 JSONField 兼容性补丁（如需要）

Migration 补丁：
- 位于 migrate_patch/patches/gaussdb/ 目录
- 由 cw_cornerstone.migrate_patch 自动加载
- 主要用于跳过不兼容的索引创建（GinIndex/BTreeIndex on JSONField）
"""

import logging

logger = logging.getLogger(__name__)


def patch():
    """
    应用 GaussDB 数据库的常规补丁。

    这些补丁在 CoreConfig.ready() 中调用，
    用于修复 ORM 层面的兼容性问题。
    """
    # GaussDB 基于 PostgreSQL 协议，大部分情况下兼容性较好
    # 目前主要问题是 GIN 索引不支持 ustore，已通过 Migration 补丁处理
    logger.info("GaussDB ORM patches applied")
