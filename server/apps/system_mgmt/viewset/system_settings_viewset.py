from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.serializers.system_settings_serializer import SystemSettingsSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.password_validator import PasswordValidator


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

    @action(methods=["GET"], detail=False)
    def get_password_settings(self, request):
        """
        获取密码策略配置

        返回所有 pwd_set_ 开头的配置项，包括：
        - pwd_set_min_length: 密码最小长度
        - pwd_set_max_length: 密码最大长度
        - pwd_set_required_char_types: 必须包含的字符类型（逗号分隔：uppercase,lowercase,digit,special）
        - pwd_set_validity_period: 密码有效期周期(天)
        - pwd_set_max_retry_count: 密码试错次数
        - pwd_set_lock_duration: 密码试错锁定时长(秒)
        - pwd_set_expiry_reminder_days: 密码过期提醒提前天数
        """
        password_settings = SystemSettings.objects.filter(key__startswith="pwd_set_").values("key", "value")

        # 转换为字典格式
        settings_dict = {item["key"]: item["value"] for item in password_settings}

        # 添加密码策略描述
        policy_description = PasswordValidator.get_password_policy_description()

        return JsonResponse({"result": True, "data": {"settings": settings_dict, "policy_description": policy_description}})
