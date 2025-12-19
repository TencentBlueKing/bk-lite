# -- coding: utf-8 --
"""
版本升级服务 - 简化版
一次性获取所有最新版本，避免重复查询
"""
from typing import Dict

from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.version_utils import VersionUtils
from apps.core.logger import node_logger as logger


class VersionUpgradeService:
    """版本升级服务"""

    @staticmethod
    def get_latest_versions_map(component_type: str = 'controller') -> Dict[str, Dict[str, str]]:
        """
        一次性获取所有组件的最新版本映射

        Args:
            component_type: 组件类型 (controller/collector)

        Returns:
            {
                'linux': {'telegraf': '1.2.3', 'sidecar': '2.0.0'},
                'windows': {'telegraf': '1.2.1', 'sidecar': '2.0.0'}
            }
        """
        try:
            packages = PackageVersion.objects.filter(type=component_type).values('os', 'object', 'version')

            # 按 os + object 分组
            versions_map = {}
            for pkg in packages:
                os_type = pkg['os']
                obj_name = pkg['object']
                version = pkg['version']

                if os_type not in versions_map:
                    versions_map[os_type] = {}

                if obj_name not in versions_map[os_type]:
                    versions_map[os_type][obj_name] = []

                versions_map[os_type][obj_name].append(version)

            # 对每个组件的版本进行排序，取最新的
            result = {}
            for os_type, components in versions_map.items():
                result[os_type] = {}
                for obj_name, versions in components.items():
                    # 按版本号排序，取最大的
                    sorted_versions = sorted(versions, key=VersionUtils.parse_version, reverse=True)
                    result[os_type][obj_name] = sorted_versions[0] if sorted_versions else ''

            return result
        except Exception as e:
            logger.error(f"Failed to get latest versions map: {e}")
            return {}
