from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_metrics import MetricGroupFilter, MetricFilter
from apps.monitor.language.service import SettingLanguage
from apps.monitor.models import MonitorObject
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.models.monitor_metrics import MetricGroup, Metric
from config.drf.pagination import CustomPageNumberPagination


class MetricGroupVieSet(viewsets.ModelViewSet):
    queryset = MetricGroup.objects.all().order_by("sort_order")
    serializer_class = MetricGroupSerializer
    filterset_class = MetricGroupFilter
    pagination_class = CustomPageNumberPagination

    @swagger_auto_schema(
        operation_id="metrics_group_list",
        operation_description="指标分组列表",
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data
        lan = SettingLanguage(request.user.locale)
        monitor_object_name = None
        for result in results:
            if monitor_object_name is None:
                monitor_object = MonitorObject.objects.filter(id=result["monitor_object"]).first()
                if monitor_object:
                    monitor_object_name = monitor_object.name
            if monitor_object_name:
                metric_group_map = lan.get_val("MONITOR_OBJECT_METRIC_GROUP", monitor_object_name)
                if not metric_group_map:
                    metric_group_map = {}
                result["display_name"] = metric_group_map.get(result["name"]) or result["name"]
        return WebUtils.response_success(results)

    @swagger_auto_schema(
        operation_id="metrics_group_create",
        operation_description="创建指标分组",
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_group_update",
        operation_description="更新指标分组",
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_group_partial_update",
        operation_description="部分更新指标分组",
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_group_retrieve",
        operation_description="查询指标分组",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_group_del",
        operation_description="删除指标分组",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_group_set_order",
        operation_description="指标分组排序",
        request_body=openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="指标分组ID"),
                    "sort_order": openapi.Schema(type=openapi.TYPE_INTEGER, description="排序"),
                }
            )
        )
    )
    @action(detail=False, methods=["post"])
    def set_order(self, request, *args, **kwargs):
        updates = [
            MetricGroup(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        MetricGroup.objects.bulk_update(updates, ["sort_order"], batch_size=200)
        return WebUtils.response_success()


class MetricVieSet(viewsets.ModelViewSet):
    queryset = Metric.objects.all().order_by("sort_order")
    serializer_class = MetricSerializer
    filterset_class = MetricFilter
    pagination_class = CustomPageNumberPagination

    @swagger_auto_schema(
        operation_id="metrics_list",
        operation_description="指标列表",
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data
        lan = SettingLanguage(request.user.locale)
        monitor_object_name = None
        for result in results:
            if monitor_object_name is None:
                monitor_object = MonitorObject.objects.filter(id=result["monitor_object"]).first()
                if monitor_object:
                    monitor_object_name = monitor_object.name
            if monitor_object_name:
                metric_map = lan.get_val("MONITOR_OBJECT_METRIC", monitor_object_name)
                if not metric_map:
                    metric_map = {}
                result["display_name"] = metric_map.get(result["name"], {}).get("name") or result["display_name"]
                result["display_description"] = metric_map.get(result["name"], {}).get("desc") or result["description"]
        return WebUtils.response_success(results)

    @swagger_auto_schema(
        operation_id="metrics_create",
        operation_description="创建指标",
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_update",
        operation_description="更新指标",
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_partial_update",
        operation_description="部分更新指标",
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_retrieve",
        operation_description="查询指标",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_del",
        operation_description="删除指标",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="metrics_set_order",
        operation_description="指标排序",
        request_body=openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="指标分组ID"),
                    "sort_order": openapi.Schema(type=openapi.TYPE_INTEGER, description="排序"),
                }
            )
        )
    )
    @action(detail=False, methods=["post"])
    def set_order(self, request, *args, **kwargs):
        updates = [
            Metric(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        Metric.objects.bulk_update(updates, ["sort_order"], batch_size=200)
        return WebUtils.response_success()
