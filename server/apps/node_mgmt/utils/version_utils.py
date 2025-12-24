# -- coding: utf-8 --
"""
版本工具类 - 简化版
支持标准的三位版本号格式：x.x.x (如 1.0.0, 1.2.3)
"""
from typing import Tuple


class VersionUtils:
    """版本工具类 - 支持标准三位版本号 (x.x.x)"""

    @staticmethod
    def parse_version(version: str) -> Tuple[int, int, int]:
        """
        解析标准三位版本号 (x.x.x) 为可比较的元组

        Args:
            version: 版本号字符串，如 "1.2.3" 或 "v1.2.3"

        Returns:
            (major, minor, patch) 元组，如 (1, 2, 3)
        """
        if not version:
            return (0, 0, 0)

        # 移除 v 前缀和空格
        version = version.strip().lower().lstrip('v')

        try:
            parts = version.split('.')[:3]  # 只取前三位
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)
        except (ValueError, IndexError):
            return (0, 0, 0)

    @staticmethod
    def is_upgradeable(current: str, latest: str) -> bool:
        """
        判断是否可升级（current < latest）

        Args:
            current: 当前版本
            latest: 最新版本

        Returns:
            True 表示可升级
        """
        if not current or not latest:
            return False
        return VersionUtils.parse_version(current) < VersionUtils.parse_version(latest)
