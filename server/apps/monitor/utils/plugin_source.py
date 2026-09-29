"""插件来源标记：自建与内置互斥，包版本只描述导入包。

`is_pre` 是写保护/预制标记，模型默认 True；用户自建模板若绕过 serializer
仍可能带着 is_pre=True。展示与列表契约必须以 template_type 判定自建，
不能把空 pack_version 当成「内置」。
"""

CUSTOM_PLUGIN_TEMPLATE_TYPES = frozenset({"api", "pull", "snmp", "script"})


def is_custom_plugin_template(template_type) -> bool:
    return (template_type or "") in CUSTOM_PLUGIN_TEMPLATE_TYPES


def is_built_in_plugin(template_type, is_pre=None) -> bool:
    """真实内置：非自建 template_type。is_pre=False 也不能把自建翻成内置。"""
    if is_custom_plugin_template(template_type):
        return False
    if is_pre is False:
        return False
    return True
