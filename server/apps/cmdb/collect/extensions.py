"""采集能力域的企业版扩展契约（社区侧门面）。

采集域的「契约」是数据：采集对象树增量、采集插件包、NodeParams 包。社区的
采集对象树合并、插件加载、NodeParams 自动注册三处统一从本门面取，不再直接
walk/import ``apps.cmdb.enterprise``。企业缺失时返回空契约（无树、无包）。
"""

from dataclasses import dataclass, field

from apps.cmdb.extensions import registry


@dataclass(frozen=True)
class CollectEnterpriseExtension:
    collect_tree: list = field(default_factory=list)
    plugin_packages: tuple = ()
    node_param_packages: tuple = ()


_EMPTY_COLLECT_EXTENSION = CollectEnterpriseExtension()


def get_collect_enterprise_extension() -> CollectEnterpriseExtension:
    return registry.get("collect", _EMPTY_COLLECT_EXTENSION)
