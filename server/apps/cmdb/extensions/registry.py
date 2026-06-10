"""社区扩展点注册表（IoC）。

社区定义具名槽位与默认空契约；商业 app 在 AppConfig.ready() 注册实现。
社区代码只 get(name, default)，从不 import 任何企业模块。
"""

_registry: dict = {}


def register(name: str, impl) -> None:
    """注册某扩展槽位的实现（后注册覆盖先注册）。"""
    _registry[name] = impl


def get(name: str, default=None):
    """取某扩展槽位的实现；未注册返回 default。"""
    return _registry.get(name, default)
