from datetime import datetime
from io import BytesIO

from django.http import HttpResponse, JsonResponse
from django_filters import rest_framework as filters
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import ErrorLog
from apps.system_mgmt.serializers.error_log_serializer import ErrorLogSerializer
from apps.system_mgmt.utils.audit_log_export import export_limit_rejection
from apps.system_mgmt.utils.error_log_presentation import (
    STACK_UNRECORDED,
    UNRECORDED,
    apply_export_mask,
    expand_app_filter_values,
    export_unrecorded,
    present_error_log,
)
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin


class ErrorLogFilter(filters.FilterSet):
    time_start = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    time_end = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    username = filters.CharFilter(field_name="username", lookup_expr="icontains")
    app = filters.CharFilter(method="filter_app_in")
    module = filters.CharFilter(field_name="module", lookup_expr="icontains")
    keyword = filters.CharFilter(field_name="error_message", lookup_expr="icontains")

    class Meta:
        model = ErrorLog
        fields = ["time_start", "time_end", "username", "app", "module", "keyword"]

    def filter_app_in(self, queryset, name, value):
        if not value:
            return queryset
        app_list = expand_app_filter_values(app.strip() for app in value.split(",") if app.strip())
        if app_list:
            return queryset.filter(app__in=app_list)
        return queryset


class ErrorLogViewSet(GroupFilterMixin, LanguageViewSet):
    queryset = ErrorLog.objects.all().order_by("-created_at")
    serializer_class = ErrorLogSerializer
    filterset_class = ErrorLogFilter
    permission_classes = [permissions.IsAuthenticated]

    @HasPermission("error_logs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _export_label(self, key, fallback):
        loader = getattr(self, "loader", None)
        if loader is None:
            return fallback
        return loader.get(key) or fallback

    def get_http_method_names(self):
        if self.action == "export_excel":
            return ["post", "options"]
        return ["get", "head", "options"]

    def http_method_not_allowed(self, request, *args, **kwargs):
        if request.method.lower() not in self.get_http_method_names():
            return super().http_method_not_allowed(request, *args, **kwargs)
        return super().http_method_not_allowed(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        message = self.loader.get("error.detail_not_supported") if self.loader else "不支持详情查询"
        return JsonResponse({"result": False, "message": message}, status=405)

    def create(self, request, *args, **kwargs):
        message = self.loader.get("error.create_not_supported") if self.loader else "不支持手动创建"
        return JsonResponse({"result": False, "message": message}, status=405)

    def update(self, request, *args, **kwargs):
        message = self.loader.get("error.update_not_supported") if self.loader else "不支持修改"
        return JsonResponse({"result": False, "message": message}, status=405)

    def destroy(self, request, *args, **kwargs):
        message = self.loader.get("error.delete_not_supported") if self.loader else "不支持删除"
        return JsonResponse({"result": False, "message": message}, status=405)

    @action(detail=False, methods=["post"])
    @HasPermission("error_logs-View")
    def export_excel(self, request):
        selected_ids = request.data.get("selected_ids", [])
        queryset = self.get_queryset()
        if selected_ids:
            queryset = queryset.filter(id__in=selected_ids)
        else:
            filterset = self.filterset_class(request.data, queryset=queryset)
            if filterset.is_valid():
                queryset = filterset.qs
            else:
                return Response({"result": False, "message": "Invalid filter parameters", "errors": filterset.errors}, status=400)

        rejection = export_limit_rejection(request, queryset)
        if rejection is not None:
            return rejection

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = self._export_label("export.error_log_sheet", "错误日志")
        headers = [
            self._export_label("export.column_time", "时间"),
            self._export_label("export.column_related_user", "关联用户"),
            self._export_label("export.column_business_module", "业务模块"),
            self._export_label("export.column_error_reason", "错误原因"),
            self._export_label("export.column_exception_type", "异常类型"),
            self._export_label("export.column_request_method", "请求方法"),
            self._export_label("export.column_path", "路径"),
            self._export_label("export.column_tech_module", "技术模块"),
            self._export_label("export.column_recorded_error_text", "已记录错误文本"),
            self._export_label("export.column_stack", "堆栈"),
        ]
        sheet.append(headers)

        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        header_alignment = Alignment(horizontal="center", vertical="center")
        for col_num, _ in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment

        column_widths = [22, 16, 20, 40, 18, 12, 40, 18, 50, 50]
        for i, width in enumerate(column_widths, 1):
            sheet.column_dimensions[sheet.cell(row=1, column=i).column_letter].width = width

        unrecorded = self._export_label("outcome.unrecorded", UNRECORDED)
        stack_unrecorded = self._export_label("export.stack_unrecorded", STACK_UNRECORDED)

        for log in queryset:
            presented = present_error_log(
                app=log.app,
                error_message=log.error_message,
                stack_trace=log.stack_trace,
                loader=self.loader,
            )
            row_data = [
                log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "-",
                log.username,
                presented.app_name,
                apply_export_mask(presented.reason) if presented.reason else unrecorded,
                export_unrecorded(presented.exception_type, unrecorded),
                export_unrecorded(presented.method, unrecorded),
                export_unrecorded(presented.path, unrecorded),
                log.module or unrecorded,
                apply_export_mask(presented.recorded_text) if presented.recorded_text else unrecorded,
                apply_export_mask(presented.stack_text) if presented.stack_text else stack_unrecorded,
            ]
            sheet.append(row_data)
            row_num = sheet.max_row
            for col_num in range(1, len(headers) + 1):
                cell = sheet.cell(row=row_num, column=col_num)
                cell.alignment = Alignment(horizontal="left", vertical="center")

        file_stream = BytesIO()
        workbook.save(file_stream)
        file_stream.seek(0)
        filename = f"{self._export_label('export.error_log_filename', '错误日志')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response = HttpResponse(file_stream.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
