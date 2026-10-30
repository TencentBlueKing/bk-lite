"""全局配置的校验、保存与运行时凭据解析。"""
import json
import ssl
from urllib.parse import urlsplit, urlunsplit

import requests
from cryptography.fernet import InvalidToken
from django.db import transaction
from rest_framework import serializers

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.itsm import config as itsm_config
from apps.alerts.itsm.config import ItsmError
from apps.alerts.models.itsm import AlertItsmIntegration, AlertItsmTicket
from apps.alerts.utils.operator_log import record_operator_log_deferred_mirror
from apps.core.mixinx import EncryptMixin


class IntegrationInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    enabled = serializers.BooleanField(default=False)
    url = serializers.CharField(max_length=1024)
    token = serializers.CharField(max_length=8192, required=False, allow_blank=True, write_only=True, trim_whitespace=True)
    ca_pem = serializers.CharField(max_length=32768, required=False, allow_blank=True, default="")
    failure_notification = serializers.DictField(default=dict)

    def validate(self, attrs):
        if {"create_id_path", "detail_fields", "states"}.intersection(self.initial_data):
            raise serializers.ValidationError("接口响应与状态由后端适配，请刷新页面后保存连接配置")
        url = attrs["url"].rstrip("/")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise serializers.ValidationError("ITSM 地址格式错误") from None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "\\" in url
            or any(ord(char) < 33 for char in url)
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise serializers.ValidationError("请填写不含凭据或查询参数的 HTTPS 网关 API 地址")
        hostname = parsed.hostname.lower()
        host = f"[{hostname}]" if ":" in hostname else hostname
        netloc = host if port in (None, 443) else f"{host}:{port}"
        try:
            attrs["url"] = requests.Request("GET", urlunsplit(("https", netloc, parsed.path.rstrip("/"), "", ""))).prepare().url.rstrip("/")
        except (requests.RequestException, ValueError):
            raise serializers.ValidationError("ITSM 地址格式错误") from None
        notification = attrs["failure_notification"]
        if set(notification) - {"usernames", "channel_ids"}:
            raise serializers.ValidationError("通知配置字段无效")
        for key, cls in [("usernames", str), ("channel_ids", int)]:
            values = notification.get(key, [])
            if not isinstance(values, list) or len(values) > 100 or any(type(value) is not cls for value in values):
                raise serializers.ValidationError("通知接收人或渠道格式错误")
        if len(json.dumps(attrs).encode()) > 65536:
            raise serializers.ValidationError("ITSM 配置超过 64 KiB")
        if attrs["ca_pem"]:
            try:
                ssl.create_default_context().load_verify_locations(cadata=attrs["ca_pem"])
            except (ssl.SSLError, ValueError):
                raise serializers.ValidationError("CA 证书必须是有效的 PEM 证书") from None
        # enabled 表示允许规则选择此连接；建单契约由规则及客户端校验，
        # 不作为连接配置的启用条件。URL、证书、凭据和团队校验仍独立生效。
        return attrs


def public_config(instance):
    if not instance:
        return None
    return {
        **{key: instance.config[key] for key in ("url", "ca_pem", "failure_notification") if key in instance.config},
        "contract_ready": itsm_config.response_contract_ready(),
        "reference": instance.reference,
        "name": instance.name,
        "enabled": instance.enabled,
        "token_configured": bool(instance.encrypted_token),
    }


def resolve_token(pk, *, allow_disabled=False, expected_url=None):
    queryset = AlertItsmIntegration.objects.filter(pk=pk)
    if not allow_disabled:
        queryset = queryset.filter(enabled=True)
    instance = queryset.first()
    if not instance:
        raise ItsmError("ITSM 集成已停用或不存在")
    if expected_url is not None and instance.config.get("url") != expected_url:
        raise ItsmError("ITSM 目标配置已变更，请重新执行连接检查")
    try:
        return EncryptMixin.get_cipher_suite().decrypt(instance.encrypted_token.encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise ItsmError("ITSM 凭据不可用，请重新配置令牌") from None


def _validate_target_change(instance, values, token):
    if not instance or instance.config.get("url") == values["url"]:
        return
    links = AlertItsmTicket.objects.filter(connection=instance.reference)
    if links.filter(ticket_id__isnull=False).exists() or links.filter(current_execution__status__in=["running", "unknown"]).exists():
        raise serializers.ValidationError({"detail": "此集成已有工单或在途建单，不能更换目标地址；可以更新令牌和证书"})
    if not token:
        raise serializers.ValidationError({"detail": "更换目标地址必须重新提供令牌"})


def _probe_configuration(instance, values):
    from apps.alerts.itsm.client import ItsmClient

    token = values.get("token", "")
    _validate_target_change(instance, values, token)
    if not token:
        if not instance:
            raise serializers.ValidationError({"detail": "首次配置必须提供认证令牌"})
        token = resolve_token(instance.pk, allow_disabled=True, expected_url=values["url"])
    ItsmClient({"url": values["url"], "ca_pem": values.get("ca_pem", "")}, token=token).test_connection()


def test_configuration(team_id, data):
    instance = AlertItsmIntegration.objects.filter(team_id=team_id).first()
    # 空请求保留只读探测已保存配置的 API 用途；表单传入当前草稿。
    if not data:
        if not instance:
            raise serializers.ValidationError({"detail": "请先填写 ITSM 连接信息"})
        data = {"name": instance.name, **instance.config}
    serializer = IntegrationInput(data=data)
    serializer.is_valid(raise_exception=True)
    _probe_configuration(instance, serializer.validated_data)


def save_configuration(team_id, data, operator):
    serializer = IntegrationInput(data=data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    snapshot = AlertItsmIntegration.objects.filter(team_id=team_id).first()
    if values["enabled"]:
        try:
            _probe_configuration(snapshot, values)
        except ItsmError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from None
    token = values.pop("token", "")
    name, enabled = values.pop("name"), values.pop("enabled")
    with transaction.atomic():
        instance, created = AlertItsmIntegration.objects.get_or_create(team_id=team_id, defaults={"name": name})
        instance = AlertItsmIntegration.objects.select_for_update().get(pk=instance.pk)
        if enabled and ((snapshot is None and not created) or (snapshot is not None and snapshot.updated_at != instance.updated_at)):
            raise serializers.ValidationError({"detail": "配置在测试期间已变更，请刷新后重新测试"})
        if not created:
            _validate_target_change(instance, values, token)
        if token:
            try:
                instance.encrypted_token = EncryptMixin.get_cipher_suite().encrypt(token.encode()).decode()
            except (ValueError, TypeError):
                raise serializers.ValidationError({"detail": "凭据加密失败，配置未保存"}) from None
        if not instance.encrypted_token:
            raise serializers.ValidationError({"detail": "首次配置必须提供认证令牌"})
        instance.name, instance.enabled, instance.config = name, enabled, values
        instance.save()
        record_operator_log_deferred_mirror(
            action=LogAction.MODIFY,
            target_type=LogTargetType.SYSTEM,
            operator=operator,
            operator_object="ITSM 集成配置",
            target_id=instance.reference,
            overview="更新当前团队 ITSM 集成配置",
        )
    return instance
