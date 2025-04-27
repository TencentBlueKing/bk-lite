from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_object import MonitorInstanceGroupingRuleFilter
from apps.monitor.models import MonitorInstanceGroupingRule, MonitorInstance, MonitorObject
from apps.monitor.serializers.monitor_object import MonitorInstanceGroupingRuleSerializer
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.node_mgmt_api import NodeUtils
from config.drf.pagination import CustomPageNumberPagination


class MonitorInstanceVieSet(viewsets.ViewSet):

    @swagger_auto_schema(
        operation_description="获取查询参数枚举",
        manual_parameters=[
            openapi.Parameter("name", openapi.IN_PATH, description="对象名称", type=openapi.TYPE_STRING,
                              required=True),
        ],
    )
    @action(methods=['get'], detail=False, url_path='query_params_enum/(?P<name>[^/.]+)')
    def get_query_params_enum(self, request, name):
        data = InstanceSearch.get_query_params_enum(name)
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="monitor_instance_list",
        operation_description="监控实例列表",
        manual_parameters=[
            openapi.Parameter("monitor_object_id", openapi.IN_PATH, description="指标查询参数",
                              type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter("page", openapi.IN_QUERY, description="页码", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="每页数据条数", type=openapi.TYPE_INTEGER),
            openapi.Parameter("add_metrics", openapi.IN_QUERY, description="是否添加指标", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter("name", openapi.IN_QUERY, description="监控实例名称", type=openapi.TYPE_STRING),
        ],
    )
    @action(methods=['get'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/list')
    def monitor_instance_list(self, request, monitor_object_id):
        page, page_size = request.GET.get("page", 1), request.GET.get("page_size", 10)
        data = MonitorObjectService.get_monitor_instance(
            int(monitor_object_id),
            int(page),
            int(page_size),
            request.GET.get("name"),
            [i["id"] for i in request.user.group_list],
            request.user.is_superuser,
            bool(request.GET.get("add_metrics", False)),
        )
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="monitor_instance_search",
        operation_description="监控实例查询",
        manual_parameters=[
            openapi.Parameter("monitor_object_id", openapi.IN_PATH, description="指标查询参数",
                              type=openapi.TYPE_INTEGER, required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "page": openapi.Schema(type=openapi.TYPE_INTEGER, description="页码"),
                "page_size": openapi.Schema(type=openapi.TYPE_INTEGER, description="每页数据条数"),
                "add_metrics": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="是否添加指标"),
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="监控实例名称"),
                "vm_params": openapi.Schema(type=openapi.TYPE_OBJECT, description="维度参数"),
            },
        )
    )
    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/search')
    def monitor_instance_search(self, request, monitor_object_id):
        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise ValueError("Monitor object does not exist")
        search_obj = InstanceSearch(
            monitor_obj,
            dict(group_list=[i["id"] for i in request.user.group_list],
                 is_superuser=request.user.is_superuser,
                 **request.data)
        )
        data = search_obj.search()
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="generate_monitor_instance_id",
        operation_description="生成监控实例ID",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "monitor_instance_name": openapi.Schema(type=openapi.TYPE_STRING, description="监控实例名称"),
                "interval": openapi.Schema(type=openapi.TYPE_INTEGER, description="监控实例采集间隔(s)"),
            },
            required=["monitor_instance_name", "interval"]
        )
    )
    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/generate_instance_id')
    def generate_monitor_instance_id(self, request, monitor_object_id):
        result = MonitorObjectService.generate_monitor_instance_id(
            int(monitor_object_id),
            request.data["monitor_instance_name"],
            request.data["interval"],
        )
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="check_monitor_instance",
        operation_description="校验监控实例是否已存在",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
                properties={
                    "instance_id": openapi.Schema(type=openapi.TYPE_STRING, description="监控实例id"),
                    "instance_name": openapi.Schema(type=openapi.TYPE_INTEGER, description="监控实例名称"),
                },
                required=["instance_id", "instance_name"]
        )
    )
    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/check_monitor_instance')
    def create_monitor_instance(self, request, monitor_object_id):
        MonitorObjectService.check_monitor_instance(
            int(monitor_object_id),
            request.data
        )
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="autodiscover_monitor_instance",
        operation_description="自动发现监控实例",
    )
    @action(methods=['get'], detail=False, url_path='autodiscover_monitor_instance')
    def autodiscover_monitor_instance(self, request):
        MonitorObjectService.autodiscover_monitor_instance()
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="remove_monitor_instance",
        operation_description="移除监控实例",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "instance_ids": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description="监控实例ID列表"),
                "clean_child_config": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="是否清除子配置"),
            },
            required=["instance_ids", "clean_child_config"]
        )
    )
    @action(methods=['post'], detail=False, url_path='remove_monitor_instance')
    def remove_monitor_instance(self, request):
        instance_ids = request.data.get("instance_ids", [])
        MonitorInstance.objects.filter(id__in=instance_ids).update(is_deleted=True)
        if request.data.get("clean_child_config"):
            NodeUtils.delete_instance_child_config(instance_ids)
        return WebUtils.response_success()


class MonitorInstanceGroupingRuleVieSet(viewsets.ModelViewSet):
    queryset = MonitorInstanceGroupingRule.objects.all()
    serializer_class = MonitorInstanceGroupingRuleSerializer
    filterset_class = MonitorInstanceGroupingRuleFilter
    pagination_class = CustomPageNumberPagination

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_list",
        operation_description="监控实例分组规则列表",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_create",
        operation_description="创建监控实例分组规则",
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_update",
        operation_description="更新监控实例分组规则",
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_partial_update",
        operation_description="部分更新监控实例分组规则",
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_retrieve",
        operation_description="查询监控实例分组规则",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_instance_grouping_rule_del",
        operation_description="删除监控实例分组规则",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)