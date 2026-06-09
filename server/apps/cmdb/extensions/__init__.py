"""CMDB 显式扩展门面（facade）+ 扩展注册表（IoC）。

社区版在各能力域持有固定契约对象与 `get_*_enterprise_extension()` 入口，
默认返回空契约（add-only）。商业实现由 overlay 在启动时把实例注册到
`registry` 的对应槽位；社区只 `registry.get(...)`，从不 import 任何 overlay 模块。
"""
