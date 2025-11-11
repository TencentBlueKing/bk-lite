# -- coding: utf-8 --
# @File: directory_service.py
# @Time: 2025/11/3 16:22
# @Author: windyzhao
from apps.operation_analysis.constants.constants import PERMISSION_DIRECTORY, PERMISSION_DATASOURCE
from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Directory, Dashboard, Topology, Architecture
from apps.operation_analysis.services.node_tree import TreeNodeBuilder


class DictDirectoryService:
    """目录服务类"""

    @staticmethod
    def get_dict_trees(request):

        """
        获取目录树形结构,目录和仪表盘统一作为树节点
        """
        # 验证用户组织权限
        current_team = int(request.COOKIES.get("current_team"))

        # 构建基础查询集并应用组织过滤
        base_queryset = Directory.objects.filter(is_active=True)
        directories = GroupPermissionMixin.apply_group_filter(base_queryset, current_team).order_by("id")

        # 构建仪表盘、拓扑图、架构图的查询集并应用组织过滤
        dashboard_queryset = Dashboard.objects.filter(directory__in=directories)
        dashboards = GroupPermissionMixin.apply_group_filter(dashboard_queryset, current_team, request.user,
                                                             "directory.dashboard").order_by("id")

        topology_queryset = Topology.objects.filter(directory__in=directories)
        topologies = GroupPermissionMixin.apply_group_filter(topology_queryset, current_team, request.user,
                                                             "directory.topology",
                                                             ).order_by("id")

        architecture_queryset = Architecture.objects.filter(directory__in=directories)
        architectures = GroupPermissionMixin.apply_group_filter(architecture_queryset, current_team, request.user,
                                                                "directory.architecture").order_by("id")

        # 构建所有节点映射
        all_nodes = {}

        # 构建目录节点
        directory_nodes, parent_children_map = TreeNodeBuilder.get_directory_nodes(directories)
        all_nodes.update(directory_nodes)

        # 构建仪表盘节点
        dashboard_nodes = TreeNodeBuilder.get_dashboard_nodes(dashboards, parent_children_map)
        all_nodes.update(dashboard_nodes)

        # 拓扑图节点构建
        topology_nodes = TreeNodeBuilder.get_topology_nodes(topologies, parent_children_map)
        all_nodes.update(topology_nodes)

        # 架构图节点构建
        architecture_nodes = TreeNodeBuilder.get_architecture_nodes(architectures, parent_children_map)
        all_nodes.update(architecture_nodes)

        def build_tree_recursive(node_key):
            """递归构建子树"""
            node = all_nodes[node_key]
            child_keys = parent_children_map.get(node_key, [])

            if child_keys:
                node["children"] = [build_tree_recursive(child_key) for child_key in child_keys]
            else:
                node["children"] = []

            return node

        # 构建根节点列表（顶级目录）
        root_keys = parent_children_map.get(None, [])
        data = [build_tree_recursive(root_key) for root_key in root_keys]

        return data

    @staticmethod
    def get_operation_analysis_module_data(module, child_module, page, page_size, group_id):
        if module == PERMISSION_DIRECTORY:
            return DictDirectoryService.get_directory_modules_data(child_module, page, page_size, group_id)
        elif module == PERMISSION_DATASOURCE:
            return DictDirectoryService.get_datasource_modules_data(page, page_size, group_id)
        else:
            return []

    @staticmethod
    def get_directory_modules_data(child_module, page, page_size, group_id):
        """
        根据目录ID获取目录信息
        :param child_module: 子模块名称
        :param page: 页码
        :param page_size: 每页大小
        :param group_id: 组ID
        :return: 目录信息列表
        """
        model_map = {
            "dashboard": Dashboard,
            "topology": Topology,
            "architecture": Architecture
        }
        model_class = model_map.get(child_module)
        if not model_class:
            return {"count": 0, "items": []}

        result = []
        queryset = model_class.objects.all()
        filter_queryset = GroupPermissionMixin.apply_group_filter(queryset, group_id)
        queryset_count = filter_queryset.count()
        instances = filter_queryset[(page - 1) * page_size: page * page_size]
        for instance in instances:
            result.append({
                "id": instance.id,
                "name": f"【{instance.directory.name}】{instance.name}" if instance.directory else instance.name
            })

        return {"count": queryset_count, "items": result}

    @staticmethod
    def get_datasource_modules_data(page, page_size, group_id):
        """
        根据数据源ID获取数据源信息
        :param page: 页码
        :param page_size: 每页大小
        :param group_id: 组ID
        :return: 数据源信息列表
        """
        queryset = DataSourceAPIModel.objects.all()
        data_sources = GroupPermissionMixin.apply_group_filter(queryset, group_id).values("id", "name")
        result = data_sources[(page - 1) * page_size: page * page_size]
        return {"count": data_sources.count(), "items": list(result)}
