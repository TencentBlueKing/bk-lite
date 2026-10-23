# -- coding: utf-8 --
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.cmdb.constants.constants import OPERATOR_COLLECT_TASK
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, CREATE_INST, DELETE_INST, UPDATE_INST
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.serializers.custom_collect_plugin import CustomCollectPluginListSerializer, CustomCollectPluginSerializer
from apps.cmdb.services.custom_collect_plugin import attach_list_reference_counts, ensure_deletable
from apps.cmdb.utils.change_record import create_change_record
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.viewset_utils import AuthViewSet
from config.drf.pagination import CustomPageNumberPagination


class CustomCollectPluginViewSet(AuthViewSet):
    """自定义采集插件库。组织隔离复用 AuthViewSet 的 team 过滤，不走任务实例级规则。"""

    queryset = CustomCollectPlugin.objects.all()
    serializer_class = CustomCollectPluginSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ["-updated_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return CustomCollectPluginListSerializer
        return CustomCollectPluginSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(self, "request", None)
        if request is not None and self.action in {"list", "retrieve", "update", "partial_update", "destroy"}:
            _current_team, _include_children, _org_field, query = self.filter_by_group(queryset, request, request.user)
            queryset = queryset.filter(query)
        return queryset

    @HasPermission("auto_collection-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self.get_queryset_by_permission(request, queryset).order_by(self.ORDERING_FIELD)
        page = self.paginate_queryset(queryset)
        batch = page if page is not None else list(queryset)
        attach_list_reference_counts(batch)
        serializer = self.get_serializer(batch, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @HasPermission("auto_collection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("auto_collection-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        plugin = CustomCollectPlugin.objects.filter(plugin_id=response.data.get("plugin_id")).first()
        if plugin is not None:
            self._write_audit(request, plugin, CREATE_INST, message=f"创建自定义采集插件. 标识: {plugin.plugin_id}")
        return response

    @HasPermission("auto_collection-Edit")
    def update(self, request, *args, **kwargs):
        plugin = self.get_object()
        before = plugin.audit_snapshot()
        response = super().update(request, *args, **kwargs)
        plugin.refresh_from_db()
        self._write_audit(
            request,
            plugin,
            UPDATE_INST,
            before=before,
            message=f"更新自定义采集插件. 标识: {plugin.plugin_id} 版本: {plugin.version}",
        )
        return response

    @HasPermission("auto_collection-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("auto_collection-Delete")
    def destroy(self, request, *args, **kwargs):
        plugin = self.get_object()
        try:
            ensure_deletable(plugin)
        except BaseAppException as exc:
            raise ValidationError(str(exc)) from exc
        snapshot = plugin.audit_snapshot()
        response = super().destroy(request, *args, **kwargs)
        self._write_audit(request, plugin, DELETE_INST, before=snapshot, message=f"删除自定义采集插件. 标识: {plugin.plugin_id}")
        return response

    @staticmethod
    def _write_audit(request, plugin, change_type, *, before=None, message=""):
        create_change_record(
            inst_id=plugin.id,
            model_id=plugin.model_id,
            label="自定义采集插件",
            _type=change_type,
            before_data=before,
            after_data=None if change_type == DELETE_INST else plugin.audit_snapshot(),
            operator=getattr(request.user, "username", ""),
            message=message,
            model_object=OPERATOR_COLLECT_TASK,
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
