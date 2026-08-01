from django.contrib.auth.hashers import make_password
from django.db import transaction
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
    INITIAL_PASSWORD_ENABLED_KEY = "user_create_initial_password_enabled"
    INITIAL_PASSWORD_HASH_KEY = "user_create_initial_password_hash"
    INITIAL_PASSWORD_INPUT_KEY = "user_create_initial_password"
    INITIAL_PASSWORD_DEFAULTS = {
        INITIAL_PASSWORD_ENABLED_KEY: "0",
        INITIAL_PASSWORD_HASH_KEY: "",
    }
    POLICY_REENTRY_KEYS = {
        "pwd_set_min_length",
        "pwd_set_max_length",
        "pwd_set_required_char_types",
    }

    def _ensure_portal_settings(self):
        default_settings = {
            **self.PORTAL_SETTING_DEFAULTS,
            **self.SENSITIVE_INFO_SETTING_DEFAULTS,
            **self.INITIAL_PASSWORD_DEFAULTS,
        }
        existing_keys = set(SystemSettings.objects.filter(key__in=default_settings.keys()).values_list("key", flat=True))
        missing_settings = [SystemSettings(key=key, value=value) for key, value in default_settings.items() if key not in existing_keys]

        if missing_settings:
            SystemSettings.objects.bulk_create(missing_settings, ignore_conflicts=True)

    @action(methods=["GET"], detail=False)
    @HasPermission("security_settings-View")
    def get_sys_set(self, request):
        self._ensure_portal_settings()
        settings = dict(SystemSettings.objects.all().values_list("key", "value"))
        password_hash = settings.pop(self.INITIAL_PASSWORD_HASH_KEY, "")
        settings["user_create_initial_password_configured"] = "1" if password_hash else "0"
        return JsonResponse({"result": True, "data": settings})

    @action(methods=["GET"], detail=False, permission_classes=[AllowAny])
    def public_portal_branding(self, request):
        self._ensure_portal_settings()
        branding_settings = SystemSettings.objects.filter(key__in=self.PORTAL_BRANDING_KEYS).values_list("key", "value")
        return JsonResponse({"result": True, "data": dict(branding_settings)})

    @action(methods=["POST"], detail=False)
    @HasPermission("security_settings-Edit")
    def update_sys_set(self, request):
        kwargs = dict(request.data)
        initial_password = kwargs.pop(self.INITIAL_PASSWORD_INPUT_KEY, None)
        if isinstance(initial_password, list):
            initial_password = initial_password[-1] if initial_password else None

        current_settings = dict(SystemSettings.objects.values_list("key", "value"))
        current_enabled = current_settings.get(self.INITIAL_PASSWORD_ENABLED_KEY, "0") == "1"
        enabled = kwargs.get(self.INITIAL_PASSWORD_ENABLED_KEY, "1" if current_enabled else "0") == "1"
        policy_changed = any(
            key in kwargs and str(kwargs[key]) != current_settings.get(key)
            for key in self.POLICY_REENTRY_KEYS
        )

        effective_policy = PasswordValidator.get_password_settings()
        try:
            if "pwd_set_min_length" in kwargs:
                effective_policy["min_length"] = int(kwargs["pwd_set_min_length"])
            if "pwd_set_max_length" in kwargs:
                effective_policy["max_length"] = int(kwargs["pwd_set_max_length"])
            if "pwd_set_required_char_types" in kwargs:
                effective_policy["required_char_types"] = [
                    item.strip() for item in str(kwargs["pwd_set_required_char_types"]).split(",") if item.strip()
                ]
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "密码策略配置无效"}, status=400)

        if enabled and (not current_enabled or policy_changed) and not initial_password:
            return JsonResponse({"result": False, "message": "请重新设置初始密码"}, status=400)
        if enabled and initial_password:
            is_valid, error_message = PasswordValidator.validate_password_with_config(initial_password, effective_policy)
            if not is_valid:
                return JsonResponse({"result": False, "message": error_message}, status=400)
        if enabled and not initial_password and not current_settings.get(self.INITIAL_PASSWORD_HASH_KEY):
            return JsonResponse({"result": False, "message": "请设置初始密码"}, status=400)

        if not enabled:
            kwargs[self.INITIAL_PASSWORD_ENABLED_KEY] = "0"
            kwargs[self.INITIAL_PASSWORD_HASH_KEY] = ""
        elif initial_password:
            kwargs[self.INITIAL_PASSWORD_ENABLED_KEY] = "1"
            kwargs[self.INITIAL_PASSWORD_HASH_KEY] = make_password(initial_password)

        with transaction.atomic():
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
