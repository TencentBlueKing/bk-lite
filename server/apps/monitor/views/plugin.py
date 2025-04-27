from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.plugin import MonitorPluginFilter
from apps.monitor.language.service import SettingLanguage
from apps.monitor.models import MonitorPlugin
from apps.monitor.serializers.pligin import MonitorPluginSerializer
from apps.monitor.services.plugin import MonitorPluginService
from config.drf.pagination import CustomPageNumberPagination


class MonitorPluginVieSet(viewsets.ModelViewSet):
    queryset = MonitorPlugin.objects.all()
    serializer_class = MonitorPluginSerializer
    filterset_class = MonitorPluginFilter
    pagination_class = CustomPageNumberPagination

    @swagger_auto_schema(
        operation_id="monitor_plugin_list",
        operation_description="监控插件列表",
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data
        lan = SettingLanguage(request.user.locale)
        for result in results:
            plugin_map = lan.get_val("MONITOR_OBJECT_PLUGIN", result["name"])
            if not plugin_map:
                plugin_map = {}
            result["display_name"] = plugin_map.get("name") or result["name"]
            result["display_description"] = plugin_map.get("desc") or result["description"]
        return WebUtils.response_success(results)

    @swagger_auto_schema(
        operation_id="monitor_plugin_create",
        operation_description="创建监控插件",
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_plugin_update",
        operation_description="更新监控插件",
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_plugin_partial_update",
        operation_description="部分更新监控插件",
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_plugin_retrieve",
        operation_description="查询监控插件",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_plugin_del",
        operation_description="删除监控插件",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="monitor_plugin_import",
        operation_description="导入监控插件",
    )
    @action(methods=['post'], detail=False, url_path='import')
    def import_monitor_object(self, request):
        MonitorPluginService.import_monitor_plugin(request.data)
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="monitor_plugin_export",
        operation_description="导出监控插件",
    )
    @action(methods=['get'], detail=False, url_path='export/(?P<pk>[^/.]+)')
    def export_monitor_object(self, request, pk):
        data = MonitorPluginService.export_monitor_plugin(pk)
        return WebUtils.response_success(data)
