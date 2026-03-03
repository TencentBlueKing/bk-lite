from django.core.cache import cache
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet
from django.db.models import Q

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import Node, NodeOrganization
from config.drf.pagination import CustomPageNumberPagination
from apps.node_mgmt.serializers.node import (
    NodeSerializer,
    BatchBindingNodeConfigurationSerializer,
    BatchOperateNodeCollectorSerializer,
)
from apps.node_mgmt.services.node import NodeService
from apps.node_mgmt.tasks.sidecar_config import sync_node_properties_to_sidecar


class NodeFilterHandler:
    """节点查询过滤器处理器 - 统一管理所有特殊字段的过滤逻辑"""

    @staticmethod
    def normalize_bool_value(value):
        """规范化布尔值"""
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        elif isinstance(value, bool):
            return value
        return bool(value) if value is not None else None

    @staticmethod
    def handle_upgradeable_filter(queryset, conditions):
        """
        处理 upgradeable 过滤逻辑

        Args:
            queryset: Django QuerySet
            conditions: 过滤条件列表

        Returns:
            过滤后的 QuerySet
        """
        if not conditions or not isinstance(conditions, list):
            return queryset

        # 收集所有有效的布尔值
        values = []
        for condition in conditions:
            if not isinstance(condition, dict):
                continue

            value = NodeFilterHandler.normalize_bool_value(condition.get("value"))
            if value is not None:
                values.append(value)

        # 如果没有有效值，返回原查询
        if not values:
            return queryset

        # 检查是否存在矛盾条件（同时有 True 和 False）
        if True in values and False in values:
            # 矛盾条件：既要可升级又要不可升级，返回空结果
            return queryset.none()

        # 取最后一个有效值作为过滤条件
        final_value = values[-1]

        # upgradeable=True: 筛选有可升级版本的节点
        if final_value:
            return queryset.filter(
                component_versions__component_type="controller",
                component_versions__upgradeable=True,
            ).distinct()

        # upgradeable=False: 排除有可升级版本的节点
        else:
            upgradeable_node_ids = Node.objects.filter(
                component_versions__component_type="controller",
                component_versions__upgradeable=True,
            ).values_list("id", flat=True)
            return queryset.exclude(id__in=upgradeable_node_ids)

    @staticmethod
    def build_standard_filters(params):
        """
        构建标准字段的 Q 对象过滤条件

        Args:
            params: 过滤参数字典

        Returns:
            Q 对象
        """
        if not params:
            return Q()

        final_q = Q()

        for field_name, conditions in params.items():
            if not conditions or not isinstance(conditions, list):
                continue

            for condition in conditions:
                if not isinstance(condition, dict):
                    continue

                lookup_expr = condition.get("lookup_expr", "exact")
                value = condition.get("value")

                if value is None or value == "":
                    continue

                # 规范化布尔值
                if lookup_expr == "bool":
                    value = NodeFilterHandler.normalize_bool_value(value)
                    lookup_expr = "exact"

                # 构建查询键
                lookup_key = f"{field_name}__{lookup_expr}"
                final_q &= Q(**{lookup_key: value})

        return final_q

    @classmethod
    def apply_filters(cls, queryset, filters):
        """
        应用所有过滤条件到 QuerySet

        Args:
            queryset: Django QuerySet
            filters: 过滤条件字典

        Returns:
            过滤后的 QuerySet
        """
        if not filters:
            return queryset

        # 特殊字段列表（需要自定义处理逻辑）
        SPECIAL_FIELDS = {
            "upgradeable": cls.handle_upgradeable_filter,
            # 未来可以在这里添加其他特殊字段处理器
            # 'custom_field': cls.handle_custom_field_filter,
        }

        # 分离特殊字段和标准字段
        special_filters = {}
        standard_filters = {}

        for field_name, conditions in filters.items():
            if field_name in SPECIAL_FIELDS:
                special_filters[field_name] = conditions
            else:
                standard_filters[field_name] = conditions

        # 1. 先应用标准字段过滤
        if standard_filters:
            q_filters = cls.build_standard_filters(standard_filters)
            if q_filters:
                queryset = queryset.filter(q_filters).distinct()

        # 2. 再依次应用特殊字段过滤
        for field_name, conditions in special_filters.items():
            handler = SPECIAL_FIELDS[field_name]
            queryset = handler(queryset, conditions)

        return queryset


