# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/7/14 16:03
# @Author: windyzhao
from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import JSONField

from apps.core.models.group_info import Groups
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

_NETWORK_TOPOLOGY_STATUS_DRAFT = "draft"
_NETWORK_TOPOLOGY_STATUS_PUBLISHED = "published"

_NETWORK_TOPOLOGY_STATUS_CHOICES = (
    (_NETWORK_TOPOLOGY_STATUS_DRAFT, "草稿"),
    (_NETWORK_TOPOLOGY_STATUS_PUBLISHED, "已发布"),
)

_BLANK_NODE_ID_ERROR = "节点缺少 id 字段"
_INVALID_VIEW_SETS_ERROR = "view_sets 必须是 JSON 对象"

#: 外层颜色兜底（无指标 / 无数据 / NaN / 全部未知时使用）。
NODE_OUTER_COLOR_UNKNOWN = "#64748b"


class Directory(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="目录名称")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, related_name="sub_directories", null=True, blank=True, verbose_name="父目录")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_directory"
        verbose_name = "目录"
        constraints = [
            models.UniqueConstraint(fields=["name", "parent"], name="unique_name_parent"),
        ]

    def clean(self):
        # 确保目录层级不超过3层
        if self.parent and self.parent.get_level() >= 2:
            raise ValidationError("Directory hierarchy cannot exceed 3 levels.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def has_children(self):
        return self.sub_directories.exists()

    def get_level(self):
        level = 0
        parent = self.parent
        while parent is not None:
            level += 1
            parent = parent.parent
        return level

    def __str__(self):
        return self.name


class Dashboard(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="仪表盘名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="dashboards", verbose_name="所属目录", null=True, blank=True)
    filters = JSONField(help_text="仪表盘公共过滤条件", verbose_name="过滤条件", blank=True, null=True)
    other = JSONField(help_text="仪表盘其他配置", verbose_name="其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="仪表盘视图集配置", verbose_name="视图集配置", default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_dashboard"
        verbose_name = "仪表盘"

    def __str__(self):
        return self.name


class Topology(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="拓扑图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="topology", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="拓扑图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="拓扑图视图集配置", default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_topology"
        verbose_name = "拓扑图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Architecture(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="架构图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="architecture", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="架构图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="架构图视图集配置", default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_architecture"
        verbose_name = "架构图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Screen(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="大屏名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="screen", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="大屏其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="大屏视图集配置", default=dict)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_screen"
        verbose_name = "大屏"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Report(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="报表名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="report", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="报表其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="报表视图集配置", default=dict)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_report"
        verbose_name = "报表"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class NetworkTopology(MaintainerInfo, TimeInfo, Groups):
    """网络拓扑大屏（P0 扁平 schema）。

    该模型是 design.md §6.3 中描述的 P0 形态：单行承载画布与 WeOps
    凭据，画布内容（节点 / 连线 / 端口对 / 指标 / 阈值）存放在
    :attr:`view_sets` JSON 字段中。运行态缓存（节点颜色 / 连线状态）
    存放在 :attr:`last_runtime_cache` 中，TTL 由 service 层维护。
    """

    name = models.CharField(max_length=128, unique=True, verbose_name="网络拓扑名称")
    desc = models.TextField(blank=True, null=True, verbose_name="描述")
    directory = models.ForeignKey(
        Directory,
        on_delete=models.CASCADE,
        related_name="network_topologies",
        verbose_name="所属目录",
    )
    base_url = models.URLField(max_length=512, verbose_name="WeOps 服务地址")
    token = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        verbose_name="WeOps 服务 Token（密文存储）",
    )
    refresh_interval = models.PositiveIntegerField(default=60, verbose_name="刷新周期")
    status = models.CharField(
        max_length=32,
        choices=_NETWORK_TOPOLOGY_STATUS_CHOICES,
        default=_NETWORK_TOPOLOGY_STATUS_DRAFT,
        verbose_name="发布状态",
    )
    view_sets = JSONField(
        blank=True,
        default=dict,
        verbose_name="画布视图集配置",
    )
    last_runtime_cache = JSONField(
        blank=True,
        default=dict,
        verbose_name="最近运行态缓存",
    )
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name="内置标识键",
    )

    class Meta:
        db_table = "operation_analysis_network_topology"
        verbose_name = "网络拓扑大屏"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    # ------------------------------------------------------------------ #
    # Static helpers                                                      #
    # ------------------------------------------------------------------ #

    _BASE_URL_TRIM_RE = re.compile(r"/+$")

    @staticmethod
    def normalize_base_url(raw: str) -> str:
        """规范化 WeOps base_url：去尾斜杠、强制 http(s) scheme。

        Raises ``rest_framework.exceptions.ValidationError`` when the
        caller provided something other than a http(s) URL.
        """
        if not isinstance(raw, str):
            raise ValidationError({"base_url": ["base_url 必须是字符串"]})
        candidate = raw.strip()
        if not candidate:
            raise ValidationError({"base_url": ["base_url 不能为空"]})
        if "://" not in candidate:
            raise ValidationError({"base_url": ["base_url 必须以 http:// 或 https:// 开头"]})
        if not (candidate.startswith("http://") or candidate.startswith("https://")):
            raise ValidationError({"base_url": ["base_url 必须以 http:// 或 https:// 开头"]})
        return NetworkTopology._BASE_URL_TRIM_RE.sub("", candidate)

    # ------------------------------------------------------------------ #
    # Validation                                                          #
    # ------------------------------------------------------------------ #

    def clean_view_sets(self) -> dict[str, Any]:
        """校验并规范化 :attr:`view_sets` 结构。"""
        from apps.operation_analysis.services.network_topology.canvas_config import _validate_payload

        return _validate_payload(self.view_sets or {})

    def clean(self) -> None:
        """Run application-level validation in addition to Django's defaults.

        Django's :meth:`Model.full_clean` only invokes the model-level
        :meth:`Model.clean` hook — there is no ``clean_<fieldname>``
        automatic dispatch for model fields (that hook is form-only).
        Without this override ``clean_view_sets`` would never run via
        ``full_clean``, allowing P0-schema-foreign data to be persisted
        through serializers that call ``instance.full_clean()``.
        """
        super().clean()
        # ``clean_view_sets`` raises ``ValidationError`` on structural
        # problems; we let it propagate so DRF translates it to a 400.
        self.clean_view_sets()

    def save(self, *args, **kwargs):
        # Normalize base_url on every save so the URL field stays canonical.
        if self.base_url:
            self.base_url = NetworkTopology.normalize_base_url(self.base_url)
        # Encrypt the token automatically. Plain-text tokens are never
        # written to the DB — serializers persist ciphertext directly,
        # so this only catches tokens that bypass the serializer (e.g.
        # from a management script or test).
        if self.token and not self.token.startswith("gAAAAA"):
            from apps.operation_analysis.serializers.network_topology_serializers import encrypt_token

            self.token = encrypt_token(self.token)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Convenience methods used by the serializer / tests                  #
    # ------------------------------------------------------------------ #

    def token_set(self) -> bool:
        return bool(self.token)

    def decrypt_token(self) -> str:
        from apps.operation_analysis.serializers.network_topology_serializers import decrypt_token

        return decrypt_token(self.token)


# --------------------------------------------------------------------------- #
# Module-level helpers for token encryption                                     #
# --------------------------------------------------------------------------- #


def encrypt_weops_token(plain: str | None) -> str | None:
    """Module-level helper used by the serializer and tests."""
    from apps.operation_analysis.serializers.network_topology_serializers import encrypt_token

    if plain in (None, ""):
        return plain if plain is None else ""
    return encrypt_token(plain)


def decrypt_weops_token(cipher: str | None) -> str | None:
    """Module-level helper used by the serializer and tests."""
    from apps.operation_analysis.serializers.network_topology_serializers import decrypt_token

    if not cipher:
        return cipher
    return decrypt_token(cipher)
