# -- coding: utf-8 --
# @File: directory_service.py
# @Time: 2025/11/3 16:22
# @Author: windyzhao
from rest_framework.exceptions import ValidationError

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.constants.constants import PERMISSION_DATASOURCE, PERMISSION_DIRECTORY
from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Directory
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY
from apps.operation_analysis.services.node_tree import TreeNodeBuilder


def _get_visible_canvas_queryset(meta, directories, current_team, request, group_ids):
    base = meta.model.objects.filter(directory__in=directories)
    return (
        (
            GroupPermissionMixin.apply_group_filter(
                base.filter(is_build_in=False),
                current_team,
                request.user,
                meta.permission_key,
                group_ids=group_ids,
            )
            | GroupPermissionMixin.apply_group_filter(base.filter(is_build_in=True), current_team, group_ids=group_ids)
        )
        .distinct()
        .order_by("id")
    )


class DictDirectoryService:
    """目录服务类"""

    @staticmethod
    def get_dict_trees(request):
        """
        获取目录树形结构,目录和仪表盘统一作为树节点
        """
        # 验证用户组织权限，构建组织ID列表（支持 include_children）
        try:
            current_team = int(get_current_team(request))
        except (TypeError, ValueError):
            raise ValidationError({"detail": "current_team cookie 缺失或格式错误，请重新登录或刷新页面"})
        group_ids = [current_team]
        if request.COOKIES.get("include_children", "0") == "1":
            from apps.core.utils.viewset_utils import GenericViewSetFun

            group_tree = getattr(request.user, "group_tree", [])
            child_ids = GenericViewSetFun.extract_child_group_ids(group_tree, current_team)
            if child_ids:
                group_ids = child_ids

        # 构建基础查询集并应用组织过滤
        base_queryset = Directory.objects.filter(is_active=True)
        directories = GroupPermissionMixin.apply_group_filter(base_queryset, current_team, group_ids=group_ids).order_by("id")

        # 构建各类画布的查询集
        # 内置画布只需通过组织过滤（第一层），跳过实例级权限过滤（第二层）
        canvas_queryset_map = {
            object_type: _get_visible_canvas_queryset(meta, directories, current_team, request, group_ids)
            for object_type, meta in CANVAS_TYPE_REGISTRY.items()
        }

        # 构建所有节点映射
        all_nodes = {}

        # 构建目录节点
        directory_nodes, parent_children_map = TreeNodeBuilder.get_directory_nodes(directories)
        all_nodes.update(directory_nodes)

        # 构建画布节点
        for object_type, instances in canvas_queryset_map.items():
            all_nodes.update(TreeNodeBuilder.get_canvas_nodes(instances, parent_children_map, object_type))

        def sort_node_key(node_key):
            node = all_nodes[node_key]
            return (node.get("_sort_created_at"), node.get("_sort_id", 0))

        for parent_key, child_keys in parent_children_map.items():
            parent_children_map[parent_key] = sorted(child_keys, key=sort_node_key)

        def build_tree_recursive(node_key):
            """递归构建子树"""
            node = dict(all_nodes[node_key])
            child_keys = parent_children_map.get(node_key, [])

            if child_keys:
                node["children"] = [build_tree_recursive(child_key) for child_key in child_keys]
            else:
                node["children"] = []

            node.pop("_sort_created_at", None)
            node.pop("_sort_id", None)
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
        model_map = {key: meta.model for key, meta in CANVAS_TYPE_REGISTRY.items()}
        model_class = model_map.get(child_module)
        if not model_class:
            return {"count": 0, "items": []}

        result = []
        queryset = model_class.objects.select_related("directory")
        filter_queryset = GroupPermissionMixin.apply_group_filter(queryset, group_id)
        queryset_count = filter_queryset.count()
        instances = filter_queryset[(page - 1) * page_size : page * page_size]
        for instance in instances:
            result.append({"id": instance.id, "name": f"【{instance.directory.name}】{instance.name}" if instance.directory else instance.name})

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
        result = data_sources[(page - 1) * page_size : page * page_size]
        return {"count": data_sources.count(), "items": list(result)}
