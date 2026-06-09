"""CMDB 显式扩展门面（facade）。

社区版在各能力域持有固定契约对象与 `get_*_enterprise_extension()` 入口，
企业版在 `apps.cmdb.enterprise.<capability>.provider` 提供实现。删除 enterprise
目录后，全部回退到社区默认空契约（add-only 原则）。
"""
