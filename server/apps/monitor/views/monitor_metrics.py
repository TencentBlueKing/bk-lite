from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.monitor_metrics import MetricGroupFilter, MetricFilter
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.models.monitor_metrics import MetricGroup, Metric
from config.drf.pagination import CustomPageNumberPagination


class MetricGroupVieSet(viewsets.ModelViewSet):
    queryset = MetricGroup.objects.all().order_by("sort_order")
    serializer_class = MetricGroupSerializer
    filterset_class = MetricGroupFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        # 获取监控插件ID与名称的映射
        plugin_ids = [i["monitor_plugin"] for i in results if i.get("monitor_plugin")]
        plugin_map = dict(
            MonitorPlugin.objects.filter(id__in=plugin_ids).values_list("id", "name")
        ) if plugin_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            plugin_id = result.get("monitor_plugin")
            if not plugin_id:
                continue
            plugin_name = plugin_map.get(plugin_id)
            if not plugin_name:
                continue
            # 组装语言配置Key（基于插件名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC_GROUP}.{plugin_name}.{result['name']}"
            # 获取语言配置值
            result["display_name"] = lan.get(lan_key) or result["name"]

        return WebUtils.response_success(results)

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

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


class MetricVieSet(viewsets.ModelViewSet):
    queryset = Metric.objects.select_related('monitor_object').all().order_by("sort_order")
    serializer_class = MetricSerializer
    filterset_class = MetricFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        # 获取监控插件ID与名称的映射
        plugin_ids = [i["monitor_plugin"] for i in results if i.get("monitor_plugin")]
        plugin_map = dict(
            MonitorPlugin.objects.filter(id__in=plugin_ids).values_list("id", "name")
        ) if plugin_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            plugin_id = result.get("monitor_plugin")
            if not plugin_id:
                continue
            plugin_name = plugin_map.get(plugin_id)
            if not plugin_name:
                continue
            # 组装语言配置Key（基于插件名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{plugin_name}.{result['name']}"
            # 获取语言配置值
            result["display_name"] = lan.get(f"{lan_key}.name") or result["display_name"]
            result["display_description"] = lan.get(f"{lan_key}.desc") or result["description"]

        return WebUtils.response_success(results)

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

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
