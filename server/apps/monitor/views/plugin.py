from rest_framework import viewsets
from rest_framework.decorators import action
from django.db import ProgrammingError

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.plugin import MonitorPluginFilter
from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.template_access_guide import TemplateAccessGuideService
from config.drf.pagination import CustomPageNumberPagination


class MonitorPluginViewSet(viewsets.ModelViewSet):
    queryset = MonitorPlugin._default_manager.all()
    serializer_class = MonitorPluginSerializer
    filterset_class = MonitorPluginFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            if result.get("template_type") in {"api", "pull"}:
                result["display_name"] = result.get("display_name") or result["name"]
                result["display_description"] = result["description"]
            else:
                plugin_key = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{result['name']}"
                result["display_name"] = lan.get(f"{plugin_key}.name") or result.get("display_name") or result["name"]
                result["display_description"] = lan.get(f"{plugin_key}.desc") or result["description"]
            result["is_custom"] = result.get("template_type") in {"api", "pull", "snmp"}

        return WebUtils.response_success(results)

    def destroy(self, request, *args, **kwargs):
        plugin = self.get_object()
        if plugin.template_type in {"api", "pull"}:
            try:
                plugin.delete()
            except ProgrammingError as exc:
                if "monitor_plugin_id" in str(exc):
                    raise BaseAppException("当前数据库缺少 monitor_collectconfig.monitor_plugin_id 字段，请先执行 monitor 应用最新迁移") from exc
                raise
            return WebUtils.response_success()
        return super().destroy(request, *args, **kwargs)

    @action(methods=["get"], detail=True, url_path="access_guide")
    def get_access_guide(self, request, pk=None):
        plugin = self.get_object()
        if plugin.template_type != "api":
            return WebUtils.response_error(error_message="当前模板不是自建API模板")

        organization_id = TemplateAccessGuideService.resolve_required_int(request.query_params.get("organization_id"), "organization_id")
        cloud_region_id = TemplateAccessGuideService.resolve_required_int(request.query_params.get("cloud_region_id"), "cloud_region_id")
        data = TemplateAccessGuideService.get_template_document(
            plugin,
            organization_id=organization_id,
            cloud_region_id=cloud_region_id,
        )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="import")
    def import_monitor_object(self, request):
        MonitorPluginService.import_monitor_plugin(request.data)
        return WebUtils.response_success()

    @action(methods=["get"], detail=False, url_path="export/(?P<pk>[^/.]+)")
    def export_monitor_object(self, request, pk):
        data = MonitorPluginService.export_monitor_plugin(pk)
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=True, url_path="ui_template")
    def get_ui_template(self, request, pk=None):
        """
        获取插件的 UI 模板。

        :param pk: 插件 ID
        :return: UI 模板内容（JSON 格式）
        """
        plugin = self.get_object()

        try:
            ui_template = MonitorPluginUITemplate.objects.get(plugin=plugin)
            return WebUtils.response_success(ui_template.content)
        except MonitorPluginUITemplate.DoesNotExist:
            return WebUtils.response_success({})

    @action(methods=["get"], detail=False, url_path="ui_template_by_params")
    def get_ui_template_by_params(self, request):
        """根据采集器名称和采集类型以及监控对象获取插件的 UI 模板。"""
        collector = request.query_params.get("collector")
        collect_type = request.query_params.get("collect_type")
        monitor_object_id = request.query_params.get("monitor_object_id")

        ui_template = MonitorPluginService.get_ui_template_by_params(collector, collect_type, monitor_object_id)
        return WebUtils.response_success(ui_template)
