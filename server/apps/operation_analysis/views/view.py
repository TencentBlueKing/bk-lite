# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/7/14 17:22
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.filters import DataSourceAPIModelFilter, DashboardModelFilter, DirectoryModelFilter, \
    TopologyModelFilter, NameSpaceModelFilter, DataSourceTagModelFilter, ArchitectureModelFilter
from apps.operation_analysis.serializers import DataSourceAPIModelSerializer, DashboardModelSerializer, \
    DirectoryModelSerializer, TopologyModelSerializer, NameSpaceModelSerializer, DataSourceTagModelSerializer, ArchitectureModelSerializer
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet
from apps.operation_analysis.models import DataSourceAPIModel, Dashboard, Directory, Topology, NameSpace, DataSourceTag, Architecture
from apps.core.logger import operation_analysis_logger as logger


class TreeNodeBuilder:
    """树节点构建器基类"""

    @staticmethod
    def get_directory_nodes(directories):
        """构建目录节点"""
        nodes = {}
        parent_children_map = {}

        for directory in directories:
            node_key = f"directory_{directory.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": directory.id,
                "desc": directory.desc,
                "name": directory.name,
                "type": "directory",
                "children": []
            }

            # 构建父子关系映射
            parent_key = f"directory_{directory.parent_id}" if directory.parent_id else None
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes, parent_children_map

    @staticmethod
    def get_dashboard_nodes(dashboards, parent_children_map):
        """构建仪表盘节点"""
        nodes = {}

        for dashboard in dashboards:
            node_key = f"dashboard_{dashboard.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": dashboard.id,
                "name": dashboard.name,
                "desc": dashboard.desc,
                "type": "dashboard",
                "children": []
            }

            # 仪表盘属于目录的子节点
            parent_key = f"directory_{dashboard.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes

    @staticmethod
    def get_topology_nodes(topologies, parent_children_map):
        """构建拓扑图节点"""
        nodes = {}
        for topology in topologies:
            node_key = f"topology_{topology.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": topology.id,
                "name": topology.name,
                "desc": topology.desc,
                "type": "topology",
                "children": []
            }

            parent_key = f"directory_{topology.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes

    @staticmethod
    def get_architecture_nodes(architectures, parent_children_map):
        """构建架构图节点"""
        nodes = {}
        for architecture in architectures:
            node_key = f"architecture_{architecture.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": architecture.id,
                "name": architecture.name,
                "desc": architecture.desc,
                "type": "architecture",
                "children": []
            }

            parent_key = f"directory_{architecture.directory_id}"
            if parent_key not in parent_children_map:
                parent_children_map[parent_key] = []
            parent_children_map[parent_key].append(node_key)

        return nodes


class NameSpaceModelViewSet(ModelViewSet):
    """
    命名空间
    """
    queryset = NameSpace.objects.all()
    serializer_class = NameSpaceModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = NameSpaceModelFilter
    pagination_class = CustomPageNumberPagination


class DataSourceAPIModelViewSet(ModelViewSet):
    """
    数据源
    """
    queryset = DataSourceAPIModel.objects.all()
    serializer_class = DataSourceAPIModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DataSourceAPIModelFilter
    pagination_class = CustomPageNumberPagination

    @action(detail=False, methods=["post"], url_path=r"get_source_data/(?P<pk>[^/.]+)")
    def get_source_data(self, request, *args, **kwargs):
        instance = self.get_object()
        params = request.data
        namespace_list = instance.namespaces.all()
        if "/" not in instance.rest_api:
            namespace = "default"
            path = instance.rest_api
        else:
            namespace, path = instance.rest_api.split("/", 1)
        client = GetNatsData(namespace=namespace, path=path, params=params, namespace_list=namespace_list,
                             request=request)
        result = []
        try:
            data = client.get_data()
            for namespace_id, _data in data.items():
                result.append({"namespace_id": namespace_id, "data": _data})
        except Exception as e:
            logger.error("获取数据源数据失败: {}".format(e))

        return Response(result)


class DirectoryModelViewSet(ModelViewSet):
    """
    目录
    """
    queryset = Directory.objects.all()
    serializer_class = DirectoryModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DirectoryModelFilter
    pagination_class = CustomPageNumberPagination

    def create(self, request, *args, **kwargs):
        data = request.data
        Directory.objects.create(**data)
        return Response(data)


    def update(self, request, *args, **kwargs):
        Directory.objects.filter(id=kwargs["pk"]).update(**request.data)
        return Response(request.data)

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        """
        获取目录树形结构，目录和仪表盘统一作为树节点
        """
        # 一次性获取所有激活的目录数据
        directories = Directory.objects.filter(is_active=True).order_by("id")

        # 一次性获取所有仪表盘数据
        dashboards = Dashboard.objects.filter(
            directory__in=directories
        ).order_by("id")

        # 增加拓扑图查询
        topologies = Topology.objects.filter(
            directory__in=directories
        ).order_by("id")

        # 增加架构图查询
        architectures = Architecture.objects.filter(
            directory__in=directories
        ).order_by("id")

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

        return Response(data)


class DashboardModelViewSet(ModelViewSet):
    """
    仪表盘
    """
    queryset = Dashboard.objects.all()
    serializer_class = DashboardModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DashboardModelFilter
    pagination_class = CustomPageNumberPagination


class TopologyModelViewSet(ModelViewSet):
    """
    拓扑图
    """
    queryset = Topology.objects.all()
    serializer_class = TopologyModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = TopologyModelFilter
    pagination_class = CustomPageNumberPagination


class ArchitectureModelViewSet(ModelViewSet):
    """
    架构图
    """
    queryset = Architecture.objects.all()
    serializer_class = ArchitectureModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = ArchitectureModelFilter
    pagination_class = CustomPageNumberPagination


class DataSourceTagModelViewSet(ModelViewSet):
    """
    数据源标签
    """
    queryset = DataSourceTag.objects.all()
    serializer_class = DataSourceTagModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DataSourceTagModelFilter
    pagination_class = CustomPageNumberPagination
