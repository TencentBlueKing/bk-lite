# -- coding: utf-8 --
"""
版本升级服务 - 简化版
一次性获取所有最新版本，避免重复查询
"""

from typing import Dict

from apps.core.logger import node_logger as logger
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.version_utils import VersionUtils


class VersionUpgradeService:
    """版本升级服务"""

    @staticmethod
    def get_latest_versions_map(component_type: str = "controller", object_name: str | None = None) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        一次性获取所有组件的最新版本映射

        Args:
            component_type: 组件类型 (controller/collector)
            object_name: 只需要单个采集器/控制器时传入，缩小扫描范围（见下方说明）。
                不传时保持原语义：扫描该 component_type 下的全部包（批量场景，如节点
                版本巡检一次性算完所有 controller，需要完整映射，不能按需收窄）。

        Returns:
            {
                'linux': {'telegraf': '1.2.3', 'sidecar': '2.0.0'},
                'windows': {'telegraf': '1.2.1', 'sidecar': '2.0.0'}
            }

        性能说明：包库版本只增不减，随时间推移只会越来越大。只关心一个采集器最新
        版本的调用方（例如导入探针包后刷新升级提示、给单节点安装计算目标版本）如果
        还是不带过滤地拉全表，会随着历史版本积累而越来越慢，且这个查询挂在同步请求
        路径上。传 `object_name` 让调用方显式收窄扫描范围。
        """
        try:
            packages = PackageVersion.objects.filter(type=component_type)
            if object_name:
                packages = packages.filter(object=object_name)
            packages = packages.values("os", "object", "version", "cpu_architecture")

            # 按 os + object + arch 分组
            versions_map = {}
            for pkg in packages:
                os_type = pkg["os"]
                obj_name = pkg["object"]
                version = pkg["version"]
                cpu_architecture = pkg.get("cpu_architecture", "") or ""

                if os_type not in versions_map:
                    versions_map[os_type] = {}

                if obj_name not in versions_map[os_type]:
                    versions_map[os_type][obj_name] = {}

                if cpu_architecture not in versions_map[os_type][obj_name]:
                    versions_map[os_type][obj_name][cpu_architecture] = []

                versions_map[os_type][obj_name][cpu_architecture].append(version)

            # 对每个组件的版本进行排序，取最新的
            result = {}
            for os_type, components in versions_map.items():
                result[os_type] = {}
                for obj_name, arch_versions in components.items():
                    result[os_type][obj_name] = {}
                    for cpu_architecture, versions in arch_versions.items():
                        sorted_versions = sorted(versions, key=VersionUtils.parse_version, reverse=True)
                        result[os_type][obj_name][cpu_architecture] = sorted_versions[0] if sorted_versions else ""

            return result
        except Exception as e:
            logger.error(f"Failed to get latest versions map: {e}")
            return {}
