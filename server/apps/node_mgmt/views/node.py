from django.core.cache import cache
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import Node
from config.drf.pagination import CustomPageNumberPagination
from apps.node_mgmt.serializers.node import NodeSerializer, BatchBindingNodeConfigurationSerializer, \
    BatchOperateNodeCollectorSerializer
from apps.node_mgmt.services.node import NodeService


class NodeViewSet(mixins.DestroyModelMixin,
                  GenericViewSet):
    queryset = Node.objects.all().prefetch_related('nodeorganization_set').order_by("-created_at")
    pagination_class = CustomPageNumberPagination
    serializer_class = NodeSerializer
    search_fields = ["id", "name", "ip"]

    def add_permission(self, permission, items):
        node_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for node_info in items:
            if node_info["id"] in node_permission_map:
                node_info["permission"] = node_permission_map[node_info["id"]]
            else:
                node_info["permission"] = NodeConstants.DEFAULT_PERMISSION

    @staticmethod
    def format_params(params: dict):
        """
        格式化查询参数，支持灵活的 lookup_expr

        输入格式:
        {
            'name': [
                {'lookup_expr': 'exact', 'value': 'xx'},
                {'lookup_expr': 'icontains', 'value': 'xxx'}
            ],
            'ip': [
                {'lookup_expr': 'exact', 'value': '10.10.10.11'}
            ]
        }

        返回: Q 对象用于过滤 queryset

        注意：所有条件之间都是 AND 逻辑关系
        """
        from django.db.models import Q

        if not params:
            return Q()

        # 最终的 Q 对象，使用 AND 逻辑组合所有条件
        final_q = Q()

        for field_name, conditions in params.items():
            if not conditions or not isinstance(conditions, list):
                continue

            # 同一字段的多个条件也使用 AND 逻辑
            for condition in conditions:
                if not isinstance(condition, dict):
                    continue

                lookup_expr = condition.get('lookup_expr', 'exact')
                value = condition.get('value')

                if value is None or value == '':
                    continue

                # 构建查询键，例如: name__exact, name__icontains
                lookup_key = f"{field_name}__{lookup_expr}"

                # 使用 AND 逻辑组合所有条件
                final_q &= Q(**{lookup_key: value})

        return final_q

    @action(methods=["post"], detail=False, url_path=r"search")
    def search(self, request, *args, **kwargs):
        # 获取权限规则
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "node_mgmt",
            NodeConstants.MODULE,
        )

        # 应用权限过滤
        queryset = permission_filter(Node, permission, team_key="nodeorganization__organization__in", id_key="id__in")

        # 应用自定义查询参数格式化
        custom_filters = request.data.get('filters')
        if custom_filters:
            q_filters = self.format_params(custom_filters)
            if q_filters:
                queryset = queryset.filter(q_filters)

        # 根据组织筛选
        organization_ids = request.query_params.get('organization_ids')
        if organization_ids:
            organization_ids = organization_ids.split(',')
            queryset = queryset.filter(nodeorganization__organization__in=organization_ids).distinct()

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

    @action(methods=["get"], detail=False, url_path=r"enum", filter_backends=[])
    def enum(self, request, *args, **kwargs):
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        # 翻译标签枚举
        translated_tags = {}
        for tag_key, tag_value in CollectorConstants.TAG_ENUM.items():
            name_key = f"{LanguageConstants.COLLECTOR_TAG}.{tag_key}"
            translated_tags[tag_key] = {
                "is_app": tag_value["is_app"],
                "name": lan.get(name_key) or tag_value["name"]
            }

        # 翻译控制器状态枚举
        translated_sidecar_status = {}
        for status_key, status_value in ControllerConstants.SIDECAR_STATUS_ENUM.items():
            status_name_key = f"{LanguageConstants.CONTROLLER_STATUS}.{status_key}"
            translated_sidecar_status[status_key] = lan.get(status_name_key) or status_value

        # 翻译控制器安装方式枚举
        translated_install_method = {}
        for method_key, method_value in ControllerConstants.INSTALL_METHOD_ENUM.items():
            method_name_key = f"{LanguageConstants.CONTROLLER_INSTALL_METHOD}.{method_key}"
            translated_install_method[method_key] = lan.get(method_name_key) or method_value

        # 翻译操作系统枚举
        translated_os = {
            NodeConstants.LINUX_OS: lan.get(f"{LanguageConstants.OS}.{NodeConstants.LINUX_OS}") or NodeConstants.LINUX_OS_DISPLAY,
            NodeConstants.WINDOWS_OS: lan.get(f"{LanguageConstants.OS}.{NodeConstants.WINDOWS_OS}") or NodeConstants.WINDOWS_OS_DISPLAY,
        }

        enum_data = dict(
            sidecar_status=translated_sidecar_status,
            install_method=translated_install_method,
            tag=translated_tags,
            os=translated_os,
        )
        return WebUtils.response_success(enum_data)

    @action(detail=False, methods=["post"], url_path="batch_binding_configuration")
    def batch_binding_node_configuration(self, request):
        serializer = BatchBindingNodeConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_configuration_id = serializer.validated_data["collector_configuration_id"]
        result, message = NodeService.batch_binding_node_configuration(node_ids, collector_configuration_id)

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
        nodes = Node.objects.prefetch_related("collectorconfiguration_set").filter(cloud_region_id=request.data["cloud_region_id"])
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
