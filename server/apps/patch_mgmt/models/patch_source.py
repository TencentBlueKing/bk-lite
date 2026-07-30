"""补丁源配置模型"""

from django.db import models

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.patch_mgmt.constants import ConnectivityStatus, PatchSourceType


class PatchSource(TimeInfo, MaintainerInfo):
    """
    补丁源配置

    Windows 类型：WSUS。
    Linux 类型：yum/dnf/apt repo。
    用于搜索、同步和建档。
    """

    name = models.CharField(max_length=128, verbose_name="名称")
    source_type = models.CharField(
        max_length=32,
        choices=PatchSourceType.CHOICES,
        verbose_name="源类型",
    )
    url = models.CharField(max_length=512, blank=True, default="", verbose_name="URL")

    # Linux 源专用字段
    distro_name = models.CharField(max_length=64, blank=True, default="", verbose_name="发行版名称")
    os_version = models.CharField(max_length=64, blank=True, default="", verbose_name="系统版本")
    arch = models.CharField(max_length=32, blank=True, default="", verbose_name="架构")

    # WSUS 网络代理配置
    proxy_host = models.CharField(max_length=256, blank=True, default="", verbose_name="代理主机")
    proxy_port = models.IntegerField(null=True, blank=True, verbose_name="代理端口")

    # WSUS 认证（可选）
    auth_user = models.CharField(max_length=128, blank=True, default="", verbose_name="认证用户名")
    auth_password = models.CharField(max_length=256, blank=True, default="", verbose_name="认证密码")

    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")
    connectivity_status = models.CharField(
        max_length=32,
        choices=ConnectivityStatus.CHOICES,
        default=ConnectivityStatus.UNKNOWN,
        verbose_name="连通性状态",
    )
    last_checked_at = models.DateTimeField(null=True, blank=True, verbose_name="上次连通性检测时间")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "补丁源"
        verbose_name_plural = verbose_name
        db_table = "patch_source"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_source_type_display()})"

    @property
    def is_windows_source(self) -> bool:
        return self.source_type in PatchSourceType.WINDOWS_TYPES

    @property
    def is_linux_source(self) -> bool:
        return self.source_type in PatchSourceType.LINUX_TYPES

    def get_auth_password(self) -> str:
        """返回供连接器使用的明文密码；兼容已有明文测试数据。"""
        data = {"auth_password": self.auth_password or ""}
        EncryptMixin.decrypt_field("auth_password", data)
        return data["auth_password"]
