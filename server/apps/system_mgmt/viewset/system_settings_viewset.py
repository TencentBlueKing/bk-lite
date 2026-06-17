from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.serializers.system_settings_serializer import SystemSettingsSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.pwd_policy_cache import invalidate_pwd_policy_cache as _invalidate_pwd_policy_cache


class SystemSettingsViewSet(viewsets.ModelViewSet):
    queryset = SystemSettings.objects.all()
    serializer_class = SystemSettingsSerializer

    PORTAL_BRANDING_KEYS = ("portal_name", "portal_logo_url", "portal_favicon_url")
    PORTAL_SETTING_DEFAULTS = {
        "portal_name": "BlueKing Lite",
        "portal_logo_url": "",
        "portal_favicon_url": "",
        "watermark_enabled": "0",
        "watermark_text": "BlueKing Lite · ${username} · ${date}",
    }
    SENSITIVE_INFO_SETTING_DEFAULTS = {
        "sensitive_info_protection_enabled": "0",
        "sensitive_info_types": "email,phone",
    }

    def _ensure_portal_settings(self):
        default_settings = {
            **self.PORTAL_SETTING_DEFAULTS,
            **self.SENSITIVE_INFO_SETTING_DEFAULTS,
        }
        existing_keys = set(SystemSettings.objects.filter(key__in=default_settings.keys()).values_list("key", flat=True))
        missing_settings = [SystemSettings(key=key, value=value) for key, value in default_settings.items() if key not in existing_keys]

        if missing_settings:
            SystemSettings.objects.bulk_create(missing_settings, ignore_conflicts=True)

    @action(methods=["GET"], detail=False)
    @HasPermission("security_settings-View")
    def get_sys_set(self, request):
        self._ensure_portal_settings()
        sys_settings = SystemSettings.objects.all().values_list("key", "value")
        return JsonResponse({"result": True, "data": dict(sys_settings)})

    @action(methods=["GET"], detail=False, permission_classes=[AllowAny])
    def public_portal_branding(self, request):
        self._ensure_portal_settings()
        branding_settings = SystemSettings.objects.filter(key__in=self.PORTAL_BRANDING_KEYS).values_list("key", "value")
        return JsonResponse({"result": True, "data": dict(branding_settings)})

    @action(methods=["POST"], detail=False)
    @HasPermission("security_settings-Edit")
    def update_sys_set(self, request):
        kwargs = request.data
        existing_settings = list(SystemSettings.objects.filter(key__in=list(kwargs.keys())))
        existing_keys = {item.key for item in existing_settings}

        for item in existing_settings:
            item.value = kwargs.get(item.key, item.value)

        if existing_settings:
            SystemSettings.objects.bulk_update(existing_settings, ["value"])

        missing_settings = [SystemSettings(key=key, value=value) for key, value in kwargs.items() if key not in existing_keys]
        if missing_settings:
            SystemSettings.objects.bulk_create(missing_settings)

        # 若密码策略相关配置被更新，清除 login 路径缓存（确保新策略立即生效）
        if any(k.startswith("pwd_set_") for k in kwargs):
            _invalidate_pwd_policy_cache()

        # 记录操作日志
        updated_keys = list(kwargs.keys())
        log_operation(request, "update", "system-manager", f"编辑系统设置: {', '.join(updated_keys)}")

        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=False)
    @HasPermission("security_settings-View")
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
