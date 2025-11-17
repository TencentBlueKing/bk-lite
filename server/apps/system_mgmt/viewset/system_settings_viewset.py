from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.serializers.system_settings_serializer import SystemSettingsSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class SystemSettingsViewSet(viewsets.ModelViewSet):
    queryset = SystemSettings.objects.all()
    serializer_class = SystemSettingsSerializer

    @action(methods=["GET"], detail=False)
    def get_sys_set(self, request):
        sys_settings = SystemSettings.objects.all().values_list("key", "value")
        return JsonResponse({"result": True, "data": dict(sys_settings)})

    @action(methods=["POST"], detail=False)
    def update_sys_set(self, request):
        kwargs = request.data
        sys_set = list(SystemSettings.objects.filter(key__in=list(kwargs.keys())))
        for i in sys_set:
            i.value = kwargs.get(i.key, i.value)
        SystemSettings.objects.bulk_update(sys_set, ["value"])

        # 记录操作日志
        updated_keys = [i.key for i in sys_set]
        log_operation(request, "update", "system_settings", f"编辑登录设置: {', '.join(updated_keys)}")

        return JsonResponse({"result": True})
