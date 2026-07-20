# -*- coding: utf-8 -*-
"""
Serializers for the network-topology canvas (P0).

* :class:`NetworkTopologySerializer` — the canvas itself. ``view_sets`` is
  validated against the structural rules in
  :meth:`NetworkTopology.clean_view_sets`; ``base_url`` is normalised via
  :meth:`NetworkTopology.normalize_base_url`; ``token`` is encrypted on
  write and replaced by ``token_set: bool`` on read.
* :class:`NetworkTopologyWeOpsTestConnectionSerializer` — the temporary
  payload for :func:`NetworkTopologyViewSet.test_connection`.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from rest_framework import serializers

from apps.operation_analysis.models.models import NetworkTopology
from apps.operation_analysis.serializers.directory_serializers import DirectoryChainVisibilityMixin

# --------------------------------------------------------------------------- #
# Token encryption                                                              #
# --------------------------------------------------------------------------- #


def _fernet_key() -> bytes:
    """Derive a deterministic Fernet key from ``SECRET_KEY``.

    We use HKDF-style SHA-256 derivation so the same SECRET_KEY produces
    the same key on every worker. The derived key is base64-url-encoded
    (32 bytes) as required by Fernet.
    """
    secret = getattr(settings, "SECRET_KEY", "bk-lite-default-secret") or "bk-lite-default-secret"
    digest = hashlib.sha256(f"network-topology-token::{secret}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_FERNET = Fernet(_fernet_key())


def encrypt_token(plain: str) -> str:
    if not plain:
        return ""
    return _FERNET.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_token(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        return _FERNET.decrypt(cipher.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Legacy plaintext tokens (or otherwise unreadable) round-trip as
        # the literal value so existing rows do not get wiped during the
        # P0 migration.
        return cipher


# --------------------------------------------------------------------------- #
# Serializer                                                                    #
# --------------------------------------------------------------------------- #


class NetworkTopologySerializer(
    DirectoryChainVisibilityMixin,
    serializers.ModelSerializer,
):
    """Read/write representation of :class:`NetworkTopology`.

    继承 :class:`DirectoryChainVisibilityMixin` 让 ``groups`` 必须落库且
    通过所属目录的组织可见性校验 —— 否则新建的网络拓扑在
    :func:`apps.operation_analysis.services.directory_service.DictDirectoryService.get_dict_trees`
    里会被 ``GroupPermissionMixin.apply_group_filter`` 过滤掉,目录树就
    看不到新画布。
    """

    token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        default="",
        help_text="WeOps 服务 Token（明文传入，密文持久化）",
    )
    token_set = serializers.SerializerMethodField(
        help_text="是否已配置 WeOps Token（明文永不返回）",
    )
    view_sets = serializers.JSONField(required=False, default=dict)
    last_runtime_cache = serializers.JSONField(required=False, default=dict, read_only=True)
    # ``groups`` 来自 :class:`apps.core.models.group_info.Groups`,在
    # Meta.fields 里以列表形式声明后会被 ModelSerializer 走原生字段;
    # DirectoryChainVisibilityMixin.validate 会校验它非空且落在目录可见组织内。
    groups = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="组织 ID 列表,需与所属目录的 groups 兼容",
    )

    class Meta:
        model = NetworkTopology
        fields = (
            "id",
            "name",
            "desc",
            "directory",
            "base_url",
            "token",
            "token_set",
            "refresh_interval",
            "status",
            "view_sets",
            "last_runtime_cache",
            "is_build_in",
            "build_in_key",
            "groups",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            # 创建时仍必填(由 ``NetworkTopologySerializer.create`` 兜底),
            # 但 PATCH / PUT 时允许「只改 token 不重传 base_url」之类的局部更新。
            "base_url": {"required": False},
            "name": {"required": False},
            "directory": {"required": False},
        }

    # ---- token round-trip ------------------------------------------------- #

    def get_token_set(self, instance: NetworkTopology) -> bool:
        return bool(instance.token)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        # `view_sets` and `last_runtime_cache` are JSON; ModelSerializer
        # already handles that. Nothing extra to do here.
        return super().to_internal_value(data)

    def validate_base_url(self, raw: str) -> str:
        return NetworkTopology.normalize_base_url(raw)

    def validate_token(self, raw: str) -> str:
        """Reject placeholder/too-short tokens and encrypt before persisting.

        ``******`` 视为「不修改 token」的信号(仅 update 模式有效,见
        :meth:`validate`),不抛 400;返回原值,后续 ``validate`` 会清掉该字段。
        """
        if raw is None:
            return ""
        candidate = str(raw).strip()
        if not candidate:
            return ""
        if candidate in {"******", "*******", "********"} or set(candidate) == {"*"}:
            # 在 update 模式下保留为占位符(让 ``validate`` 决定语义);
            # 在 create 模式下直接报错,因为创建必须有真 token。
            if self.instance is None:
                raise serializers.ValidationError("Token 不允许使用占位符")
            return candidate
        if len(candidate) < 4:
            raise serializers.ValidationError("Token 长度过短，至少 4 个字符")
        return encrypt_token(candidate)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # 先让 :class:`DirectoryChainVisibilityMixin.validate` 跑目录组织可见性校验
        # (避免后续 ``groups`` 与目录不兼容导致新建画布被目录树过滤掉)。
        attrs = super().validate(attrs)
        # Token persistence is gated on "token" appearing in attrs at all.
        # `update()` can legitimately leave it out (i.e. user is not
        # updating credentials), in which case we keep the previous value.
        if "token" in attrs:
            raw_token = attrs.get("token") or ""
            # 客户端表单用 ``******`` 兜底展示「已配置 token」;update 模式
            # 把它当成「保持原值」,避免明文回传也避免被 ``validate_token``
            # 当成占位符直接 400。前端在选择「重置 token」时才会清空再重输。
            if raw_token == "******":
                attrs.pop("token", None)
            elif raw_token == "":
                if self.instance is None:
                    raise serializers.ValidationError({"token": ["Token 不能为空"]})
                attrs.pop("token", None)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> NetworkTopology:
        if not validated_data.get("token"):
            raise serializers.ValidationError({"token": ["Token 不能为空"]})
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        username = getattr(user, "username", None) or "anonymous"
        validated_data.setdefault("created_by", username)
        validated_data.setdefault("updated_by", username)
        instance = NetworkTopology(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance: NetworkTopology, validated_data: dict[str, Any]) -> NetworkTopology:
        for field, value in validated_data.items():
            setattr(instance, field, value)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        username = getattr(user, "username", None) or "anonymous"
        instance.updated_by = username
        instance.full_clean()
        instance.save()
        return instance


class NetworkTopologyWeOpsTestConnectionSerializer(serializers.Serializer):
    """Request shape for :func:`NetworkTopologyViewSet.test_connection`.

    Neither field is persisted — the endpoint is a verification call only.
    """

    base_url = serializers.CharField(max_length=512, required=True)
    token = serializers.CharField(required=True, allow_blank=False)

    def validate_base_url(self, raw: str) -> str:
        return NetworkTopology.normalize_base_url(raw)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


# Patch the model with the encrypt/decrypt methods so existing call-sites
# (and tests) that use ``topology.decrypt_token()`` keep working.
def _decrypt_token(self: NetworkTopology) -> str:  # pragma: no cover - thin wrapper
    return decrypt_token(self.token)


def _encrypt_token(plain: str) -> str:  # pragma: no cover - thin wrapper
    return encrypt_token(plain)


if not hasattr(NetworkTopology, "decrypt_token"):
    NetworkTopology.decrypt_token = _decrypt_token
if not hasattr(NetworkTopology, "encrypt_token"):
    NetworkTopology.encrypt_token = staticmethod(_encrypt_token)
