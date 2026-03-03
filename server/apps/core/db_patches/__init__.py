"""
数据库兼容性补丁入口。

根据当前 DATABASES 配置的 ENGINE 分发到对应的数据库引擎补丁模块。
每个引擎的补丁独立放置在同目录下的 <engine>.py 文件中，方便按需扩展。

使用方式：
    在 CoreConfig.ready() 中调用 apply_patches() 即可。
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# 引擎关键字 → 补丁模块映射
# 新增数据库引擎时，只需在此处添加映射并创建对应的 .py 文件
_ENGINE_PATCH_MAP = {
    "dameng": "apps.core.db_patches.dameng",
    "goldendb": "apps.core.db_patches.goldendb",
    "oceanbase": "apps.core.db_patches.oceanbase",
    "gaussdb": "apps.core.db_patches.gaussdb",
    # "mysql": "apps.core.db_patches.mysql",
}


def apply_patches():
    """
    读取 settings.DATABASES["default"]["ENGINE"]，
    匹配到对应引擎后加载其补丁模块并调用 patch() 函数。
    """
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")

    for keyword, module_path in _ENGINE_PATCH_MAP.items():
        if keyword in engine:
            try:
                import importlib

                mod = importlib.import_module(module_path)
                mod.patch()
                logger.info("Database patches applied for engine: %s", keyword)
            except Exception:
                logger.exception("Failed to apply database patches for engine: %s", keyword)
            return

    logger.debug("No database patches needed for engine: %s", engine)
