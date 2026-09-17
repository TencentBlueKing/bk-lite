"""
PostgreSQL 系兼容库的聚合 ``FILTER (WHERE ...)`` 子句降级。

背景
====
Django 的 ``postgresql`` 后端声明 ``supports_aggregate_filter_clause = True``，于是
``Count("id", filter=Q(...))`` 这类 ORM 写法直接生成 PG 9.4+ 的
``COUNT(...) FILTER (WHERE ...)``。openGauss 家族（Vastbase G100、GaussDB）内核基线是
PG 9.2，不认这个子句，运行期直接报 ``syntax error at or near "("``；Kingbase MySQL
兼容模式的解析器也不保证支持。server 内非测试代码有 30 余处依赖该写法。

策略
====
把 ``supports_aggregate_filter_clause`` 置为 ``False``。Django 自带降级路径：
``Aggregate.as_sql`` 会把条件改写成 ``COUNT(CASE WHEN ... THEN ... END)``，语义与
``FILTER`` 完全等价，且是所有 SQL 方言都支持的写法。业务代码无需改动。

本模块只提供一个共享入口，由各兼容库补丁（vastbase / kingbase / gaussdb）调用。
"""

from apps.core.logger import logger


def disable_aggregate_filter_clause(*extra_feature_classes):
    """把 Django postgresql 后端及其派生 features 类的聚合 FILTER 开关关掉。

    ``extra_feature_classes`` 用于第三方后端（如 cw_cornerstone 的 GaussDB 后端）自带的
    ``DatabaseFeatures`` 子类：Python 属性查找会沿 MRO 回退到 Django 基类，所以只改基类
    通常已足够；显式传入是为了防御子类自行覆写该属性的情况。

    幂等：重复调用只是反复赋同一个值。
    """
    from django.db.backends.postgresql.features import DatabaseFeatures

    targets = (DatabaseFeatures, *extra_feature_classes)
    for features_cls in targets:
        features_cls.supports_aggregate_filter_clause = False
    logger.info(
        "postgresql aggregate FILTER clause disabled, falling back to CASE WHEN (%d feature classes)",
        len(targets),
    )
    return targets
