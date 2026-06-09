# -- coding: utf-8 --
# @File: __init__.py.py
# @Time: 2025/11/13 14:16
# @Author: windyzhao

import importlib
import pkgutil
from pathlib import Path


def _import_modules_in_package(package_name: str, package_paths):
    for _, module_name, _ in pkgutil.walk_packages(package_paths, prefix=f"{package_name}."):
        base_name = module_name.split('.')[-1]
        if base_name.startswith('_'):
            continue

        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - 模块导入失败不应阻塞其他模块注册
            # 忽略导入失败的模块,避免阻塞其他模块注册
            # 实际使用时如需调试可记录日志
            pass


def _auto_register_from_package(package_name: str):
    try:
        package = importlib.import_module(package_name)
    except ModuleNotFoundError:
        return
    except Exception:  # noqa: BLE001 - 扩展包失败不应阻塞主流程
        return

    package_paths = getattr(package, "__path__", None)
    if not package_paths:
        return

    _import_modules_in_package(package_name, package_paths)


def _auto_register_node_params():
    """
    自动发现并导入当前包下所有子模块中的 NodeParams 类，
    触发 BaseNodeParams.__init_subclass__ 完成注册。
    """
    current_dir = Path(__file__).parent
    package_name = __name__

    _import_modules_in_package(package_name, [str(current_dir)])

    # 企业版 NodeParams 经 collect 门面发现（仅扫描 enterprise.collect 包，缺企业时为空）
    from apps.cmdb.collect.extensions import get_collect_enterprise_extension

    for ent_package in get_collect_enterprise_extension().node_param_packages:
        _auto_register_from_package(ent_package)


# 执行自动注册
_auto_register_node_params()
