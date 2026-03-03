from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.monitor_metrics import MetricGroupFilter, MetricFilter
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.models.monitor_metrics import MetricGroup, Metric
from config.drf.pagination import CustomPageNumberPagination


class MetricGroupViewSet(viewsets.ModelViewSet):
    queryset = MetricGroup.objects.all().order_by("sort_order")
    serializer_class = MetricGroupSerializer
    filterset_class = MetricGroupFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        # 获取监控对象ID与名称的映射
        object_ids = [i["monitor_object"] for i in results if i.get("monitor_object")]
        object_map = dict(
            MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")
        ) if object_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            object_id = result.get("monitor_object")
            if not object_id:
                continue
            object_name = object_map.get(object_id)
            if not object_name:
                continue
            # 组装语言配置Key（基于监控对象名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC_GROUP}.{object_name}.{result['name']}"
            # 获取语言配置值
            result["display_name"] = lan.get(lan_key) or result["name"]

        return WebUtils.response_success(results)

    @action(detail=False, methods=["post"])
    def set_order(self, request, *args, **kwargs):
        updates = [
            MetricGroup(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        MetricGroup.objects.bulk_update(updates, ["sort_order"], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)
        return WebUtils.response_success()


class MetricViewSet(viewsets.ModelViewSet):
    queryset = Metric.objects.select_related('monitor_object').all().order_by("sort_order")
    serializer_class = MetricSerializer
    filterset_class = MetricFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        # 获取监控对象ID与名称的映射
        object_ids = [i["monitor_object"] for i in results if i.get("monitor_object")]
        object_map = dict(
            MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")
        ) if object_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            object_id = result.get("monitor_object")
            if not object_id:
                continue
            object_name = object_map.get(object_id)
            if not object_name:
                continue
            # 组装语言配置Key（基于监控对象名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{object_name}.{result['name']}"
            # 获取语言配置值
            result["display_name"] = lan.get(f"{lan_key}.name") or result["display_name"]
            result["display_description"] = lan.get(f"{lan_key}.desc") or result["description"]

        return WebUtils.response_success(results)

    @action(detail=False, methods=["post"])
    def set_order(self, request, *args, **kwargs):
        updates = [
            Metric(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        Metric.objects.bulk_update(updates, ["sort_order"], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)
        return WebUtils.response_success()
