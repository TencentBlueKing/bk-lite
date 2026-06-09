"""共享的企业版 provider 加载器。

约定：
- provider 模块缺失（企业未部署）→ 返回传入的 ``default`` 工厂，调用即得社区默认契约。
- provider 模块存在但未定义约定入口 → 抛 ``AttributeError``，暴露契约实现错误。
- provider 模块在导入其依赖时缺失其它模块 → 原样抛出，不被吞掉。
"""

from importlib import import_module


def load_provider(module_path: str, attr_name: str, *, default):
    """加载企业 provider 的契约工厂。

    Args:
        module_path: 企业 provider 模块路径，如 ``apps.cmdb.enterprise.model_ops.provider``。
        attr_name: 模块需暴露的工厂函数名，如 ``get_model_enterprise_extension``。
        default: provider 缺失时返回的默认工厂（callable）。

    Returns:
        工厂 callable：调用后返回扩展契约对象。
    """
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        # 缺失的是 provider 模块本身或其某层父包（企业目录整体未部署）→ 回退默认；
        # 若缺失的是 provider 内部依赖（其它无关模块）→ 暴露出来，不吞掉。
        missing = exc.name or ""
        if missing == module_path or module_path.startswith(missing + "."):
            return default
        raise

    if not hasattr(module, attr_name):
        raise AttributeError(f"{module_path} must define {attr_name}")
    return getattr(module, attr_name)
