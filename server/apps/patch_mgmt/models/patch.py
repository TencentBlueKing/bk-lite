"""补丁主记录及 OS 扩展 detail 表"""

import uuid
from pathlib import Path

from django.db import models
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.patch_mgmt.constants import (
    OSType,
    PackageManagerType,
    PackageStatus,
    PatchSeverity,
    PatchType,
)

PATCH_PACKAGE_BUCKET = "patch-mgmt-packages"


def windows_patch_package_upload_path(instance, filename: str) -> str:
    """为手工 Windows 补丁包生成不可猜测的对象键。"""
    extension = Path(filename).suffix.lower()
    digest_prefix = (instance.package_sha256 or "pending")[:12]
    return f"windows/{instance.patch_id}/{digest_prefix}/{uuid.uuid4().hex}{extension}"


class Patch(TimeInfo, MaintainerInfo):
    """
    补丁主记录（统一主表）

    Windows 和 Linux 补丁均使用此主表，OS 特有字段由
    WindowsPatchDetail / LinuxPatchDetail 扩展 detail 表承载。
    """

    title = models.CharField(max_length=512, verbose_name="标题")
    os_type = models.CharField(
        max_length=16, choices=OSType.CHOICES, db_index=True, verbose_name="OS类型"
    )
    patch_type = models.CharField(
        max_length=16, choices=PatchType.CHOICES, default=PatchType.SECURITY, verbose_name="补丁类型"
    )
    severity = models.CharField(
        max_length=16,
        choices=PatchSeverity.CHOICES,
        default=PatchSeverity.UNSPECIFIED,
        db_index=True,
        verbose_name="严重级别",
    )

    # CVE 列表，例：["CVE-2024-21234", "CVE-2024-21235"]
    cve_list = models.JSONField(default=list, verbose_name="CVE列表")

    # 来源（补丁源），允许多个（同一补丁可从多个源同步入库）
    sources = models.ManyToManyField(
        "patch_mgmt.PatchSource",
        blank=True,
        related_name="patches",
        verbose_name="来源",
    )

    pkg_status = models.CharField(
        max_length=32,
        choices=PackageStatus.CHOICES,
        default=PackageStatus.PENDING,
        db_index=True,
        verbose_name="包状态",
    )

    # 适用范围（OS 版本、产品等），结构由 OS 类型决定
    applicable_scope = models.JSONField(default=dict, verbose_name="适用范围")

    # 适用规则（插件或引擎用于判断目标是否适用此补丁的规则）
    applicable_rules = models.JSONField(default=dict, verbose_name="适用规则")

    # 依赖/替代关系（存储 Patch.id 列表，MVP 简化为 JSONField）
    dependency_ids = models.JSONField(default=list, verbose_name="依赖补丁ID列表")
    replacement_ids = models.JSONField(default=list, verbose_name="替代补丁ID列表")

    released_at = models.DateTimeField(null=True, blank=True, verbose_name="发布时间")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="最近同步时间")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "补丁"
        verbose_name_plural = verbose_name
        db_table = "patch_patch"
        ordering = ["-released_at", "-created_at"]

    def __str__(self) -> str:
        return self.title


class WindowsPatchDetail(models.Model):
    """Windows 补丁扩展 detail 表（与 Patch 1:1）"""

    patch = models.OneToOneField(
        Patch,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="windows_detail",
        verbose_name="补丁主记录",
    )

    # KB 编号，例：KB5034441
    kb_number = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="KB编号")

    # 适用产品列表，例：["Windows Server 2019", "Windows Server 2022"]
    product_list = models.JSONField(default=list, verbose_name="适用产品列表")

    # 适用架构，例：["x64"]
    architectures = models.JSONField(default=list, verbose_name="适用架构")

    # MS 安全公告编号（可选）
    ms_bulletin = models.CharField(max_length=32, blank=True, default="", verbose_name="MS安全公告编号")

    package_file = models.FileField(
        verbose_name="手工补丁包",
        storage=MinioBackend(bucket_name=PATCH_PACKAGE_BUCKET),
        upload_to=windows_patch_package_upload_path,
        blank=True,
        null=True,
    )
    package_original_name = models.CharField(max_length=255, blank=True, default="", verbose_name="原始文件名")
    package_size = models.BigIntegerField(default=0, verbose_name="文件大小")
    package_sha256 = models.CharField(max_length=64, blank=True, default="", verbose_name="SHA-256")
    package_extension = models.CharField(max_length=8, blank=True, default="", verbose_name="文件扩展名")
    package_error = models.TextField(blank=True, default="", verbose_name="文件处理错误")
    package_uploaded_at = models.DateTimeField(null=True, blank=True, verbose_name="文件上传完成时间")

    class Meta:
        verbose_name = "Windows补丁详情"
        verbose_name_plural = verbose_name
        db_table = "patch_windows_detail"
        constraints = [
            models.UniqueConstraint(
                fields=["kb_number"],
                condition=~models.Q(kb_number=""),
                name="patch_windows_unique_nonempty_kb",
            )
        ]

    def __str__(self) -> str:
        return f"[Windows] {self.patch.title}"


class LinuxPatchDetail(models.Model):
    """Linux 补丁扩展 detail 表（与 Patch 1:1）"""

    patch = models.OneToOneField(
        Patch,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="linux_detail",
        verbose_name="补丁主记录",
    )

    pkg_name = models.CharField(max_length=256, blank=True, default="", verbose_name="包名")
    pkg_version = models.CharField(max_length=128, blank=True, default="", verbose_name="包版本")
    distro_name = models.CharField(max_length=64, blank=True, default="", verbose_name="发行版名称")
    os_version_range = models.CharField(max_length=128, blank=True, default="", verbose_name="系统版本范围")
    architectures = models.JSONField(default=list, verbose_name="适用架构")

    repo_type = models.CharField(
        max_length=8,
        choices=PackageManagerType.CHOICES,
        blank=True,
        default="",
        verbose_name="Repo类型",
    )

    # 安装风险信息（apt: Depends/Conflicts/Breaks/Replaces）
    install_deps = models.JSONField(default=dict, verbose_name="安装依赖信息")

    class Meta:
        verbose_name = "Linux补丁详情"
        verbose_name_plural = verbose_name
        db_table = "patch_linux_detail"

    def __str__(self) -> str:
        return f"[Linux] {self.patch.title}"
