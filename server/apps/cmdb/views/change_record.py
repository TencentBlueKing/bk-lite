import io
import json
from urllib.parse import quote

from django.http import HttpResponse
from openpyxl import Workbook
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.cmdb.filters.change_record import ChangeRecordFilter
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models.change_record import (
    OPERATE_TYPE_CHOICES,
    SCENARIO_CHOICES,
    ChangeRecord,
)
from apps.cmdb.serializers.change_record import ChangeRecordSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination


class ChangeRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ChangeRecord.objects.all().order_by("-created_at")
    serializer_class = ChangeRecordSerializer
    filterset_class = ChangeRecordFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("operation_log-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("operation_log-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return WebUtils.response_success(serializer.data)

    @action(methods=["get"], detail=False)
    @HasPermission("operation_log-View")
    def enum_data(self, request, *args, **kwargs):
        lan = SettingLanguage(request.user.locale)
        result = dict(OPERATE_TYPE_CHOICES)
        for key in result:
            result[key] = lan.get_val("ChangeRecordType", key) or result[key]
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path="enum_scenarios")
    @HasPermission("operation_log-View")
    def enum_scenarios(self, request, *args, **kwargs):
        """变更场景枚举"""
        lan = SettingLanguage(request.user.locale)
        result = dict(SCENARIO_CHOICES)
        for key in result:
            result[key] = lan.get_val("ChangeRecordScenario", key) or result[key]
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path="export")
    @HasPermission("operation_log-View")
    def export(self, request, *args, **kwargs):
        """按当前过滤条件导出 Excel"""
        queryset = self.filter_queryset(self.get_queryset())
        # 限制单次导出条数，避免 OOM
        max_rows = 50000
        queryset = queryset[:max_rows]

        lan = SettingLanguage(request.user.locale)
        type_map = dict(OPERATE_TYPE_CHOICES)
        scenario_map = dict(SCENARIO_CHOICES)

        wb = Workbook()
        ws = wb.active
        ws.title = "ChangeRecord"
        ws.append([
            "ID",
            "实例ID",
            "模型ID",
            "标签",
            "变更类型",
            "变更场景",
            "操作者",
            "模型对象",
            "操作信息",
            "变更前",
            "变更后",
            "创建时间",
        ])
        for record in queryset.iterator(chunk_size=500):
            ws.append([
                record.id,
                record.inst_id,
                record.model_id,
                record.label,
                lan.get_val("ChangeRecordType", record.type) or type_map.get(record.type, record.type),
                lan.get_val("ChangeRecordScenario", record.scenario) or scenario_map.get(record.scenario, record.scenario),
                record.operator,
                record.model_object,
                record.message,
                json.dumps(record.before_data, ensure_ascii=False) if record.before_data else "",
                json.dumps(record.after_data, ensure_ascii=False) if record.after_data else "",
                record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
            ])

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        filename = quote("变更记录.xlsx")
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
        return response
