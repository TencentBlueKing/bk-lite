# -- coding: utf-8 --
# @File: __init__.py.py
# @Time: 2025/11/13 14:16
# @Author: windyzhao

import importlib
import pkgutil
from pathlib import Path


def _auto_register_node_params():
    """
    自动发现并导入当前包下所有子模块中的 NodeParams 类，
    触发 BaseNodeParams.__init_subclass__ 完成注册。
    """
    current_dir = Path(__file__).parent
    package_name = __name__

    # 递归遍历当前包及所有子包
    for importer, module_name, is_pkg in pkgutil.walk_packages(
        [str(current_dir)], 
        prefix=f"{package_name}."
    ):
        # 跳过私有模块、__init__ 和 base 模块
        base_name = module_name.split('.')[-1]
        if base_name.startswith('_'):
            continue

        try:
            # 动态导入模块以触发类定义和 __init_subclass__
            importlib.import_module(module_name)
        except Exception:
            # 忽略导入失败的模块,避免阻塞其他模块注册
            # 实际使用时如需调试可记录日志
            pass


# 执行自动注册
_auto_register_node_params()
