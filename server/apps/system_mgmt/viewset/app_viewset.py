from django.http import JsonResponse

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import App
from apps.system_mgmt.serializers.app_serializer import AppSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class AppViewSet(LanguageViewSet):
    queryset = App.objects.all().order_by("name")
    serializer_class = AppSerializer

    @HasPermission("application_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_build_in:
            message = self.loader.get("error.cannot_delete_builtin_app") if self.loader else "Cannot delete built-in application"
            return JsonResponse({"result": False, "message": message})

        app_name = obj.name
        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "app", f"删除应用: {app_name}")

        return response

    @HasPermission("application_list-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            app_name = response.data.get("name", "")
            log_operation(request, "create", "app", f"新增应用: {app_name}")

        return response

    @HasPermission("application_list-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 200:
            app_name = response.data.get("name", "")
            log_operation(request, "update", "app", f"编辑应用: {app_name}")

        return response

    @HasPermission("application_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
