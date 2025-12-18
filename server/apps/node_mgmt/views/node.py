from django.core.cache import cache
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

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
from apps.node_mgmt.serializers.node import NodeSerializer, BatchBindingNodeConfigurationSerializer, \
    BatchOperateNodeCollectorSerializer
from apps.node_mgmt.services.node import NodeService


class NodeViewSet(mixins.DestroyModelMixin,
                  GenericViewSet):
    queryset = Node.objects.all().prefetch_related('nodeorganization_set').order_by("-created_at")
    pagination_class = CustomPageNumberPagination
    serializer_class = NodeSerializer
    search_fields = ["id", "name", "ip", "cloud_region_id", "install_method"]

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

        # 从 filters 中提取 upgradeable 参数（因为它不是 Node 模型的直接字段）
        upgradeable_from_filters = None
        if custom_filters and 'upgradeable' in custom_filters:
            upgradeable_conditions = custom_filters.pop('upgradeable', None)
            if upgradeable_conditions and isinstance(upgradeable_conditions, list):
                # 取第一个条件的值
                first_condition = upgradeable_conditions[0]
                if isinstance(first_condition, dict):
                    upgradeable_from_filters = first_condition.get('value')

        if custom_filters:
            q_filters = self.format_params(custom_filters)
            if q_filters:
                queryset = queryset.filter(q_filters)

        # 根据组织筛选
        organization_ids = request.query_params.get('organization_ids')
        if organization_ids:
            organization_ids = organization_ids.split(',')
            queryset = queryset.filter(nodeorganization__organization__in=organization_ids).distinct()

        # 是否可升级筛选 - 优先使用 filters 中的值，其次使用 request.data 中的值
        upgradeable = upgradeable_from_filters if upgradeable_from_filters is not None else request.data.get('upgradeable')

        # 规范化布尔值处理（支持字符串 "true"/"false" 和布尔值 True/False）
        if upgradeable is not None:
            if isinstance(upgradeable, str):
                upgradeable = upgradeable.lower() in ('true', '1', 'yes')
            elif not isinstance(upgradeable, bool):
                upgradeable = bool(upgradeable)

            if upgradeable:
                # 筛选有可升级版本的节点
                queryset = queryset.filter(
                    component_versions__component_type='controller',
                    component_versions__upgradeable=True
                ).distinct()
            else:
                # 筛选没有可升级版本的节点（排除有 upgradeable=True 的节点）
                upgradeable_node_ids = Node.objects.filter(
                    component_versions__component_type='controller',
                    component_versions__upgradeable=True
                ).values_list('id', flat=True)
                queryset = queryset.exclude(id__in=upgradeable_node_ids)

        # 应用预加载优化，避免 N+1 查询
        queryset = NodeSerializer.setup_eager_loading(queryset)

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

        # 更新节点名称
        if name is not None:
            node.name = name
            node.save()

        # 如果 organizations 字段有传递（即使是空数组也进）
        if organizations is not None:
            # ① 删除原有组织关联
            NodeOrganization.objects.filter(node=node).delete()

            # ② 批量创建新的组织关联（允许空列表 → 自动清空）
            new_relations = [
                NodeOrganization(node=node, organization=org_id)
                for org_id in organizations
            ]
            NodeOrganization.objects.bulk_create(new_relations)

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
            node_type=ControllerConstants.NODE_TYPE_ENUM,
            tag=translated_tags,
            os=translated_os,
            cloud_server_status=CloudRegionServiceConstants.STATUS_ENUM,
            cloud_deployed_status=CloudRegionServiceConstants.DEPLOY_STATUS_ENUM,
            manual_install_status=ControllerConstants.MANUAL_INSTALL_STATUS_ENUM,
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