class NodeViewSet(mixins.DestroyModelMixin, GenericViewSet):
    queryset = (
        Node.objects.all()
        .prefetch_related("nodeorganization_set")
        .order_by("-created_at")
    )
    pagination_class = CustomPageNumberPagination
    serializer_class = NodeSerializer
    search_fields = ["id", "name", "ip", "cloud_region_id", "install_method"]

    def add_permission(self, permission, items):
        node_permission_map = {
            i["id"]: i["permission"] for i in permission.get("instance", [])
        }
        for node_info in items:
            if node_info["id"] in node_permission_map:
                node_info["permission"] = node_permission_map[node_info["id"]]
            else:
                node_info["permission"] = NodeConstants.DEFAULT_PERMISSION

    @action(methods=["post"], detail=False, url_path=r"search")
    def search(self, request, *args, **kwargs):
        # 获取权限规则
        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "node_mgmt",
            NodeConstants.MODULE,
            include_children=include_children,
        )

        # 应用权限过滤
        queryset = permission_filter(
            Node,
            permission,
            team_key="nodeorganization__organization__in",
            id_key="id__in",
        )

        # 应用自定义查询参数格式化（统一处理所有过滤条件）
        custom_filters = request.data.get("filters")
        if custom_filters:
            queryset = NodeFilterHandler.apply_filters(queryset, custom_filters)

        # 根据组织筛选
        organization_ids = request.query_params.get(
            "organization_ids"
        ) or request.data.get("organization_ids")
        if organization_ids:
            organization_ids = organization_ids.split(",")
            queryset = queryset.filter(
                nodeorganization__organization__in=organization_ids
            ).distinct()

        # 根据云区域筛选
        cloud_region_id = request.query_params.get(
            "cloud_region_id"
        ) or request.data.get("cloud_region_id")
        if cloud_region_id:
            queryset = queryset.filter(cloud_region_id=cloud_region_id)

        # 应用预加载优化，避免 N+1 查询
        queryset = NodeSerializer.setup_eager_loading(queryset)

        # 按创建时间倒序排序（最新的在前）
        queryset = queryset.order_by("-created_at")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = NodeSerializer(page, many=True)
            node_data = serializer.data
            processed_data = NodeService.process_node_data(node_data)

            # 添加权限信息到每个节点
            self.add_permission(permission, processed_data)

            return self.get_paginated_response(processed_data)

        serializer = NodeSerializer(queryset, many=True)
        node_data = serializer.data
        processed_data = NodeService.process_node_data(node_data)

        # 添加权限信息到每个节点
        self.add_permission(permission, processed_data)

        return WebUtils.response_success(processed_data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return WebUtils.response_success()

    @action(methods=["patch"], detail=True, url_path="update")
    def update_node(self, request, pk=None):
        node = self.get_object()

        name = request.data.get("name")
        organizations = request.data.get("organizations")

        if name is not None:
            node.name = name
            node.save()

        if organizations is not None:
            NodeOrganization.objects.filter(node=node).delete()
            new_relations = [
                NodeOrganization(node=node, organization=org_id)
                for org_id in organizations
            ]
            NodeOrganization.objects.bulk_create(new_relations)

        if name is not None or organizations is not None:
            sync_node_properties_to_sidecar.delay(
                node_id=node.id, name=name, organizations=organizations
            )

        return WebUtils.response_success()

    @action(methods=["get"], detail=False, url_path=r"enum", filter_backends=[])
    def enum(self, request, *args, **kwargs):
        lan = LanguageLoader(
            app=LanguageConstants.APP, default_lang=request.user.locale
        )

        # 翻译标签枚举
        translated_tags = {}
        for tag_key, tag_value in CollectorConstants.TAG_ENUM.items():
            name_key = f"{LanguageConstants.COLLECTOR_TAG}.{tag_key}"
            translated_tags[tag_key] = {
                "is_app": tag_value["is_app"],
                "name": lan.get(name_key) or tag_value["name"],
            }

        # 翻译控制器状态枚举
        translated_sidecar_status = {}
        for status_key, status_value in ControllerConstants.SIDECAR_STATUS_ENUM.items():
            status_name_key = f"{LanguageConstants.CONTROLLER_STATUS}.{status_key}"
            translated_sidecar_status[status_key] = (
                lan.get(status_name_key) or status_value
            )

        # 翻译控制器安装方式枚举
        translated_install_method = {}
        for method_key, method_value in ControllerConstants.INSTALL_METHOD_ENUM.items():
            method_name_key = (
                f"{LanguageConstants.CONTROLLER_INSTALL_METHOD}.{method_key}"
            )
            translated_install_method[method_key] = (
                lan.get(method_name_key) or method_value
            )

        # 翻译操作系统枚举
        translated_os = {
            NodeConstants.LINUX_OS: lan.get(
                f"{LanguageConstants.OS}.{NodeConstants.LINUX_OS}"
            )
            or NodeConstants.LINUX_OS_DISPLAY,
            NodeConstants.WINDOWS_OS: lan.get(
                f"{LanguageConstants.OS}.{NodeConstants.WINDOWS_OS}"
            )
            or NodeConstants.WINDOWS_OS_DISPLAY,
        }

        enum_data = dict(
            sidecar_status=translated_sidecar_status,
            install_method=translated_install_method,
            node_type=ControllerConstants.NODE_TYPE_ENUM,
            tag=translated_tags,
            os=translated_os,
            cloud_server_status=CloudRegionServiceConstants.STATUS_ENUM,
            manual_install_status=ControllerConstants.MANUAL_INSTALL_STATUS_ENUM,
        )
        return WebUtils.response_success(enum_data)

    @action(detail=False, methods=["post"], url_path="batch_binding_configuration")
    def batch_binding_node_configuration(self, request):
        serializer = BatchBindingNodeConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_configuration_id = serializer.validated_data[
            "collector_configuration_id"
        ]
        result, message = NodeService.batch_binding_node_configuration(
            node_ids, collector_configuration_id
        )

        # 清除cache中的etag
        for node_id in node_ids:
            cache.delete(f"node_etag_{node_id}")

        if result:
            return WebUtils.response_success(message)
        else:
            return WebUtils.response_error(error_message=message)

    @action(detail=False, methods=["post"], url_path="batch_operate_collector")
    def batch_operate_node_collector(self, request):
        serializer = BatchOperateNodeCollectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_id = serializer.validated_data["collector_id"]
        operation = serializer.validated_data["operation"]
        NodeService.batch_operate_node_collector(node_ids, collector_id, operation)

        # 清除cache中的etag
        for node_id in node_ids:
            cache.delete(f"node_etag_{node_id}")

        return WebUtils.response_success()

    @action(detail=False, methods=["post"], url_path="node_config_asso")
    def get_node_config_asso(self, request):
        nodes = Node.objects.prefetch_related("collectorconfiguration_set").filter(
            cloud_region_id=request.data["cloud_region_id"]
        )
        if request.data.get("ids"):
            nodes = nodes.filter(id__in=request.data["ids"])

        result = [
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "operating_system": node.operating_system,
                "cloud_region_id": node.cloud_region_id,
                "configs": [
                    {
                        "id": cfg.id,
                        "name": cfg.name,
                        "collector_id": cfg.collector_id,
                        "is_pre": cfg.is_pre,
                    }
                    for cfg in node.collectorconfiguration_set.all()
                ],
            }
            for node in nodes
        ]

        return WebUtils.response_success(result)
