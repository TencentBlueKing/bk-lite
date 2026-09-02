import json
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import Channel, ChannelChoices, SystemSettings, User
from apps.system_mgmt.serializers.system_settings_serializer import SystemSettingsSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.otp_settings import (
    DEFAULT_OTP_RECOMMENDED_APPS,
    default_otp_whitelist_value,
    parse_otp_recommended_apps,
)
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.password_vault import encrypt_for_vault
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
    INITIAL_PASSWORD_HASH_KEY = "user_create_initial_password_hash"
    INITIAL_PASSWORD_ENCRYPTED_KEY = "user_create_initial_password_encrypted"
    INITIAL_PASSWORD_INPUT_KEY = "user_create_initial_password"
    INITIAL_PASSWORD_MODE_KEY = "user_create_initial_password_mode"
    INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY = "user_create_initial_password_random_email_channel_id"
    INITIAL_PASSWORD_DEFAULTS = {
        INITIAL_PASSWORD_HASH_KEY: "",
        INITIAL_PASSWORD_ENCRYPTED_KEY: "",
        INITIAL_PASSWORD_MODE_KEY: "none",
        INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY: "",
    }
    INITIAL_PASSWORD_MODES = ("fixed", "random", "none")
    POLICY_REENTRY_KEYS = {
        "pwd_set_min_length",
        "pwd_set_max_length",
        "pwd_set_required_char_types",
    }

    def _get_initial_password_email_channel(self, channel_id_raw):
        """返回有效的邮件通道；初始密码启用时这是必填配置。"""
        channel_id_str = str(channel_id_raw or "").strip()
        if not channel_id_str:
            return None, "启用新建用户初始密码时需配置邮件通道"
        try:
            channel = Channel.objects.get(id=int(channel_id_str))
        except (Channel.DoesNotExist, ValueError, TypeError):
            return None, f"邮件通道 {channel_id_str} 不存在或类型不是 email"
        if channel.channel_type != ChannelChoices.EMAIL:
            return None, f"通道 {channel_id_str} 不是 email 类型"
        return channel, None

    def _ensure_portal_settings(self):
        default_settings = {
            **self.PORTAL_SETTING_DEFAULTS,
            **self.SENSITIVE_INFO_SETTING_DEFAULTS,
            **self.INITIAL_PASSWORD_DEFAULTS,
            "otp_recommended_apps": DEFAULT_OTP_RECOMMENDED_APPS,
            "otp_whitelist": default_otp_whitelist_value(),
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
        settings.pop("user_create_initial_password_enabled", None)
        password_hash = settings.pop(self.INITIAL_PASSWORD_HASH_KEY, "")
        settings.pop(self.INITIAL_PASSWORD_ENCRYPTED_KEY, "")
        settings["user_create_initial_password_configured"] = "1" if password_hash else "0"
        mode = settings.get(self.INITIAL_PASSWORD_MODE_KEY, "none")
        settings.setdefault(self.INITIAL_PASSWORD_MODE_KEY, mode)
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
        kwargs.pop("user_create_initial_password_enabled", None)
        initial_password = kwargs.pop(self.INITIAL_PASSWORD_INPUT_KEY, None)
        if isinstance(initial_password, list):
            initial_password = initial_password[-1] if initial_password else None

        current_settings = dict(SystemSettings.objects.values_list("key", "value"))
        if "otp_recommended_apps" in kwargs:
            kwargs["otp_recommended_apps"] = ",".join(parse_otp_recommended_apps(kwargs["otp_recommended_apps"]))
        enable_otp = str(kwargs.get("enable_otp", current_settings.get("enable_otp", "0")))
        if enable_otp == "1":
            apps_value = kwargs["otp_recommended_apps"] if "otp_recommended_apps" in kwargs else current_settings.get("otp_recommended_apps", "")
            if not parse_otp_recommended_apps(apps_value):
                return JsonResponse({"result": False, "message": "推荐认证器应用不能为空"}, status=400)
        if "otp_whitelist" in kwargs:
            raw_whitelist = kwargs["otp_whitelist"]
            if isinstance(raw_whitelist, str):
                try:
                    raw_whitelist = json.loads(raw_whitelist)
                except json.JSONDecodeError:
                    raw_whitelist = None
            if not isinstance(raw_whitelist, list) or any(isinstance(item, bool) for item in raw_whitelist):
                return JsonResponse({"result": False, "message": "OTP 白名单必须是用户 ID 列表"}, status=400)
            try:
                whitelist = [int(item) for item in raw_whitelist]
            except (TypeError, ValueError):
                return JsonResponse({"result": False, "message": "OTP 白名单必须是用户 ID 列表"}, status=400)
            if len(set(whitelist)) != len(whitelist):
                return JsonResponse({"result": False, "message": "OTP 白名单包含重复的用户 ID"}, status=400)
            if User.objects.filter(id__in=whitelist).count() != len(whitelist):
                return JsonResponse({"result": False, "message": "OTP 白名单包含不存在的用户"}, status=400)
            kwargs["otp_whitelist"] = json.dumps(whitelist)
        current_mode = current_settings.get(self.INITIAL_PASSWORD_MODE_KEY, "none")
        if self.INITIAL_PASSWORD_MODE_KEY in kwargs:
            requested_mode = str(kwargs[self.INITIAL_PASSWORD_MODE_KEY])
            if requested_mode not in self.INITIAL_PASSWORD_MODES:
                return JsonResponse(
                    {"result": False, "message": f"初始密码模式不合法: {requested_mode}"},
                    status=400,
                )
            current_mode = requested_mode

        # fixed + enabled:旧行为(单一固定密码 hash)。
        # random:每次创建本地用户生成随机密码,通过 email 通道告知。
        # none:本地用户创建时不设本地密码(走 make_password(None) sentinel)。
        if current_mode != "fixed":
            # 切到 random/none 时,显式清空历史 hash,避免旧 hash 被误读。
            kwargs[self.INITIAL_PASSWORD_HASH_KEY] = ""
            kwargs[self.INITIAL_PASSWORD_ENCRYPTED_KEY] = ""
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

        if current_mode == "fixed":
            if policy_changed and not initial_password:
                return JsonResponse({"result": False, "message": "请重新设置初始密码"}, status=400)
            if initial_password:
                is_valid, error_message = PasswordValidator.validate_password_with_config(initial_password, effective_policy)
                if not is_valid:
                    return JsonResponse({"result": False, "message": error_message}, status=400)
            if not initial_password and not current_settings.get(self.INITIAL_PASSWORD_HASH_KEY):
                return JsonResponse({"result": False, "message": "请设置初始密码"}, status=400)
            if initial_password:
                kwargs[self.INITIAL_PASSWORD_HASH_KEY] = make_password(initial_password)
                kwargs[self.INITIAL_PASSWORD_ENCRYPTED_KEY] = encrypt_for_vault(initial_password)

        initial_password_active = current_mode in ("fixed", "random")
        if initial_password_active:
            channel_id_raw = kwargs.get(
                self.INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY,
                current_settings.get(self.INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY, ""),
            )
            channel, channel_error = self._get_initial_password_email_channel(channel_id_raw)
            if channel_error:
                return JsonResponse({"result": False, "message": channel_error}, status=400)
            kwargs[self.INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY] = str(channel.id)
        else:
            kwargs[self.INITIAL_PASSWORD_RANDOM_EMAIL_CHANNEL_ID_KEY] = ""

        kwargs[self.INITIAL_PASSWORD_MODE_KEY] = current_mode

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

        locale = getattr(getattr(request, "user", None), "locale", "zh-Hans") or "zh-Hans"
        policy_description = PasswordValidator.get_password_policy_description(locale=locale)

        return JsonResponse({"result": True, "data": {"settings": settings_dict, "policy_description": policy_description}})
