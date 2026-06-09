"""模型能力域的企业版扩展契约（社区侧门面）。

社区默认实现为空契约：不新增字段类型、不附加字段校验。企业版通过
``apps.cmdb.enterprise.model_ops.provider.get_model_enterprise_extension`` 返回
携带真实逻辑（如附件/图片字段类型与规则）的子类实例。
"""

from apps.cmdb.extensions import registry


class ModelEnterpriseExtension:
    """模型能力域扩展契约。社区默认全部为 no-op。"""

    def file_attr_types(self) -> set:
        """返回属于「文件型」（附件/图片）的 attr_type 集合。

        这是社区代码识别文件字段的唯一来源：写路径校验、列表/搜索/Excel
        排除等都据此判断。社区默认为空集 → 这些分支全部 inert。
        """
        return set()

    def validate_attr(self, attr: dict) -> dict:
        """模型字段建/改时的企业版校验与规范化。默认原样返回。

        企业版可在此对附件/图片类型强制 ``is_required=False``、限制可配置项等。
        """
        return attr

    def unsupported_unique_attr_types(self) -> set:
        """不可加入联合唯一规则的企业字段类型增量。默认空集。"""
        return set()

    def unsupported_auto_relation_attr_types(self) -> set:
        """不参与自动关联匹配的企业字段类型增量。默认空集。"""
        return set()


_EMPTY_MODEL_EXTENSION = ModelEnterpriseExtension()


def get_model_enterprise_extension() -> ModelEnterpriseExtension:
    return registry.get("model_ops", _EMPTY_MODEL_EXTENSION)


def file_attr_types() -> set:
    """社区便捷入口：当前部署下的文件型 attr_type 集合（企业缺失时为空集）。"""
    return set(get_model_enterprise_extension().file_attr_types())


def is_file_attr_type(attr_type) -> bool:
    return attr_type in file_attr_types()


def unsupported_unique_attr_types() -> set:
    """社区便捷入口：企业版不支持联合唯一的字段类型增量（缺企业时为空集）。"""
    return set(get_model_enterprise_extension().unsupported_unique_attr_types())


def unsupported_auto_relation_attr_types() -> set:
    """社区便捷入口：企业版不参与自动关联的字段类型增量（缺企业时为空集）。"""
    return set(get_model_enterprise_extension().unsupported_auto_relation_attr_types())
